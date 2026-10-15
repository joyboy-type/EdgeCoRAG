"""下载官方模型权重(经 hf-mirror.com)到**工作区之外**的缓存目录。

本机 huggingface.co 的 DNS 被污染,直连不可用,故必须走镜像。
缓存位置由 scripts/project_config.py 统一决定(默认 E:\\EdgeCoRAG-A-store\\hf-cache),
**不再放在工作区内**,以免工作区膨胀到 26 GiB 以上。

用法:
    python scripts/download_models.py --list
    python scripts/download_models.py --model embeddinggemma   # 1.42 GiB
    python scripts/download_models.py --model e2b              # 9.57 GiB
    python scripts/download_models.py --model e4b
    python scripts/download_models.py --all
    python scripts/download_models.py --measure-only           # 统计缓存体积
    python scripts/download_models.py --check                  # 检查本地是否已齐全
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", default=None,
                    choices=list(cfg.MODELS) + ["all"])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--measure-only", action="store_true",
                    help="只统计缓存体积,不下载")
    ap.add_argument("--check", action="store_true",
                    help="检查每个模型是否已在本地缓存")
    args = ap.parse_args()

    hf_home = cfg.hf_home()

    if args.list:
        print(f"镜像   : {cfg.HF_MIRROR}")
        print(f"缓存   : {hf_home}   (工作区之外)")
        print(f"store  : {cfg.store_root()}\n")
        for k, v in cfg.MODELS.items():
            print(f"  {k:16s} {v['repo']:32s} ~{v['approx_gb']:5.2f} GB")
            print(f"  {'':16s} {v['desc']}")
        return 0

    # 环境变量必须在导入 huggingface_hub 之前设置
    cfg.apply_env()

    from huggingface_hub import snapshot_download

    if args.measure_only:
        total = 0
        if hf_home.exists():
            for f in hf_home.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        print(f"缓存体积: {total / 1024 ** 3:.2f} GiB")
        print(f"位置    : {hf_home}")
        return 0

    if args.check:
        print(f"缓存: {hf_home}\n")
        hub = hf_home / "hub"
        for k, v in cfg.MODELS.items():
            d = hub / ("models--" + v["repo"].replace("/", "--"))
            if d.exists():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                print(f"  ✅ {k:16s} {size / 1024 ** 3:6.2f} GiB  {d}")
            else:
                print(f"  ❌ {k:16s} 未下载  ({v['repo']}, 约 {v['approx_gb']} GB)")
        return 0

    wanted = args.model or ["embeddinggemma"]
    if "all" in wanted:
        wanted = list(cfg.MODELS)

    print(f"镜像   : {cfg.HF_MIRROR}")
    print(f"缓存   : {hf_home}   (工作区之外)")
    print(f"计划下载: {', '.join(wanted)}\n")

    for key in wanted:
        spec = cfg.MODELS[key]
        print(f"\n{'=' * 74}\n[{key}] {spec['repo']}  (~{spec['approx_gb']} GB)\n{'=' * 74}")
        t0 = time.time()
        try:
            path = snapshot_download(
                repo_id=spec["repo"],
                allow_patterns=[
                    "*.json", "*.safetensors", "*.model", "*.txt", "*.py",
                    "tokenizer*", "*.tiktoken", "chat_template*",
                ],
                max_workers=8,
            )
            dt = time.time() - t0
            size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
            print(f"[{key}] ✅ 完成 {size / 1024 ** 3:.2f} GiB,用时 {dt:.0f}s")
            print(f"[{key}] 本地路径: {path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{key}] ✗ 下载失败: {type(exc).__name__}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
