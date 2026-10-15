"""确定 MRAG-Bench 图片到底能否取到原始字节,并选定**唯一**的哈希口径。

背景: `verify_hash_reliability.py` 显示 `im.fp` 不存在,而 `raw_bytes()` 里
有 fp 分支 -> 说明历史测量的哈希实际来自重编码路径。本脚本把候选方法列全,
逐一实测并给出唯一可用、可复现的口径。

用法: python scripts/determine_hash_method.py [--n 5]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def try_methods(im) -> dict:
    r: dict = {"dir_attrs": [a for a in dir(im) if "fp" in a.lower() or "data" in a.lower()]}
    # A) ImageFile 的私有 _data / data
    for a in ("_data", "data", "tobytes"):
        v = getattr(im, a, None)
        r[f"A_{a}"] = type(v).__name__ if v is not None else None
    # B) fp
    r["B_has_fp"] = hasattr(im, "fp")
    fp = getattr(im, "fp", None)
    r["B_fp_type"] = type(fp).__name__ if fp is not None else None
    # C) 尝试 getattr im.fp 后读取
    if fp is not None:
        try:
            r["C_fp_readable"] = hasattr(fp, "read")
            if hasattr(fp, "read"):
                pos = fp.tell() if hasattr(fp, "tell") else None
                if hasattr(fp, "seek"):
                    fp.seek(0)
                d = fp.read()
                r["C_len"] = len(d) if d else 0
                r["C_magic"] = d[:4].hex() if d else None
                r["C_sha"] = sha(d)[:16] if d else None
                if pos is not None and hasattr(fp, "seek"):
                    fp.seek(pos)
        except Exception as e:  # noqa: BLE001
            r["C_err"] = f"{type(e).__name__}: {e}"
    # D) 有些版本把原始字节放在 im.data（dict 形式）
    d2 = getattr(im, "data", None)
    if isinstance(d2, dict):
        r["D_dict_keys"] = list(d2.keys())[:5]
    # E) 重编码 JPEG
    b1 = io.BytesIO(); im.convert("RGB").save(b1, format="JPEG", quality=95)
    r["E_jpeg95_sha"] = sha(b1.getvalue())[:16]
    r["E_jpeg95_len"] = len(b1.getvalue())
    # F) 重编码 PNG
    b2 = io.BytesIO(); im.convert("RGB").save(b2, format="PNG")
    r["F_png_sha"] = sha(b2.getvalue())[:16]
    r["F_png_len"] = len(b2.getvalue())
    # G) 重编码 JPEG 无损(quality=100, subsampling=0)
    b3 = io.BytesIO(); im.convert("RGB").save(b3, format="JPEG", quality=100, subsampling=0)
    r["G_jpeg100_sha"] = sha(b3.getvalue())[:16]
    r["G_jpeg100_len"] = len(b3.getvalue())
    # 稳定性: 同一方法连续两次
    b4 = io.BytesIO(); im.convert("RGB").save(b4, format="PNG")
    r["F_png_sha_2nd"] = sha(b4.getvalue())[:16]
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)
    for i, ex in enumerate(ds):
        if i >= args.n:
            break
        print(f"\n{'=' * 74}\nqid={ex['id']}  scenario={ex['scenario']}\n{'=' * 74}")
        for role, im in [("query", ex["image"])] + [("gt", g) for g in ex["gt_images"][:2]]:
            print(f"\n  [{role}] {im.width}x{im.height} {type(im).__name__}")
            for k, v in try_methods(im).items():
                print(f"      {k:18s} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
