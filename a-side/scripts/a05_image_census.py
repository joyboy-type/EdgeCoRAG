"""MRAG-Bench 映像普查：统计题目/图像实例/唯一身份，核对检索索引规模口径。

产出（供检索一致性审计与统一接口冻结使用）：
  - 14,475 个"图像实例"(1353 查询 + 6,357 GT + 6,765 官方候选)的原始字节 sha256
  - 唯一身份计数（全局/分角色/角色交集）
  - 与已知索引规模 18,955 的口径核对结论

不联网、不改动数据集与既有包。原始字节直接取自 parquet 的 struct<bytes> 字段。

用法: python scripts/a05_image_census.py [--q95-sample N] [--out outputs/census]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
REPO = "uclanlp/MRAG-Bench"
REV = "43620fde4044bb150e158c67ad7af6b6b11e1da2"


def q95_sha(raw: bytes) -> str | None:
    from PIL import Image

    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None
    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=95)
    return hashlib.sha256(b.getvalue()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--q95-sample", type=int, default=0, help="对多少张图额外计算 JPEG q95 身份用于口径核对")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs" / "census")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    shards = sorted(DATA.glob("test-*.parquet"))
    roles: dict[str, Counter] = {"query": Counter(), "gt": Counter(), "ret": Counter()}
    per_q: dict[str, dict[str, int]] = {}
    instances = 0
    q95_pairs: list[tuple[str, str, str]] = []  # (qid, role, raw_sha, q95_sha)

    t0 = time.time()
    for sh in shards:
        pf = pq.ParquetFile(sh)
        for rg in range(pf.num_row_groups):
            tbl = pf.read_row_group(rg, columns=["id", "image", "gt_images", "retrieved_images"])
            for row in tbl.to_pylist():
                qid = f"mragb:{row['id']}"
                qraw = row["image"]["bytes"]
                per_q[qid] = {"gt": len(row["gt_images"]), "ret": len(row["retrieved_images"])}
                roles["query"][hashlib.sha256(qraw).hexdigest()] += 1
                instances += 1
                if args.q95_sample and len(q95_pairs) < args.q95_sample:
                    s = q95_sha(qraw)
                    if s:
                        q95_pairs.append((qid, "query", hashlib.sha256(qraw).hexdigest(), s))
                for g in row["gt_images"]:
                    roles["gt"][hashlib.sha256(g["bytes"]).hexdigest()] += 1
                    instances += 1
                    if args.q95_sample and len(q95_pairs) < args.q95_sample:
                        s = q95_sha(g["bytes"])
                        if s:
                            q95_pairs.append((qid, "gt", hashlib.sha256(g["bytes"]).hexdigest(), s))
                for r in row["retrieved_images"]:
                    roles["ret"][hashlib.sha256(r["bytes"]).hexdigest()] += 1
                    instances += 1
                    if args.q95_sample and len(q95_pairs) < args.q95_sample:
                        s = q95_sha(r["bytes"])
                        if s:
                            q95_pairs.append((qid, "ret", hashlib.sha256(r["bytes"]).hexdigest(), s))

    all_keys = set()
    for c in roles.values():
        all_keys |= set(c)

    gt_q = set(roles["gt"]) & set(roles["query"])
    ret_q = set(roles["ret"]) & set(roles["query"])
    gt_ret = set(roles["gt"]) & set(roles["ret"])

    q95_identity_collisions = 0
    raw_to_q95: dict[str, set[str]] = {}
    for _qid, _role, raw, q in q95_pairs:
        raw_to_q95.setdefault(raw, set()).add(q)
    q95_multi = {k: v for k, v in raw_to_q95.items() if len(v) > 1}
    q95_identity_collisions = len(q95_multi)

    report = {
        "dataset": {"repo": REPO, "revision": REV, "split": "test", "shards": len(shards)},
        "identity": {
            "raw_sha256": "parquet struct<bytes> 原始字节的 sha256（本次新增口径）",
            "jpeg_q95_sha256": "既有包/审计使用的身份口径（JPEG q95 重编码后 sha256）",
        },
        "questions": len(per_q),
        "image_instances": instances,
        "instances_by_role": {k: sum(c.values()) for k, c in roles.items()},
        "unique_by_role": {k: len(c) for k, c in roles.items()},
        "unique_union": len(all_keys),
        "role_intersections": {
            "gt_and_query": len(gt_q),
            "ret_and_query": len(ret_q),
            "gt_and_ret": len(gt_ret),
        },
        "duplicate_instances": {
            "query": sum(v - 1 for v in roles["query"].values()),
            "gt": sum(v - 1 for v in roles["gt"].values()),
            "ret": sum(v - 1 for v in roles["ret"].values()),
        },
        "index_size_checks": {
            "claimed_18955": 18955,
            "instances": instances,
            "unique_raw": len(all_keys),
            "instances_eq_18955": instances == 18955,
            "unique_eq_18955": len(all_keys) == 18955,
        },
        "q95_sample": {
            "pairs": len(q95_pairs),
            "same_raw_same_q95": len(q95_pairs) - q95_identity_collisions,
            "same_raw_diff_q95": q95_identity_collisions,
        },
        "elapsed_seconds": round(time.time() - t0, 1),
    }

    (args.out / "image_census.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # 逐题实例计数（便于核对）
    with (args.out / "per_question_image_counts.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("qid,gt_images,retrieved_images,total\n")
        for qid in sorted(per_q, key=lambda s: int(s.split(":")[1])):
            d = per_q[qid]
            f.write(f"{qid},{d['gt']},{d['ret']},{1 + d['gt'] + d['ret']}\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
