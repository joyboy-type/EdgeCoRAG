"""核对交接包样例文件: 文件名、真实容器格式、字节数与索引哈希是否自洽。

**为什么需要它**

出现过一次口径混乱: `raw_bytes()` 声称"取原始字节",实际走的是重编码回退分支
(因为 `im.fp` 为 None)。这导致:
  * 索引里记录的 sha256 可能是 PNG 重编码的哈希;
  * 而落盘文件可能是 JPEG 重编码的字节;
  * 二者不一致 -> 哈希校验失去意义。

本脚本按**魔数**判断每个文件的真实容器格式,重算 sha256 并与 `evidence_index.csv`
比对,逐条报告是否自洽。这是第四部分"验证脚本及实际输出"的一部分。

用法: python scripts/verify_sample_files.py [--dir <样例目录>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

DEFAULT = cfg.ROOT.parent / "EdgeCoRAG-B-handover" / "samples"

MAGIC = [
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"RIFF", "webp"),
    (b"BM", "bmp"),
]


def sniff(b: bytes) -> str:
    for m, name in MAGIC:
        if b.startswith(m):
            return name
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT)
    args = ap.parse_args()
    base: Path = args.dir

    print(f"样例目录: {base}\n")
    idx_csv = base / "evidence_index.csv"
    if not idx_csv.exists():
        print(f"✗ 找不到 {idx_csv}")
        return 1

    with idx_csv.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    print(f"索引条目: {len(rows)}\n")

    print("=== 逐文件核对(格式 / 字节 / 哈希)===")
    print(f"  {'evidence_id':38s} {'ext':5s} {'real':6s} {'bytes':>9s} {'hash':>6s}")
    n_mismatch_ext = n_mismatch_hash = n_missing = 0
    for r in rows:
        p = base / r["path"]
        if not p.exists():
            print(f"  {r['evidence_id']:38s} MISSING  {r['path']}")
            n_missing += 1
            continue
        b = p.read_bytes()
        real = sniff(b)
        ext = p.suffix.lstrip(".").lower()
        ext_norm = {"jpg": "jpeg"}.get(ext, ext)
        sha = hashlib.sha256(b).hexdigest()
        ok_ext = (ext_norm == real)
        ok_hash = (sha == r["sha256"])
        if not ok_ext:
            n_mismatch_ext += 1
        if not ok_hash:
            n_mismatch_hash += 1
        print(f"  {r['evidence_id']:38s} {ext:5s} {real:6s} {len(b):9,d} "
              f"{'✅' if ok_hash else '❌':>6s}"
              + ("" if ok_ext else f"   ⚠️ 扩展名与内容不符"))

    print(f"\n=== 汇总 ===")
    print(f"  条目总数            : {len(rows)}")
    print(f"  文件缺失            : {n_missing}")
    print(f"  扩展名与内容不符    : {n_mismatch_ext}")
    print(f"  哈希与索引不符      : {n_mismatch_hash}")

    # 结论 + 处置建议
    print(f"\n=== 结论 ===")
    if n_missing == 0 and n_mismatch_ext == 0 and n_mismatch_hash == 0:
        print("  ✅ 自洽: 文件名、容器格式、字节数、哈希全部一致")
        verdict = "consistent"
    else:
        print("  ❌ 不自洽,需要修正后再交付。")
        if n_mismatch_hash:
            print("     哈希不一致意味着索引无法用于跨版本校验 —— 必须重新生成索引。")
        if n_mismatch_ext:
            print("     扩展名与内容不符会误导下游解码 —— 必须改为正确扩展名。")
        verdict = "inconsistent"

    out = cfg.ROOT / "outputs" / "handover_verify" / "sample_files_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "script": "scripts/verify_sample_files.py",
        "dir": str(base),
        "entries": len(rows),
        "missing": n_missing,
        "extension_content_mismatch": n_mismatch_ext,
        "hash_mismatch": n_mismatch_hash,
        "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out}")
    return 0 if verdict == "consistent" else 1


if __name__ == "__main__":
    sys.exit(main())
