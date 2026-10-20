"""构建 A 侧规范化检索语料（唯一内容身份 + 哈希可验证）。

目的（对应本轮任务 1/2）：
  * 把"候选身份"写成可验证的确定性对象：JPEG q95 重编码字节的 sha256（沿用既有包/审计口径）；
  * 同一内容只保留一行，消除"同一张图以多个 evidence 身份出现"造成的并列（tie）；
  * 固定行序（按 sha256 升序），使任何实现都能得到同样的索引行序，tie 不再依赖发现顺序。

产出（默认 E:\\EdgeCoRAG-A-store\\corpus_v1，不写入工作区、不改动既有包）：
  images/<aa>/<sha>.jpg     唯一内容的 q95 字节（与 sha 同源，可逐文件校验）
  occurrences.csv           每个 (qid, role, rank) 实例 -> sha 的映射
  corpus_manifest.csv       索引行序：row,sha256,bytes,w,h,first_seen
  corpus_meta.json          content_digest / 计数 / 口径 / 复现命令

用法:
    python scripts/a06_build_corpus.py [--store E:\\EdgeCoRAG-A-store\\corpus_v1] [--verify]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
REPO = "uclanlp/MRAG-Bench"
REV = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
CORPUS_VERSION = "corpus_v1"


def q95_bytes(raw: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    im.load()
    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=95)
    return b.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=Path(r"E:\EdgeCoRAG-A-store") / CORPUS_VERSION)
    ap.add_argument("--verify", action="store_true", help="仅重算哈希并与既有清单核对，不重写图片")
    args = ap.parse_args()
    store: Path = args.store

    shards = sorted(DATA.glob("test-*.parquet"))
    if not shards:
        print(f"找不到分片: {DATA}", file=sys.stderr)
        return 1
    print(f"分片 {len(shards)} 个  ->  {store}")

    # ---------------- 第 1 遍：解出唯一内容并落盘
    t0 = time.time()
    if not args.verify:
        (store / "images").mkdir(parents=True, exist_ok=True)
    occ_rows: list[tuple[str, str, str, str]] = []  # qid, role, rank, sha
    seen: dict[str, dict] = {}                      # sha -> {bytes,w,h,first_seen}
    order_of_first_seen: list[str] = []

    for sh in shards:
        pf = pq.ParquetFile(sh)
        for rg in range(pf.num_row_groups):
            tbl = pf.read_row_group(rg, columns=["id", "image", "gt_images", "retrieved_images"])
            for row in tbl.to_pylist():
                qid = f"mragb:{row['id']}"
                items: list[tuple[str, str, bytes]] = [("query", "", row["image"]["bytes"])]
                items += [("gt", str(i), g["bytes"]) for i, g in enumerate(row["gt_images"])]
                items += [("official_retrieved", str(i), r["bytes"]) for i, r in enumerate(row["retrieved_images"])]
                for role, rank, raw in items:
                    b = q95_bytes(raw)
                    sha = hashlib.sha256(b).hexdigest()
                    occ_rows.append((qid, role, rank, sha))
                    if sha in seen:
                        seen[sha]["occurrences"] += 1
                        continue
                    from PIL import Image

                    im = Image.open(io.BytesIO(b))
                    seen[sha] = {"bytes": len(b), "w": im.width, "h": im.height,
                                 "first_seen": f"{qid}#{role}{rank}", "occurrences": 1}
                    order_of_first_seen.append(sha)
                    if not args.verify:
                        d = store / "images" / sha[:2]
                        d.mkdir(parents=True, exist_ok=True)
                        p = d / f"{sha}.jpg"
                        if not p.exists():
                            p.write_bytes(b)

    canonical = sorted(seen)  # 固定行序：按 sha256 升序

    # ---------------- 第 2 遍：逐文件校验（可选）
    mismatches = 0
    if args.verify or True:
        for sha in canonical if args.verify else []:
            p = store / "images" / sha[:2] / f"{sha}.jpg"
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
                mismatches += 1

    with (store / "occurrences.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("qid,role,rank,sha256\n")
        for qid, role, rank, sha in occ_rows:
            f.write(f"{qid},{role},{rank},{sha}\n")

    with (store / "corpus_manifest.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("row,sha256,bytes,w,h,occurrences,first_seen\n")
        for i, sha in enumerate(canonical):
            d = seen[sha]
            f.write(f"{i},{sha},{d['bytes']},{d['w']},{d['h']},{d['occurrences']},{d['first_seen']}\n")

    digest = hashlib.sha256()
    for sha in canonical:
        digest.update(f"{sha}\n".encode())

    roles_count: dict[str, int] = {}
    for _qid, role, _rank, _sha in occ_rows:
        roles_count[role] = roles_count.get(role, 0) + 1

    meta = {
        "corpus_version": CORPUS_VERSION,
        "dataset": {"repo": REPO, "revision": REV, "split": "test", "shards": len(shards)},
        "identity": {
            "rule": "sha256(JPEG q95 re-encode of the parquet struct<bytes>)",
            "why": "沿用既有证据包/审计的身份口径；原始字节也在 parquet 中，raw sha256 可作为附加核对",
            "deterministic": "PIL 12.3.0 下同机多次独立加载结果一致（见 scripts/test_hash_stability.py）",
        },
        "row_order_rule": "sha256 升序（与发现顺序、题目顺序、角色无关）",
        "counts": {
            "questions": len({r[0] for r in occ_rows}),
            "image_instances": len(occ_rows),
            "instances_by_role": roles_count,
            "unique_contents": len(canonical),
            "duplicate_instances": len(occ_rows) - len(canonical),
        },
        "content_digest_sha256": digest.hexdigest(),
        "files": {
            "occurrences.csv": "每个实例 (qid,role,rank) -> sha256",
            "corpus_manifest.csv": "索引行序 row -> sha256（本语料就是候选池本体）",
            "images/": "唯一内容 q95 字节，路径 images/<sha[:2]>/<sha>.jpg",
        },
        "verify": {
            "command": "python scripts/a06_build_corpus.py --verify",
            "mismatches_in_this_run": mismatches,
        },
        "elapsed_seconds": round(time.time() - t0, 1),
        "known_gaps": [
            "已发布 smoke 报告的索引规模 18,955 无法由本数据集的实例数 14,475 或唯一内容数 4,712 复现，需 B 提供索引构建回执",
            "唯一内容 4,712 由 JPEG q95 口径给出；若改用原始字节口径，集合规模相同（互为双射，见 outputs/census/image_census.json）",
        ],
    }
    (store / "corpus_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(meta["counts"], indent=2, ensure_ascii=False))
    print(f"content_digest={meta['content_digest_sha256']}")
    print(f"耗时 {meta['elapsed_seconds']}s  -> {store}")
    if args.verify:
        print(f"校验不一致文件数 = {mismatches}")
        return 0 if mismatches == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
