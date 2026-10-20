"""统一接口下的检索指标（any-hit / 集合召回 / MRR），按维度与 cohort 分开。

任务 1/2/4 共用。指标定义按 B 侧要求冻结：
  any-hit@k  = 1[top-k ∩ GT非空]                  分母 = 有非空 GT 的题
  set-recall@k = |top-k ∩ GT| / |GT|              逐题求值后取题均值
  all-GT@k   = 1[GT ⊆ top-k]
  MRR@10     = 1 / 首个精确命中的名次（未命中为 0）
GT 身份 = 与候选同一口径（JPEG q95 字节 sha256）。精确哈希命中 != 语义支持。

纪律：维度只能用 dev_150 决定；frozen_test 数值仅描述性，禁止据此反选。

用法: python scripts/a16_retrieval_metrics.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IFACE = ROOT / "a-side" / "retrieval_if_v1"
CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
OUT = ROOT / "a-side" / "retrieval_if_v1" / "metrics"
COHORTS = ["smoke_20", "dev_150", "frozen_test"]
DIMS = [768, 512, 256, 128]


def gt_map() -> dict[str, set[str]]:
    g: dict[str, set[str]] = {}
    for line in (CORPUS / "occurrences.csv").read_text(encoding="utf-8").splitlines()[1:]:
        qid, role, _rank, sha = line.split(",")
        if role == "gt":
            g.setdefault(qid, set()).add(sha)
    return g


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gt = gt_map()
    rows = []
    summary = {}
    for cohort in COHORTS:
        for dim in DIMS:
            p = IFACE / "pools" / f"{cohort}__dim{dim}__top10.csv"
            if not p.exists():
                continue
            pools: dict[str, list[str]] = {}
            with p.open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    pools.setdefault(r["qid"], []).append(r["sha256"])
            qids = [q for q in pools if gt.get(q)]
            n = len(qids)
            a1 = a5 = a10 = a_all = 0
            rr = 0.0
            rec5 = rec10 = 0.0
            for q in qids:
                top = pools[q]
                inter5 = len(set(top[:5]) & gt[q])
                inter10 = len(set(top) & gt[q])
                a1 += 1 if inter5 and top[0] in gt[q] else 0
                a5 += 1 if inter5 else 0
                a10 += 1 if inter10 else 0
                a_all += 1 if gt[q] <= set(top) else 0
                rec5 += inter5 / len(gt[q])
                rec10 += inter10 / len(gt[q])
                for rank, sha in enumerate(top, 1):
                    if sha in gt[q]:
                        rr += 1.0 / rank
                        break
            summary[f"{cohort}|{dim}"] = {
                "questions": n,
                "any_hit@1": round(a1 / n, 6), "any_hit@5": round(a5 / n, 6), "any_hit@10": round(a10 / n, 6),
                "set_recall@5": round(rec5 / n, 6), "set_recall@10": round(rec10 / n, 6),
                "all_gt_covered@10": round(a_all / n, 6), "MRR@10": round(rr / n, 6),
                "counts": {"any_hit@1": a1, "any_hit@5": a5, "any_hit@10": a10, "all_gt@10": a_all},
            }
            rows.append({"cohort": cohort, "embed_dim": dim, "questions": n, **{k: v for k, v in summary[f"{cohort}|{dim}"].items() if k != "counts"},
                         **summary[f"{cohort}|{dim}"]["counts"]})

    with (OUT / "retrieval_metrics_by_dim.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    doc = {
        "protocol": "a-side/retrieval-interface-v1",
        "identity": "sha256(JPEG q95 bytes)",
        "metrics_definition": {
            "any_hit@k": "1[top-k ∩ GT 非空] / 有非空GT的题数",
            "set_recall@k": "逐题 |top-k ∩ GT| / |GT| 后取题均值",
            "all_gt_covered@10": "1[GT ⊆ top-10]",
            "MRR@10": "首个精确命中名次倒数，未命中 0",
        },
        "cohorts": summary,
        "discipline": [
            "维度只能由 dev_150 决定；frozen_test 数值仅描述性，禁止反选维度或阈值",
            "精确哈希命中不等于语义支持；未命中 GT 也不等于检索失败（GT 不穷尽有效证据）",
            "本表为已观察数据上的复核，不是新盲测",
        ],
        "known_gap": "已发布 smoke 报告的索引规模 18,955 与本语料 4,712（唯一内容）不一致，索引口径待 B 提供构建回执",
    }
    (OUT / "retrieval_metrics.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{'cohort':12s} {'dim':>4s} {'n':>5s} {'hit@1':>7s} {'hit@5':>7s} {'hit@10':>7s} {'rec@5':>7s} {'rec@10':>7s} {'MRR':>7s}")
    for k, v in summary.items():
        c, d = k.split("|")
        print(f"{c:12s} {d:>4s} {v['questions']:>5d} {v['any_hit@1']:>7.4f} {v['any_hit@5']:>7.4f} {v['any_hit@10']:>7.4f} "
              f"{v['set_recall@5']:>7.4f} {v['set_recall@10']:>7.4f} {v['MRR@10']:>7.4f}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
