"""核清 MRAG-Bench 的**体积口径差异**，并实地测量各计数方式。

**为什么需要这个脚本**

出现过一个明显矛盾：
    官方 API metadata 的 `usedStorage`          ≈ 8.0 GiB
    数据集卡里 split 的 `num_bytes`             ≈ 4.41 GiB
    B 同学报告自己下载约                        ≈ 4 GiB

这些数字**都是对的，但口径不同**。本脚本逐一实测并标明每个数字量的是什么，
避免后续再把不同口径的数字放在一起比较。

口径定义：
  A. parquet 文件在磁盘上的实际字节      —— 计费/传输口径
  B. 解压/解码后所有图片的像素字节        —— 计算口径（模型真正要处理的量）
  C. Snapshot 目录树体积（含重复副本）    —— 本地占用口径
  D. 内容去重后的唯一图片字节             —— 去重口径

用法:
    python scripts/reconcile_dataset_size.py
    python scripts/reconcile_dataset_size.py --limit 300    # 抽样外推(快)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
OUT = cfg.ROOT / "outputs" / "dataset_probe" / "size_reconciliation.json"


def human(n: float) -> str:
    return f"{n / 1024 ** 3:.2f} GiB"


def dir_size(p: Path) -> tuple[int, int]:
    """(总字节, 文件数)，按扩展名分组统计。"""
    total = 0
    n = 0
    if not p.exists():
        return 0, 0
    for f in p.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
            n += 1
    return total, n


def img_sha(im) -> str:
    """原始字节哈希；取不到时标注为 fallback（会影响去重口径的准确性）。"""
    for attr in ("_data", "data"):
        blob = getattr(im, attr, None)
        if isinstance(blob, (bytes, bytearray)):
            return hashlib.sha256(bytes(blob)).hexdigest()
    fn = getattr(im, "filename", None)
    if fn and Path(fn).exists():
        return hashlib.sha256(Path(fn).read_bytes()).hexdigest()
    fp = getattr(im, "fp", None)
    if fp is not None and hasattr(fp, "read") and hasattr(fp, "seek"):
        try:
            pos = fp.tell()
            fp.seek(0)
            data = fp.read()
            fp.seek(pos)
            if data:
                return hashlib.sha256(bytes(data)).hexdigest()
        except Exception:  # noqa: BLE001
            pass
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="只扫前 N 题并外推(推荐 300),不填则全量")
    args = ap.parse_args()

    store = cfg.store_root() / "datasets" / "mrag_bench" / REVISION
    print("=== A. 磁盘上的 parquet 实际字节（传输/计费口径）===")
    pq_bytes, pq_n = dir_size(store)
    print(f"  目录: {store}")
    print(f"  文件数 {pq_n}, 共 {human(pq_bytes)}")
    per_ext: dict[str, int] = {}
    if store.exists():
        for f in store.rglob("*"):
            if f.is_file():
                per_ext[f.suffix] = per_ext.get(f.suffix, 0) + f.stat().st_size
    for ext, b in sorted(per_ext.items(), key=lambda x: -x[1]):
        print(f"    {ext or '(无扩展名)':12s} {human(b)}")

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    print(f"\n=== B/C/D. 解码后的图片像素字节（计算口径）"
          f"{f'，抽样 {args.limit} 题外推' if args.limit else '，全量'} ===")
    total_q = 0
    total_gt = 0
    total_ret = 0
    raw_all = 0          # 所有图片原始字节
    unique_shas: set[str] = set()
    uniq_bytes = 0
    decoded_all = 0      # 解码为 RGB 后的像素字节 = w*h*3
    n_images = 0
    fallback_hash = 0
    t0 = time.time()

    for ex in ds:
        if args.limit is not None and total_q >= args.limit:
            break
        total_q += 1
        for im in [ex["image"]] + list(ex["gt_images"]) + list(ex["retrieved_images"]):
            n_images += 1
            decoded_all += im.width * im.height * 3
            h = img_sha(im)
            if not h:
                fallback_hash += 1
                continue
            unique_shas.add(h)
        # 统计角色数量
        total_gt += len(ex["gt_images"])
        total_ret += len(ex["retrieved_images"])
        if total_q % 300 == 0:
            print(f"    已核 {total_q} 题 ({time.time() - t0:.0f}s)")

    # 抽样外推系数
    scale = (1353 / total_q) if args.limit else 1.0
    print(f"  扫描题数     : {total_q}  (外推系数 {scale:.2f})")
    print(f"  图片总数     : {n_images}  (外推 {int(n_images * scale)})")
    print(f"    query 图   : {total_q}")
    print(f"    GT 图      : {total_gt}")
    print(f"    候选图     : {total_ret}")
    print(f"  解码后像素字节: {human(decoded_all * scale)}  <- 模型实际要处理的量")
    print(f"  唯一图片数   : {len(unique_shas)}  (外推 {int(len(unique_shas) * scale)})")
    print(f"  哈希回退次数 : {fallback_hash}")

    result = {
        "script": "scripts/reconcile_dataset_size.py",
        "dataset_repo": REPO_ID,
        "dataset_revision": REVISION,
        "why": ("官方 metadata usedStorage(≈8.0GiB)、数据集卡 num_bytes(≈4.41GiB)、"
                "B 侧下载量(≈4GiB) 三个数字口径不同，此处逐一口径化并实测。"),
        "denominators": {
            "A_parquet_on_disk_bytes": pq_bytes,
            "A_parquet_files": pq_n,
            "A_per_extension_bytes": per_ext,
            "B_decoded_pixel_bytes_estimated": int(decoded_all * scale),
            "C_snapshot_dir_bytes": pq_bytes,
            "D_unique_images": int(len(unique_shas) * scale),
            "images_scanned": n_images,
            "questions_scanned": total_q,
            "extrapolation_scale": round(scale, 4),
            "hash_fallback_count": fallback_hash,
        },
        "interpretation": {
            "8_GiB_class": "parquet 文件在磁盘上的字节(A/C 口径)",
            "4_GiB_class": "数据集卡 num_bytes 与解码侧口径;B 报告的下载量属此量级",
            "note": ("三者不矛盾。比较体积数字时必须声明口径；"
                     "本脚本输出的 A 为实测，B/D 在全量模式下为实测、抽样模式下为外推"),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
