"""共享路径解析：让 A 侧脚本在"仓库布局"和"本地开发布局"下都能直接跑。

两种布局：
  仓库布局      <repo>/a-side/scripts/aXX.py    → a-side 目录 = <repo>/a-side
  本地开发布局  <workspace>/a-side/scripts/aXX.py（同上）
                <workspace>/scripts/aXX.py       → a-side 目录 = <workspace>/a-side

因此只按"脚本所在目录的祖先里哪个有 retrieval_if_v1 / splits"来判断，不看盘符、不写死绝对路径。

语料与接口目录的优先级统一为：命令行参数 > 环境变量 > 布局推导。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_CORPUS = "EDGECORAG_CORPUS"
ENV_IFACE = "EDGECORAG_IFACE"

IFACE_DIRNAME = "retrieval_if_v1"


def side_root(start: Path | None = None) -> Path:
    """返回 a-side 目录。"""
    here = (start or Path(__file__)).resolve()
    for p in here.parents:
        if (p / IFACE_DIRNAME).is_dir() and (p / "splits").is_dir():
            return p
        if (p / "a-side" / IFACE_DIRNAME).is_dir():
            return p / "a-side"
    for p in here.parents:
        if (p / "a-side" / "splits").is_dir():
            return p / "a-side"
    return here.parent.parent


def iface_root(cli_value: str | None = None) -> Path:
    raw = cli_value or os.environ.get(ENV_IFACE)
    p = Path(raw).expanduser().resolve() if raw else side_root() / IFACE_DIRNAME
    if not (p / "pools").is_dir():
        raise SystemExit(
            f"接口目录 {p} 下找不到 pools/；请用 --iface 或环境变量 {ENV_IFACE} 指定 retrieval_if_v1 目录"
        )
    return p


def corpus_root(cli_value: str | None = None) -> Path:
    raw = cli_value or os.environ.get(ENV_CORPUS)
    if not raw:
        raise SystemExit(
            "缺少语料目录：请用 --corpus <dir> 指定，或设置环境变量 "
            f"{ENV_CORPUS}=<dir>。\n"
            "该目录应由 a06_build_corpus.py 生成，包含 corpus_meta.json、"
            "corpus_manifest.csv、occurrences.csv 与 images/<aa>/<sha>.jpg。"
        )
    p = Path(raw).expanduser().resolve()
    need = ("corpus_meta.json", "corpus_manifest.csv", "occurrences.csv", "images")
    missing = [n for n in need if not (p / n).exists()]
    if missing:
        raise SystemExit(
            f"语料目录 {p} 不完整，缺少 {missing}。\n"
            f"请先运行：python a06_build_corpus.py --store {p}"
        )
    return p


def splits_dir() -> Path:
    return side_root() / "splits"


def reports_dir(stage: str = "next_stage_20261020") -> Path:
    return side_root() / "reports" / stage
