"""检验同一张图的字节在**多次独立加载**中是否稳定。

**要回答的问题**

`determine_hash_method.py` 报告 query 图的 PNG 重编码长度 369,844 B,
而交接包里 `q_0.jpg` 只有 118,729 B(JPEG95 的长度),且索引哈希与该 JPEG 文件一致。
两者不可能同时对同一份字节成立,除非**同一张图在不同运行中得到不同编码**。

若字节不稳定,则:
  * 基于哈希的"精确匹配命中率"不可复现;
  * 交接包里的 sha256 无法作为跨版本校验依据。

本脚本对同一题反复独立加载并求哈希,逐次报告容器格式与哈希,量化稳定性。

用法: python scripts/test_hash_stability.py [--repeats 4] [--qid 0]
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


def sniff(b: bytes) -> str:
    for m, n in ((b"\xff\xd8\xff", "jpeg"), (b"\x89PNG\r\n\x1a\n", "png")):
        if b.startswith(m):
            return n
    return "unknown"


def encodings(im) -> dict:
    """对同一 PIL 对象生成多种字节表示,记录格式/长度/哈希。"""
    out = {}
    # 原始(fp)
    fp = getattr(im, "fp", None)
    if fp is not None and hasattr(fp, "read"):
        try:
            pos = fp.tell()
            fp.seek(0)
            d = fp.read()
            fp.seek(pos)
            out["原始(fp)"] = (sniff(d), len(d), hashlib.sha256(d).hexdigest()[:16])
        except Exception as e:  # noqa: BLE001
            out["原始(fp)"] = ("err", 0, str(e)[:40])
    else:
        out["原始(fp)"] = ("不可用", 0, "-")
    for fmt, kw in (("JPEG95", dict(format="JPEG", quality=95)),
                    ("PNG", dict(format="PNG")),
                    ("JPEG100", dict(format="JPEG", quality=100, subsampling=0))):
        b = io.BytesIO()
        im.convert("RGB").save(b, **kw)
        d = b.getvalue()
        out[fmt] = (sniff(d), len(d), hashlib.sha256(d).hexdigest()[:16])
    out["尺寸"] = (f"{im.width}x{im.height}", 0, "-")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--qid", type=str, default="0",
                    help="原始 id,取其 query 图与第一张 GT 图")
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    print(f"对 qid={args.qid} 反复独立加载 {args.repeats} 次\n")
    collected: dict[str, list[tuple[str, int, str]]] = {}

    for run in range(1, args.repeats + 1):
        ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION,
                          cache_dir=str(cfg.hf_home() / "hub"))
        for ex in ds:
            if str(ex["id"]) != args.qid:
                continue
            for tag, im in [("query", ex["image"]), ("gt0", ex["gt_images"][0])]:
                enc = encodings(im)
                for k, v in enc.items():
                    collected.setdefault(f"{tag}/{k}", []).append(v)
            break
        print(f"  第 {run} 次加载完成")

    print(f"\n{'=' * 84}\n各表示在各次加载中的稳定性\n{'=' * 84}")
    print(f"  {'表示':22s} {'格式':8s} {'长度':>10s}  {'哈希(前16)':18s} 稳定?")
    all_stable = True
    for key, vals in collected.items():
        fmts = {v[0] for v in vals}
        lens = {v[1] for v in vals}
        shas = {v[2] for v in vals}
        stable = (len(shas) == 1)
        if not stable and "尺寸" not in key:
            all_stable = False
        f = "/".join(sorted(fmts))
        l = "/".join(str(x) for x in sorted(lens))
        s = "/".join(sorted(shas))
        print(f"  {key:22s} {f:8s} {l:>10s}  {s:18s} {'✅' if stable else '❌ 不稳定'}")

    print(f"\n=== 结论 ===")
    if all_stable:
        print("  ✅ 所有表示在多次加载中哈希一致 —— 哈希口径可复现")
    else:
        print("  ❌ 存在不稳定的表示。若使用这些表示做精确匹配,命中率不可复现。")
        print("     处置: 选定唯一且稳定的口径(见上表稳定行),重算全部哈希并标明。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
