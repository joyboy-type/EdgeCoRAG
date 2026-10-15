"""配置复现实验的 Python 环境（项目内自包含,不污染系统 Python）。

用法:
    python scripts/setup_env.py --list
    python scripts/setup_env.py main                  # CUDA torch + 模型库
    python scripts/setup_env.py mrag                  # 作者代码复现环境(Transformers 4.x)
    python scripts/setup_env.py all

环境划分依据(任务书第 3/4 节 + 本机实测):
    main  = torch(CUDA) + transformers 5.x + sentence-transformers
            -> EmbeddingGemma 2 图文检索、Gemma 4 生成
    mrag  = torch(CUDA) + transformers 4.x
            -> utility-mrag 作者代码(其环境锁定 4.x,不得与 5.x 混装)

所有模型下载请先设置 HF_ENDPOINT=https://hf-mirror.com
(huggingface.co 在本机 DNS 被污染,直连超时)。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import project_config as cfg  # noqa: E402

# torch 2.11.0+cu128 / cp312 / win_amd64 —— 已核对 wheel 真实存在
# 本机驱动 592.00 报告 CUDA Version 13.1,故 cu128 在支持范围内
#
# 镜像与路径统一从 scripts/project_config.py 取,避免多处写死。
# 镜像速度实测见 scripts/probe_mirrors.py: SJTU 13.31 MB/s > 官方 8.51 MB/s。
TORCH_INDEXES = cfg.TORCH_INDEXES
TORCH_PKGS = ["torch==2.11.0", "torchvision==0.26.0"]
PYPI_INDEX = cfg.PYPI_INDEX
HF_ENDPOINT = cfg.HF_MIRROR
# 模型缓存位于**工作区之外**(默认 E:\EdgeCoRAG-A-store\hf-cache),避免工作区膨胀。
HF_HOME = cfg.hf_home()

ENVS: dict[str, dict] = {
    "main": {
        "desc": "EmbeddingGemma 2 图文检索 + Gemma 4 生成 (transformers 5.x)",
        # 注意: 此处不再钉死 huggingface-hub 版本。
        # sentence-transformers 6.1.0 要求 huggingface-hub<2.0.0,>=1.3.0,
        # 与 huggingface-hub==2.2.0 冲突(pip ResolutionImpossible),交由解析器决定。
        # 同样不再写 torch==2.11.0: 已装的是 +cu128 本地版本,写死版本号会让 pip
        # 去 PyPI 重新下载 CPU 轮子覆盖 CUDA 构建。
        "install": [
            "numpy", "pillow", "requests",
            "transformers==5.19.0",
            "sentence-transformers==6.1.0",
            "accelerate==1.15.0",
            "datasets==5.1.0",
            "pypdf",
        ],
    },
    "mrag": {
        "desc": "utility-mrag 作者代码复现 (transformers 4.x,与其锁版一致)",
        # 包清单逐条对齐第三方 pyproject.toml 的 [project].dependencies。
        # 该仓库的注释明确写道:
        #   "Qwen3-VL needs >=4.57; the Ovis 2.5 / MiniCPM-V remote code targets
        #    the 4.x API (transformers 5.x removed attributes it relies on),
        #    so cap below 5."
        # => transformers 必须 <5,这正是必须与 .venv-main 分开的原因。
        "install": [
            "numpy", "pillow", "requests",
            "transformers>=4.57,<5",
            "accelerate>=0.30",
            "pandas>=2.0",
            "tqdm>=4.65",
            "pyyaml>=6.0",
            "jsonlines>=4.0",
            "scikit-learn>=1.3",
            "sentencepiece>=0.1.99",   # SigLIP baseline / Gemma 3 的 SentencePiece 分词器需要
            "protobuf>=3.20",
            "datasets>=2.18",          # --extra datasets
            "pytest>=7.4",             # --extra dev
            "pypdf",
        ],
    },
}


def venv_python(env: str) -> Path:
    return ROOT / f".venv-{env}" / "Scripts" / "python.exe"


def run(cmd: list[str], *, env: dict | None = None, check: bool = True) -> int:
    printable = " ".join(cmd)
    print(f"\n$ {printable}", flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, env=env, text=True)
    print(f"  -> exit={r.returncode} 用时 {time.time() - t0:.0f}s", flush=True)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败: {printable}")
    return r.returncode


def ensure_venv(env: str) -> Path:
    py = venv_python(env)
    if py.exists():
        print(f"[{env}] 虚拟环境已存在: {py.parent.parent}")
        return py
    print(f"[{env}] 创建虚拟环境 {ROOT / f'.venv-{env}'}")
    run([sys.executable, "-m", "venv", str(ROOT / f".venv-{env}")])
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    return py


def setup(env: str) -> None:
    spec = ENVS[env]
    print(f"\n{'=' * 72}\n[{env}] {spec['desc']}\n{'=' * 72}")
    py = ensure_venv(env)

    child_env = os.environ.copy()
    child_env["HF_ENDPOINT"] = HF_ENDPOINT
    # 模型与数据集缓存放在**工作区之外**(见 scripts/project_config.py),
    # 默认 E:\EdgeCoRAG-A-store\hf-cache。工作区内只保留脚本与轻量产物。
    child_env["HF_HOME"] = str(HF_HOME)
    child_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    child_env["PYTHONUTF8"] = "1"
    child_env["PIP_DEFAULT_TIMEOUT"] = "60"   # 大轮子在慢链路上需要更长超时
    child_env["PIP_RETRIES"] = "5"

    # 1) CUDA 版 torch：按实测速度依次尝试镜像，避免慢源拖死整个安装
    print(f"\n[{env}] 安装 CUDA torch（按实测速度依次尝试镜像）")
    ok = False
    for name, index in TORCH_INDEXES:
        print(f"\n[{env}] 尝试镜像: {name} -> {index}")
        rc = run([str(py), "-m", "pip", "install", "--index-url", index] + TORCH_PKGS,
                 env=child_env, check=False)
        if rc == 0:
            print(f"[{env}] torch 安装成功（源: {name}）")
            ok = True
            break
        print(f"[{env}] 源 {name} 失败(exit={rc})，换下一个镜像")
    if not ok:
        raise SystemExit(f"[{env}] 所有 torch 镜像均失败，请检查网络或改用离线轮子")

    # 2) 其余依赖走 PyPI 镜像,失败回退官方源
    print(f"\n[{env}] 安装其余依赖（PyPI 镜像）")
    rc = run([str(py), "-m", "pip", "install", "--index-url", PYPI_INDEX] + spec["install"],
             env=child_env, check=False)
    if rc != 0:
        print(f"[{env}] PyPI 镜像失败，回退官方源")
        run([str(py), "-m", "pip", "install"] + spec["install"], env=child_env)

    # 3) 验收
    print(f"\n[{env}] 验收")
    code = (
        "import torch, sys;"
        "print('python', sys.version.split()[0]);"
        "print('torch', torch.__version__);"
        "print('cuda_available', torch.cuda.is_available());"
        "print('cuda_version', torch.version.cuda);"
        "print('bf16_supported', torch.cuda.is_bf16_supported() if torch.cuda.is_available() else None);"
        "print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU-ONLY!');"
        "print('vram_total_GB', round(torch.cuda.get_device_properties(0).total_memory/1024**3,2) if torch.cuda.is_available() else None)"
    )
    run([str(py), "-c", code], env=child_env, check=False)

    # 4) 冻结环境
    locked = ROOT / "reports" / f"requirements-{env}.lock.txt"
    locked.parent.mkdir(parents=True, exist_ok=True)
    with locked.open("w", encoding="utf-8") as fh:
        subprocess.run([str(py), "-m", "pip", "freeze"], stdout=fh, text=True)
    print(f"[{env}] 冻结清单 -> {locked}")
    print(f"[{env}] 完成。使用方式: {py}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", choices=[*ENVS, "all"], default="main")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, v in ENVS.items():
            print(f"{k:6s} {v['desc']}\n       索引: {v['index']}\n       包: {', '.join(v['install'])}")
        return 0

    targets = list(ENVS) if args.target == "all" else [args.target]
    for t in targets:
        setup(t)
    print("\n全部完成。提醒: 模型下载请设 HF_ENDPOINT=" + HF_ENDPOINT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
