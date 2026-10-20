"""交 4,712 唯一图的 sha256 清单（只要 sha256 与规模，不含图像）。

输入（只读）：
  <corpus>/corpus_manifest.csv   唯一内容清单（一行一内容）
  <corpus>/occurrences.csv       (qid,role,rank,sha256) 实例展开

输出：
  <out>/unique_4712_sha256.csv   sha256 + 来源标记
  <out>/unique_4712_summary.json 规模/分布/文件 sha256

来源标记：
  n_instances 该内容在 14,475 个实例里出现几次
  n_query / n_gt / n_retrieved  按角色计数
  roles       角色集合（query;gt;retrieved 的子集，分号分隔）
  in_instances 恒为 1（4,712 ⊂ 14,475，不存在只出现在清单里、却没有实例的内容）

用法：
  python a32_unique_sha_list.py --corpus E:/EdgeCoRAG-A-store/corpus_v1 \
      --out a-side/reports/index_scope_20261021
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROLES = ["query", "gt", "official_retrieved"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=r"E:\EdgeCoRAG-A-store\corpus_v1")
    ap.add_argument("--out", default=r"a-side\reports\index_scope_20261021")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1) 清单：唯一内容
    man_rows = list(csv.DictReader((corpus / "corpus_manifest.csv").open(encoding="utf-8", newline="")))
    sha_col = "sha256" if "sha256" in (man_rows[0] if man_rows else {}) else None
    if sha_col is None:
        sha_col = next(k for k in man_rows[0] if "sha" in k.lower())
    manifest_shas = [r[sha_col].strip() for r in man_rows]
    assert len(manifest_shas) == len(set(manifest_shas)), "corpus_manifest 里有重复 sha256"

    # 2) 实例展开：按 sha 统计角色
    counts: dict[str, Counter] = defaultdict(Counter)
    total_occ = 0
    with (corpus / "occurrences.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sha = row["sha256"].strip()
            counts[sha][row["role"].strip()] += 1
            total_occ += 1

    # 3) 一致性：清单 ⊆ 实例，且实例里的 sha 全在清单里
    occ_shas = set(counts)
    assert occ_shas == set(manifest_shas), (
        f"清单与实例的 sha 集合不一致：清单独有 {len(set(manifest_shas) - occ_shas)}，"
        f"实例独有 {len(occ_shas - set(manifest_shas))}"
    )

    rows = []
    for sha in sorted(manifest_shas):
        c = counts[sha]
        roles = [r for r in ROLES if c.get(r)]
        rows.append({
            "sha256": sha,
            "n_instances": sum(c.values()),
            "n_query": c.get("query", 0),
            "n_gt": c.get("gt", 0),
            "n_official_retrieved": c.get("official_retrieved", 0),
            "roles": ";".join(roles),
            "in_instances": 1,
        })

    csv_p = out / "unique_4712_sha256.csv"
    with csv_p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    role_sets = Counter(r["roles"] for r in rows)
    summary = {
        "schema": "unique_sha_list/v1",
        "corpus": str(corpus),
        "inputs": {
            "corpus_manifest": {"path": str(corpus / "corpus_manifest.csv"),
                                "sha256": hashlib.sha256((corpus / "corpus_manifest.csv").read_bytes()).hexdigest(),
                                "rows": len(manifest_shas)},
            "occurrences": {"path": str(corpus / "occurrences.csv"),
                            "sha256": hashlib.sha256((corpus / "occurrences.csv").read_bytes()).hexdigest(),
                            "rows": total_occ},
        },
        "counts": {
            "unique_contents": len(rows),
            "instances": total_occ,
            "duplicate_instances": total_occ - len(rows),
            "shas_with_multiple_roles": sum(1 for r in rows if ";" in r["roles"]),
        },
        "role_distribution": dict(sorted(role_sets.items())),
        "output": {"path": str(csv_p), "rows": len(rows),
                   "sha256": hashlib.sha256(csv_p.read_bytes()).hexdigest(),
                   "bytes": csv_p.stat().st_size},
        "usage_for_B": (
            "B 侧把 18,955 的 sha256 与本表做交集：命中数 = 落在 4,712 里的条目；"
            "未命中但落在 occurrences.csv 的 sha 集合里 = 落在 14,475 实例里但不在唯一内容里"
            "（本表已含全部实例 sha，故该类为 0）；两边都不在 = 18,955 中的新增内容。"
        ),
        "no_gold": True,
        "no_gpu": True,
    }
    (out / "unique_4712_summary.json").write_bytes(
        (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    print(f"unique={len(rows)} instances={total_occ} duplicates={total_occ - len(rows)}")
    print(f"roles: {dict(sorted(role_sets.items()))}")
    print(f"-> {csv_p}  sha256={summary['output']['sha256'][:16]}  bytes={summary['output']['bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
