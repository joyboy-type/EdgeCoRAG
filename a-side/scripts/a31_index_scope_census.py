"""任务1：索引口径普查——三个数（18,955 / 14,475 / 4,712）各是什么，逐项可追到文件与行。

只读：数据集 parquet（计数用，不解码图像）+ corpus_v1 清单。不读 gold、不联网、不用 GPU。

用法：
    python a31_index_scope_census.py --data <parquet 目录> --corpus <corpus_v1> --out <目录>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

CLAIMED_INDEX_ROWS = 18955  # 已发布 smoke 报告写的索引条目数（B 侧回执 index.entries 同值）


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
    ap.add_argument("--corpus", default=r"E:\EdgeCoRAG-A-store\corpus_v1")
    ap.add_argument("--out", default=r"C:\Users\zhang'cheng'xuan\Desktop\1\EdgeCoRAG-A\a-side\reports\order_diff_20261021")
    args = ap.parse_args()

    data = Path(args.data)
    corpus = Path(args.corpus)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    shards = sorted(data.glob("test-*.parquet"))
    per_shard = []
    total_q = total_gt = total_ret = 0
    per_question = []
    for sh in shards:
        pf = pq.ParquetFile(sh)
        n_q = n_gt = n_ret = 0
        for rg in range(pf.num_row_groups):
            tbl = pf.read_row_group(rg, columns=["id", "gt_images", "retrieved_images"])
            for row in tbl.to_pylist():
                g = len(row["gt_images"])
                r = len(row["retrieved_images"])
                n_q += 1
                n_gt += g
                n_ret += r
                per_question.append({"qid": f"mragb:{row['id']}", "gt": g, "retrieved": r,
                                     "total": 1 + g + r})
        per_shard.append({"file": sh.name, "rows": n_q, "gt": n_gt, "retrieved": n_ret,
                          "instances": n_q + n_gt + n_ret})
        total_q += n_q
        total_gt += n_gt
        total_ret += n_ret

    instances = total_q + total_gt + total_ret

    man = (corpus / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()
    manifest_rows = len(man) - 1
    occ_rows = len((corpus / "occurrences.csv").read_text(encoding="utf-8").splitlines()) - 1
    meta = json.loads((corpus / "corpus_meta.json").read_text(encoding="utf-8"))
    unique = manifest_rows
    duplicates = instances - unique

    report = {
        "task": "index_scope_20261021 / 索引口径普查",
        "inputs": {
            "data_dir": str(data), "shards": len(shards),
            "corpus_manifest": {"path": str(corpus / "corpus_manifest.csv"),
                                "sha256": sha_file(corpus / "corpus_manifest.csv")},
            "occurrences": {"path": str(corpus / "occurrences.csv"),
                            "sha256": sha_file(corpus / "occurrences.csv"), "rows": occ_rows},
            "corpus_meta": {"path": str(corpus / "corpus_meta.json"),
                            "sha256": sha_file(corpus / "corpus_meta.json"),
                            "content_digest_sha256": meta.get("content_digest_sha256")},
        },
        "three_numbers": {
            "claimed_index_rows": CLAIMED_INDEX_ROWS,
            "image_instances_recomputable": instances,
            "unique_contents_recomputable": unique,
            "duplicate_instances": duplicates,
            "delta_claimed_minus_instances": CLAIMED_INDEX_ROWS - instances,
            "delta_claimed_minus_unique": CLAIMED_INDEX_ROWS - unique,
        },
        "instance_decomposition": {
            "query_images": total_q, "gt_images": total_gt, "retrieved_images": total_ret,
            "formula": f"{total_q}（每题 1 张查询图） + {total_gt}（GT 实例） + {total_ret}（官方候选实例） = {instances}",
        },
        "per_shard": per_shard,
        "per_question_count_check": {
            "questions": len(per_question),
            "gt_counts": _counts(per_question, "gt"),
            "retrieved_counts": _counts(per_question, "retrieved"),
            "total_matches": sum(p["total"] for p in per_question) == instances,
        },
        "verdict": {
            "usable_as_instance_count": instances,
            "usable_as_unique_content_count": unique,
            "claimed_index_rows_self_evident": False,
            "why": ("18,955 无法用公开数据集复核：按 (qid, role, index) 展开只有 14,475 个实例，"
                    "按内容去重只有 4,712 个唯一内容；两者都不等于 18,955。"
                    "B 侧回执称 dedup=true / kept_duplicates=0，即索引里有 18,955 个互不重复的身份，"
                    "比可复核的唯一内容多 14,243，比实例多 4,480——其构成需要 sources[] 才能确认。"),
            "missing_inputs": ["index_receipt.sources[]（额外语料的 path/sha256/规模）",
                               "index.artifact_files[] 的逐文件 sha256 与行数",
                               "若 identity 为 sha256_raw_bytes：额外内容是否与数据集图像有交集"],
        },
        "gaps": [
            {"delta": CLAIMED_INDEX_ROWS - instances, "meaning": "18,955 − 14,475",
             "self_evident": False,
             "note": "不能用算术拆解成'多出的图'——需要 sources[] 证据"},
            {"delta": CLAIMED_INDEX_ROWS - unique, "meaning": "18,955 − 4,712",
             "self_evident": False, "note": "同上；等于实例重复被计入两次的差额 4,480 + 9,763"},
        ],
        "cross_check_duplicates": {
            "instances_minus_unique": duplicates,
            "note": "9,763 = 同一内容在 1,353 题的不同角色/名下重复出现的次数；"
                    "corpus_v1 已按 sha256 去重，故 9,763 不出现在索引行数里",
        },
    }
    p = out / "census.json"
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"shards={len(shards)}  questions={total_q}  gt={total_gt}  retrieved={total_ret}")
    print(f"instances={instances}  unique={unique}  duplicates={duplicates}")
    print(f"claimed={CLAIMED_INDEX_ROWS}  delta_vs_instances={CLAIMED_INDEX_ROWS - instances}"
          f"  delta_vs_unique={CLAIMED_INDEX_ROWS - unique}")
    print(f"-> {p}")
    return 0


def _counts(rows: list[dict], key: str) -> dict:
    c: dict[int, int] = {}
    for r in rows:
        c[r[key]] = c.get(r[key], 0) + 1
    return {str(k): v for k, v in sorted(c.items())}


if __name__ == "__main__":
    sys.exit(main())
