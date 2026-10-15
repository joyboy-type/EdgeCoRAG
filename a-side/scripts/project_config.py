"""项目共享配置:缓存位置、镜像地址、环境约束。

**为什么缓存放在工作区之外**

模型权重合计约 26 GiB(E2B 9.57 + E4B 14.92 + EmbeddingGemma 2 1.42),
且**全部可重新下载**,不属于需要版本管理的产物。放在工作区内会让工作区膨胀到 35 GiB 以上。
因此权重缓存统一放在工作区之外的大容量分区,工作区内只保留脚本与轻量产物。

缓存位置解析优先级:
    1. 环境变量 EDGECORAG_STORE      (便于整盘迁移)
    2. 环境变量 HF_HOME              (遵循 HuggingFace 约定)
    3. 默认 E:\\EdgeCoRAG-A-store\\hf-cache

若目标位置不存在(例如换机器),自动回退到 `~/.cache/huggingface`,
保证脚本不会因为路径缺失而失败。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_STORE = Path(r"E:\EdgeCoRAG-A-store")
FALLBACK_STORE = Path.home() / ".cache" / "edgecorag-a-store"


def store_root() -> Path:
    """重资源(模型权重等)的存放根目录。"""
    env = os.environ.get("EDGECORAG_STORE")
    if env:
        return Path(env)
    if DEFAULT_STORE.exists():
        return DEFAULT_STORE
    return FALLBACK_STORE


def hf_home() -> Path:
    """HuggingFace 缓存目录。

    尊重已有的 HF_HOME(用户在外部显式设置时),否则用 store_root()/hf-cache。
    """
    env = os.environ.get("HF_HOME")
    if env:
        return Path(env)
    return store_root() / "hf-cache"


# ---------------------------------------------------------------- 镜像
# 本机实测: huggingface.co 的 DNS 被污染(解析到 88.191.249.183 / Facebook 段 IPv6),
# 直连超时;hf-mirror.com 可用。
HF_MIRROR = "https://hf-mirror.com"

# torch CUDA 轮子镜像(按实测速度排序,见 scripts/probe_mirrors.py)
TORCH_INDEXES = [
    ("上海交大 SJTU", "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128"),
    ("pytorch 官方", "https://download.pytorch.org/whl/cu128"),
]

# PyPI 镜像
PYPI_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

# ---------------------------------------------------------------- 模型
MODELS: dict[str, dict] = {
    "embeddinggemma": {
        "repo": "google/embeddinggemma-2",
        "desc": "EmbeddingGemma 2 图文嵌入(检索基线/A-P0-2 必需)",
        "approx_gb": 1.42,
    },
    "e2b": {
        "repo": "google/gemma-4-E2B-it",
        "desc": "Gemma 4 E2B IT(路径 A0/A1 生成模型;4bit 实测 6.28 GiB 可驻留)",
        "approx_gb": 9.57,
    },
    "e4b": {
        "repo": "google/gemma-4-E4B-it",
        "desc": "Gemma 4 E4B IT(路径 A2/A3;4bit 实测 8.685 GiB 超出 8 GB 显存,本机不可行)",
        "approx_gb": 14.92,
    },
}


def apply_env() -> None:
    """把镜像与缓存设置写入当前进程环境。

    **必须在 import huggingface_hub / transformers 之前调用。**
    """
    os.environ["HF_ENDPOINT"] = HF_MIRROR
    os.environ["HF_HOME"] = str(hf_home())
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


if __name__ == "__main__":
    print(f"ROOT        : {ROOT}")
    print(f"store_root  : {store_root()}   (存在={store_root().exists()})")
    print(f"hf_home     : {hf_home()}   (存在={hf_home().exists()})")
    print(f"HF_ENDPOINT : {HF_MIRROR}")
