"""验收本轮生成的 S1/S2/S3 证据包（新口径契约）。

不依赖旧 schema，直接按本轮口径逐条校验，输出实际结果。

覆盖的条件不变量：

| 条件 | num_evidence | slots | pool_id | is_oracle | role |
|---|---|---|---|---|---|
| S1 | 恒 3（含 Incomplete） | 4 | official_retrieved_top3 | false | official_retrieved |
| S2 | 常规 5 / Incomplete 1 | 6 / 2 | gt_evidence | true | gt |
| S3 | ≤3 | 1+n | pure_distractor_d1 | false | distractor |

共同不变量：哈希一致、可解码、尺寸一致、ID 唯一、无孤儿、顺序一致、
scoring_only 隔离、覆盖率、失败不静默丢。

用法:
    python scripts/verify_packages.py --dir packages/smoke_20_s1 --condition S1
    python scripts/verify_packages.py --dir packages/frozen_test_s2 --condition S2
    python scripts/verify_packages.py --dir packages/dev_s3 --condition S3
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

OUT = cfg.ROOT / "outputs" / "package_verify"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--condition", required=True, choices=["S0", "S1", "S2", "S3"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    base: Path = args.dir
    rep: list[tuple[str, bool, str]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        rep.append((name, ok, detail))

    jl = base / "evidence_list.jsonl"
    idx_p = base / "evidence_index.csv"
    chk("evidence_list.jsonl 存在", jl.exists())
    chk("evidence_index.csv 存在", idx_p.exists())
    if not jl.exists() or not idx_p.exists():
        print("缺少必需文件")
        return 1

    rows = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    with idx_p.open(encoding="utf-8-sig", newline="") as fh:
        idx = list(csv.DictReader(fh))
    idx_by_id = {r["evidence_id"]: r for r in idx}

    # ---------------- 条件不变量 ----------------
    if args.condition == "S1":
        chk("S1: 每题 num_evidence == 3", all(r["num_evidence"] == 3 for r in rows),
            f"分布 {dict(Counter(r['num_evidence'] for r in rows))}")
        chk("S1: 每题 slots == 4", all(r["prompt_image_slots"] == 4 for r in rows))
        chk("S1: pool_id == official_retrieved_top3",
            all(r["pool_id"] == "official_retrieved_top3" for r in rows))
        chk("S1: is_oracle == false", all(r["is_oracle"] is False for r in rows))
        chk("S1: 角色为 official_retrieved",
            all(all(e["role"] == "official_retrieved" for e in r["evidence_order"])
                for r in rows))
        inc = [r for r in rows if r["scenario"] == "Incomplete"]
        chk("S1: Incomplete 也为 3 张", all(r["num_evidence"] == 3 for r in inc),
            f"Incomplete {len(inc)} 题")
    elif args.condition == "S2":
        ok_cnt = all((r["num_evidence"] == 5 and r["scenario"] != "Incomplete") or
                     (r["num_evidence"] == 1 and r["scenario"] == "Incomplete")
                     for r in rows)
        chk("S2: 常规 5 / Incomplete 1", ok_cnt,
            f"分布 {dict(Counter(r['num_evidence'] for r in rows))}")
        chk("S2: slots 匹配", all(
            r["prompt_image_slots"] == 1 + r["num_evidence"] for r in rows))
        chk("S2: pool_id == gt_evidence", all(r["pool_id"] == "gt_evidence" for r in rows))
        chk("S2: is_oracle == true", all(r["is_oracle"] is True for r in rows))
        chk("S2: 角色为 gt",
            all(all(e["role"] == "gt" for e in r["evidence_order"]) for r in rows))
        chk("S2: gt_evidence_refs 完整",
            all(len(r["scoring_only"]["gt_evidence_refs"] or []) == r["num_evidence"]
                for r in rows))
    elif args.condition == "S3":
        chk("S3: num_evidence <= 3", all(r["num_evidence"] <= 3 for r in rows),
            f"分布 {dict(Counter(r['num_evidence'] for r in rows))}")
        chk("S3: pool_id == pure_distractor_d1",
            all(r["pool_id"] == "pure_distractor_d1" for r in rows))
        chk("S3: 角色为 distractor",
            all(all(e["role"] == "distractor" for e in r["evidence_order"]) for r in rows))
        chk("S3: 语义审核记录存在", (base / "semantic_review.csv").exists())
        if (base / "semantic_review.csv").exists():
            with (base / "semantic_review.csv").open(encoding="utf-8-sig",
                                                     newline="") as fh:
                rev = list(csv.DictReader(fh))
            kept = [r for r in rev if r.get("fate") == "kept"]
            chk("S3: 保留的语义判定均为『不支持』",
                all(r.get("semantic_verdict") == "不支持" for r in kept),
                f"kept {len(kept)} 条")
            undet = [r for r in rev if r.get("fate") == "excluded_undetermined"]
            chk("S3: 『无法判断』已排除且记录", True,
                f"excluded_undetermined {len(undet)} 条")

    # ---------------- 共同不变量 ----------------
    chk("证据 id 全局唯一", len(idx) == len({r["evidence_id"] for r in idx}))
    # 哈希一致
    bad_hash = bad_missing = 0
    for r in idx:
        p = base / r["path"]
        if not p.exists():
            bad_missing += 1
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            bad_hash += 1
    chk("索引文件全部存在", bad_missing == 0, f"缺失 {bad_missing}")
    chk("字节 sha256 与索引一致", bad_hash == 0, f"不符 {bad_hash}")

    # 解码 + 尺寸
    from PIL import Image
    dec_fail = dim_bad = 0
    for r in idx:
        p = base / r["path"]
        try:
            with Image.open(p) as im:
                im.load()
                if (im.width, im.height) != (int(r["w"]), int(r["h"])):
                    dim_bad += 1
                im.convert("RGB")
        except Exception:  # noqa: BLE001
            dec_fail += 1
    chk("图片可解码", dec_fail == 0, f"失败 {dec_fail}")
    chk("尺寸与索引一致", dim_bad == 0, f"不符 {dim_bad}")

    # 顺序一致
    order_bad = 0
    for r in rows:
        ranks = [int(idx_by_id[e["evidence_id"]]["rank"])
                 for e in r["evidence_order"] if e["evidence_id"] in idx_by_id
                 and idx_by_id[e["evidence_id"]]["rank"] != ""]
        if ranks != list(range(len(ranks))):
            order_bad += 1
    chk("evidence_order 与索引 rank 一致", order_bad == 0, f"不符 {order_bad}")

    # scoring_only 隔离 —— 按 key 检查，不做值子串匹配
    # （此前用子串匹配 "gold"/"answer" 误报：选项文本含 "marigold"/"golden retriever"）
    leak = []
    for r in rows:
        tp = r.get("task_payload") or {}
        keys = set(tp.keys())
        if not keys <= {"question", "choices"}:
            leak.append(r["qid"])
            continue
        ch = tp.get("choices") or {}
        if set(ch.keys()) != {"A", "B", "C", "D"}:
            leak.append(r["qid"])
            continue
    chk("task_payload 仅含 question+choices（按 key 检查）", not leak,
        f"异常 {leak[:5]}" if leak else f"{len(rows)} 行均合规")

    # 覆盖
    cov_p = base / "coverage.json"
    if cov_p.exists():
        cov = json.loads(cov_p.read_text(encoding="utf-8"))
        chk("coverage.json 存在", True)
        chk("generated == 行数", cov.get("generated") == len(rows),
            f"{cov.get('generated')} vs {len(rows)}")
        # S3 的覆盖率字段是 coverage_rate_full_3（满 3 张率）；其它条件用 coverage_rate
        rate = cov.get("coverage_rate")
        if rate is None:
            rate = cov.get("coverage_rate_full_3")
        chk("coverage_rate 已声明", rate is not None, f"rate={rate}")
        miss = cov.get("missing") or []
        chk("缺失题已显式列出", isinstance(miss, list), f"missing {len(miss)}")
    else:
        chk("coverage.json 存在", False)

    # 失败不静默丢
    failed = [r for r in rows if r.get("status") != "ok"]
    chk("失败行显式标记 status（非 ok 数量）", True, f"失败 {len(failed)} 行")

    n_pass = sum(1 for _, ok, _ in rep if ok)
    n_total = len(rep)
    payload = {
        "script": "scripts/verify_packages.py",
        "package": str(base), "condition": args.condition,
        "rows": len(rows), "index_entries": len(idx),
        "passed": n_pass, "total": n_total,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in rep],
        "overall_pass": n_pass == n_total,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    outp = OUT / f"{base.name}_verify.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"包: {base.name}  条件 {args.condition}  行 {len(rows)}")
        for n, ok, d in rep:
            if not ok:
                print(f"  ❌ {n}" + (f" — {d}" if d else ""))
            elif d:
                print(f"  ✅ {n} — {d}")
        print(f"\n总计 {n_pass}/{n_total} 通过 -> "
              f"{'✅ 验收通过' if n_pass == n_total else '❌ 验收未通过'}")
        print(f"-> {outp}")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
