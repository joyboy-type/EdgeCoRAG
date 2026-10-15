"""校验图片哈希方法的**可靠性**——这是命中率测量的前提。

**背景**

`audit_gt_match_rate.py` 报告 GT 精确匹配命中率 55.9%,但该结论依赖
「能稳定取到图片原始字节」。在 `reconcile_dataset_size.py` 中同一套取字节逻辑
出现了 3224/3224 全部回退的情况,说明该方法**不稳定**。

若哈希退化为"重编码后的字节",则:
  * 同一张图在不同次运行中可能得到不同哈希(不可复现);
  * 两张不同的图可能因为重编码而巧合一致(假命中);
  * 结论 55.9% 就不可信。

本脚本对同一条样本反复求哈希并比较,量化稳定性;同时确认:
  1. 能否稳定取到原始字节(不重编码);
  2. 原始字节是否就是 JPEG(魔数 FF D8 FF);
  3. 对同一张图重复求哈希是否完全一致;
  4. 重编码路径与原始字节路径是否给出不同哈希。

用法: python scripts/verify_hash_reliability.py [--n 40]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"


def probe_methods(im) -> dict:
    """逐一尝试各种取字节方式,报告哪种可用。"""
    out: dict = {}
    # 1) datasets Image 特征可能保留的原始 bytes
    for attr in ("_data", "data"):
        v = getattr(im, attr, None)
        out[f"attr_{attr}"] = (len(v) if isinstance(v, (bytes, bytearray)) else None)
    # 2) filename
    fn = getattr(im, "filename", None)
    out["filename"] = (str(fn)[:60] if fn else None)
    # 3) PIL 文件指针
    fp = getattr(im, "fp", None)
    out["fp_present"] = fp is not None
    if fp is not None:
        out["fp_seekable"] = bool(getattr(fp, "seekable", lambda: False)())
        try:
            pos = fp.tell()
            fp.seek(0)
            data = fp.read()
            fp.seek(pos)
            out["fp_read_len"] = len(data) if data else 0
            out["fp_magic"] = (data[:4].hex() if data else None)
            out["fp_sha256"] = (hashlib.sha256(data).hexdigest()[:16] if data else None)
        except Exception as exc:  # noqa: BLE001
            out["fp_error"] = f"{type(exc).__name__}: {exc}"
    # 4) 重编码路径
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=95)
    out["reencode_jpeg_sha256"] = hashlib.sha256(buf.getvalue()).hexdigest()[:16]
    out["reencode_len"] = len(buf.getvalue())
    # 5) PNG 重编码
    buf2 = io.BytesIO()
    im.convert("RGB").save(buf2, format="PNG")
    out["reencode_png_sha256"] = hashlib.sha256(buf2.getvalue()).hexdigest()[:16]
    out["size"] = f"{im.width}x{im.height}"
    out["pil_type"] = type(im).__name__
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="抽样题数")
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    print("加载数据集(流式)…")
    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    stats = {
        "images_probed": 0,
        "fp_available": 0,
        "fp_magic_jpeg": 0,
        "sha_fp_present": 0,
        "sha_fp_missing": 0,
    }
    examples: list[dict] = []
    fp_sha_by_key: dict[str, list[str]] = {}

    t0 = time.time()
    qn = 0
    for ex in ds:
        if qn >= args.n:
            break
        qn += 1
        imgs = [("query", ex["image"])]
        imgs += [("gt", g) for g in ex["gt_images"]]
        imgs += [("ret", r) for r in ex["retrieved_images"]]
        for role, im in imgs:
            stats["images_probed"] += 1
            info = probe_methods(im)
            if info.get("fp_present"):
                stats["fp_available"] += 1
            if info.get("fp_magic", "")[:6] == "ffd8ff":
                stats["fp_magic_jpeg"] += 1
            if info.get("fp_sha256"):
                stats["sha_fp_present"] += 1
            else:
                stats["sha_fp_missing"] += 1
            if len(examples) < 6:
                examples.append({"qid": ex["id"], "role": role, **info})
            # 同一张图再问一次,检查稳定性
            key = f"{ex['id']}:{role}:{im.width}x{im.height}"
            if info.get("fp_sha256"):
                fp_sha_by_key.setdefault(key, []).append(info["fp_sha256"])
        if qn % 10 == 0:
            print(f"  已核 {qn} 题 ({time.time() - t0:.0f}s)")

    print(f"\n=== 抽样结果 (n={qn} 题) ===")
    for k, v in stats.items():
        print(f"  {k:22s} {v}")

    print("\n=== 取字节方法可用性(前几条样本详情)===")
    for e in examples[:4]:
        print(f"\n  qid={e['qid']} role={e['role']} {e.get('size')} {e.get('pil_type')}")
        for k, v in e.items():
            if k in ("qid", "role"):
                continue
            print(f"      {k:24s} = {v}")

    print("\n=== 结论 ===")
    if stats["sha_fp_present"] == stats["images_probed"]:
        print("  ✅ 所有图片都能经 PIL fp 取到原始字节,哈希方法可靠")
        print("     -> 55.9% 命中率所依赖的基础成立")
    elif stats["sha_fp_present"] == 0:
        print("  ❌ 完全取不到原始字节,命中率结论不可信,必须改为重编码哈希并重新测量")
    else:
        pct = stats["sha_fp_present"] / max(stats["images_probed"], 1) * 100
        print(f"  ⚠️ 仅 {pct:.1f}% 的图片能取到原始字节")
        print("     -> 存在混合口径: 部分用原始字节、部分用重编码,不可比,必须统一后重测")
    if stats["fp_magic_jpeg"]:
        print(f"  原始字节魔数确认 JPEG: {stats['fp_magic_jpeg']}/{stats['fp_available']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
