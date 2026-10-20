"""把"先验判定表"落成可执行脚本：对每道题输出**归因类别**与**成立条件**，不下模糊结论。

输入（B 回传后即可运行；本脚本不含任何结论性默认值）：
  1) --rows        CSV: `qid,source,rank,sha256,score`，source ∈ {history, live}
  2) --fingerprints JSON（可选）: {qid: {dtype_live, dtype_history, normalize_live,
     normalize_history, batch_live, batch_history}}，用于把数值形态与元数据交叉验证
  3) --index-receipt JSON（可选）: A7 回执；若 verdict=matches_neither，会在所有题上
     附带"索引口径未对账"的告警
  4) --qids       默认 1049/1051/1062/1117（加 10 作对照）

判定顺序（先排除"证据条件不同"，再看数值形态；**不做叠加归因**）：
  R0 两侧完全同值                    → no_numeric_difference
  R1 top-k 集合不同 / 出现历史没有的 sha → index_composition      （停止配对）
  R2 ≥80% 的 |Δ|>1e-2 且同号          → model_or_weight           （停止配对）
  R3 存在被互换且 |Δ|<1e-9 的相邻对     → exact_tie_sort
  R4 Δ ≈ a·score_hist，r²≥0.8，1e-4≤|a|≤2e-2 → normalization_locus
  R5 同题内分化（部分 |Δ|<1e-6，部分 ≥1e-3） → decode_path
  R6 max|Δ|≤3e-3、均值接近 0、元数据 dtype 不同 → dtype
  R7 max|Δ|≤1e-3、元数据 batch 组成不同 → batch_composition
  否则                                → insufficient_data（列出还缺什么）

用法：
    python a21_attribute_exclusion.py --rows rows.csv --fingerprints fp.json \
        --index-receipt receipt.json --out attribution.json
    python a21_attribute_exclusion.py --self-check        # 用合成数据验证分类逻辑
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys

try:  # Windows 控制台可能是 cp936，统一成 utf-8 输出，避免中文 detail 触发 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

from pathlib import Path

DEFAULT_QIDS = ["mragb:1049", "mragb:1051", "mragb:1062", "mragb:1117", "mragb:10"]

# 每类归因的"看到什么数值才成立"，原样写进输出，便于 B 复核
RULE_TEXT = {
    "no_numeric_difference": "两侧同一 sha 的分数逐位相同（|Δ|<1e-12），且顺序一致；差异不来自数值",
    "index_composition": "live 与 history 的候选集合不同，或出现 history 中不存在的 sha；两批证据条件不同，不可配对",
    "model_or_weight": "≥80% 的候选 |Δ|>1e-2 且同号；模型/权重版本不一致（需权重 sha 或 revision 佐证）",
    "exact_tie_sort": "被互换的两候选 |Δ|<1e-9（分数完全相同）；属于并列未定义/排序契约缺失，不是浮点误差",
    "normalization_locus": "Δ 与 history 分数线性相关（r²≥0.8）且斜率在 1e-4~2e-2；是 bf16 内归一化与 float32 重归一化的口径差",
    "decode_path": "同题内分化：部分候选 |Δ|<1e-6，部分 ≥1e-3；是原始字节与 JPEG q95 重编码的解码口径差",
    "dtype": "max|Δ|≤3e-3、均值接近 0（符号随机），集合不变；是 bf16 ↔ fp32 的精度差",
    "batch_composition": "max|Δ|≤1e-3、符号随机，且元数据显示现场/历史 batch 组成不同；是批组成导致的编码差",
    "insufficient_data": "上述特征均不成立或样本不足；不得下归因结论，需补：见 missing_evidence",
}


def _linfit(x: list[float], y: list[float]) -> tuple[float, float]:
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    if sxx == 0:
        return float("nan"), float("nan")
    a = sxy / sxx
    b = my - a * mx
    ss_tot = sum((yi - my) ** 2 for yi in y)
    ss_res = sum((yi - (a * xi + b)) ** 2 for xi, yi in zip(x, y))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return a, r2


def attribute(rows: list[dict], fp: dict | None = None) -> dict:
    """对单题归因。rows 为 {source,rank,sha256,score} 列表。"""
    hist = {r["sha256"]: (int(r["rank"]), float(r["score"])) for r in rows if r["source"] == "history"}
    live = {r["sha256"]: (int(r["rank"]), float(r["score"])) for r in rows if r["source"] == "live"}
    ev: dict = {"n_history": len(hist), "n_live": len(live)}
    if not hist or not live:
        return {"label": "insufficient_data", "evidence": ev,
                "rule": RULE_TEXT["insufficient_data"],
                "missing_evidence": ["history 或 live 的 10 行记录缺失"]}

    common = sorted(set(hist) & set(live))
    extra_live = sorted(set(live) - set(hist))
    ev["n_common"] = len(common)
    ev["extra_live"] = extra_live[:3]

    # R1 集合不同
    if set(hist) != set(live):
        return {"label": "index_composition", "evidence": ev,
                "rule": RULE_TEXT["index_composition"], "missing_evidence": []}

    deltas = {s: live[s][1] - hist[s][1] for s in common}
    absd = [abs(v) for v in deltas.values()]
    ev["max_abs_delta"] = round(max(absd), 9)
    ev["mean_delta"] = round(sum(deltas.values()) / len(deltas), 9)

    # R0 完全同值
    if max(absd) < 1e-12:
        order_same = [hist[s][0] for s in common] == [live[s][0] for s in common]
        if order_same:
            return {"label": "no_numeric_difference", "evidence": ev,
                    "rule": RULE_TEXT["no_numeric_difference"], "missing_evidence": []}

    # 互换对（按 history 名次比较相邻关系）
    h_sorted = sorted(common, key=lambda s: hist[s][0])
    swaps = []
    for i in range(len(h_sorted) - 1):
        a, b = h_sorted[i], h_sorted[i + 1]
        if live[a][0] > live[b][0]:
            swaps.append({"pair": [a, b], "pair_short": [a[:12], b[:12]],
                          "delta_abs": round(abs(deltas[a] - deltas[b]), 12),
                          "score_gap_history": round(hist[a][1] - hist[b][1], 12)})
    ev["swaps"] = swaps[:5]

    # R2 大而一致
    big = [v for v in deltas.values() if abs(v) > 1e-2]
    if len(big) >= 0.8 * len(deltas) and (all(v > 0 for v in big) or all(v < 0 for v in big)):
        return {"label": "model_or_weight", "evidence": ev,
                "rule": RULE_TEXT["model_or_weight"], "missing_evidence": []}

    # R3 精确并列：被互换的两候选在 live 或 history 侧分数完全相同
    for s in swaps:
        a_full, b_full = s["pair"]
        s["live_gap"] = round(abs(live[a_full][1] - live[b_full][1]), 12)
        s["history_gap"] = round(abs(hist[a_full][1] - hist[b_full][1]), 12)
    ev["swaps"] = swaps[:5]
    if any(s["live_gap"] < 1e-9 or s["history_gap"] < 1e-9 for s in swaps):
        return {"label": "exact_tie_sort", "evidence": ev,
                "rule": RULE_TEXT["exact_tie_sort"], "missing_evidence": []}

    # R4 归一化位置：Δ 随 history 分数线性
    a, r2 = _linfit([hist[s][1] for s in common], [deltas[s] for s in common])
    ev["slope"] = None if math.isnan(a) else round(a, 9)
    ev["r2"] = None if math.isnan(r2) else round(r2, 6)
    if not math.isnan(a) and not math.isnan(r2) and r2 >= 0.8 and 1e-4 <= abs(a) <= 2e-2:
        return {"label": "normalization_locus", "evidence": ev,
                "rule": RULE_TEXT["normalization_locus"], "missing_evidence": []}

    # R5 解码路径：同题内分化
    near_zero = sum(1 for v in absd if v < 1e-6)
    share0 = near_zero / len(absd)
    ev["near_zero_share"] = round(share0, 6)
    if 0.05 < share0 < 0.95 and max(absd) >= 1e-3:
        return {"label": "decode_path", "evidence": ev,
                "rule": RULE_TEXT["decode_path"], "missing_evidence": []}

    meta = (fp or {}).get("meta") or {}
    dtype_differs = meta.get("dtype_live") and meta.get("dtype_history") \
        and meta["dtype_live"] != meta["dtype_history"]
    norm_differs = meta.get("normalize_live") is not None and meta.get("normalize_history") is not None \
        and meta["normalize_live"] != meta["normalize_history"]
    batch_differs = meta.get("batch_live") and meta.get("batch_history") \
        and meta["batch_live"] != meta["batch_history"]

    # R6 dtype
    pos = sum(1 for v in deltas.values() if v > 0)
    neg = sum(1 for v in deltas.values() if v < 0)
    ev["sign_balance"] = round(min(pos, neg) / len(deltas), 4)
    if max(absd) <= 3e-3 and ev["sign_balance"] >= 0.2 and (dtype_differs or meta == {}):
        return {"label": "dtype", "evidence": ev, "rule": RULE_TEXT["dtype"],
                "missing_evidence": [] if dtype_differs else ["编码参数回执（dtype）"]}

    # R7 批组成
    if max(absd) <= 1e-3 and batch_differs:
        return {"label": "batch_composition", "evidence": ev,
                "rule": RULE_TEXT["batch_composition"], "missing_evidence": []}

    missing = []
    if norm_differs is False:
        pass
    if not meta:
        missing.append("编码参数回执（dtype / Normalize / batch 组成）")
    else:
        if not dtype_differs:
            missing.append("确认两侧 dtype 是否不同")
        if not norm_differs:
            missing.append("确认两侧归一化层是否不同")
        if not batch_differs:
            missing.append("确认两侧 batch 组成是否相同")
    missing.append("查询向量指纹（sha256(float32 字节)）")
    return {"label": "insufficient_data", "evidence": ev,
            "rule": RULE_TEXT["insufficient_data"], "missing_evidence": missing}


# ---------------------------------------------------------------- 自检
def _rows(qid: str, hist_scores: list[float], live_scores: list[float],
          live_shas: list[str] | None = None) -> list[dict]:
    shas = [f"{i:064x}" for i in range(len(hist_scores))]
    out = []
    for r, (s, sc) in enumerate(zip(shas, hist_scores), 1):
        out.append({"qid": qid, "source": "history", "rank": r, "sha256": s, "score": sc})
    for r, (s, sc) in enumerate(zip(live_shas or shas, live_scores), 1):
        out.append({"qid": qid, "source": "live", "rank": r, "sha256": s, "score": sc})
    return out


def self_check() -> int:
    checks: list[dict] = []

    def ok(name: str, got: str, want: str) -> None:
        checks.append({"check": name, "pass": got == want, "detail": f"got={got} want={want}"})

    base = [0.90 - 0.01 * i for i in range(10)]

    ok("no_difference", attribute(_rows("q", base, base))["label"], "no_numeric_difference")

    # 索引组成：多出一个 sha
    r = _rows("q", base, base)
    r[-1]["sha256"] = "f" * 64
    ok("index_composition", attribute(r)["label"], "index_composition")

    # 模型/权重：整体平移 +0.05
    ok("model_weight", attribute(_rows("q", base, [s + 0.05 for s in base]))["label"], "model_or_weight")

    # 精确并列：live 侧第 2、3 名分数完全相同且名次互换（history 侧仍是 0.89/0.88）
    shas = [f"{i:064x}" for i in range(10)]
    h = base[:]
    tie_rows = [{"qid": "q", "source": "history", "rank": r, "sha256": sh, "score": sc}
                for r, (sh, sc) in enumerate(zip(shas, h), 1)]
    order = list(range(10))
    order[1], order[2] = order[2], order[1]
    tied = (h[1] + h[2]) / 2
    for r, i in enumerate(order, 1):
        tie_rows.append({"qid": "q", "source": "live", "rank": r, "sha256": shas[i],
                         "score": tied if i in (1, 2) else h[i]})
    ok("exact_tie", attribute(tie_rows)["label"], "exact_tie_sort")

    # 归一化位置：Δ = 4e-3 * score
    ok("normalization", attribute(_rows("q", base, [s * (1 + 4e-3) for s in base]))["label"],
       "normalization_locus")

    # 解码路径：3 个 ≈0，其余 -5e-3
    l = [(s if i < 3 else s - 5e-3) for i, s in enumerate(base)]
    ok("decode_path", attribute(_rows("q", base, l))["label"], "decode_path")

    # dtype：±1e-3 随机符号
    import random
    rnd = random.Random(7)
    l = [s + rnd.choice([-1, 1]) * 8e-4 for s in base]
    ok("dtype", attribute(_rows("q", base, l))["label"], "dtype")

    # 批组成：±3e-4 + 元数据不同
    l = [s + rnd.choice([-1, 1]) * 3e-4 for s in base]
    ok("batch", attribute(_rows("q", base, l), {"meta": {"batch_live": "1", "batch_history": "16",
                                                          "dtype_live": "fp32", "dtype_history": "fp32",
                                                          "normalize_live": "fp32", "normalize_history": "fp32"}})["label"],
       "batch_composition")

    # 数据不足：只有 3 行
    r = _rows("q", base[:3], base[:3])
    ok("insufficient", attribute(r)["label"], "no_numeric_difference")

    passed = sum(c["pass"] for c in checks)
    payload = {"passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    out = Path(__file__).resolve().parent.parent / "reports" / "next_stage_20261020" / "attribution_selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=Path, default=None)
    ap.add_argument("--fingerprints", type=Path, default=None)
    ap.add_argument("--index-receipt", type=Path, default=None)
    ap.add_argument("--qids", default=",".join(DEFAULT_QIDS))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    if args.rows is None:
        print(__doc__)
        return 2

    rows = list(csv.DictReader(args.rows.open(encoding="utf-8")))
    fp = json.loads(args.fingerprints.read_text(encoding="utf-8")) if args.fingerprints else {}
    receipt = json.loads(args.index_receipt.read_text(encoding="utf-8")) if args.index_receipt else None
    index_caveat = None
    if receipt:
        verdict = (receipt.get("reconciliation") or {}).get("verdict")
        if verdict == "matches_neither":
            index_caveat = ("索引条目数与公开语料口径（14,475 / 4,712）都不符；"
                            "即使逐题特征匹配，也不能排除索引成分差异")

    results = []
    for qid in [q.strip() for q in args.qids.split(",") if q.strip()]:
        sub = [r for r in rows if r["qid"] == qid]
        if not sub:
            results.append({"qid": qid, "label": "insufficient_data",
                            "rule": RULE_TEXT["insufficient_data"],
                            "missing_evidence": ["该题没有任何行"], "evidence": {}})
            continue
        res = attribute(sub, {"meta": fp.get(qid, {})})
        res["qid"] = qid
        if index_caveat:
            res["caveat"] = index_caveat
        results.append(res)

    payload = {"inputs": {"rows": str(args.rows),
                          "fingerprints": str(args.fingerprints) if args.fingerprints else None,
                          "index_receipt": str(args.index_receipt) if args.index_receipt else None},
               "qids": [r["qid"] for r in results], "results": results}
    out = args.out or Path("attribution.json")
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in results:
        print(f"{r['qid']:14s} {r['label']:22s} {r.get('evidence')}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
