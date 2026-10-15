"""把重资源迁移到工作区之外,控制工作区体积。

**为什么需要这个脚本**

本项目合法的磁盘需求超过 35 GiB:模型权重约 26 GiB(EmbeddingGemma 2 + Gemma 4 E2B/E4B)、
两个虚拟环境各约 4.8 GiB(每个都含一份约 2.8 GiB 的 CUDA torch)。这些都**可重新生成**,
不属于需要随代码版本管理的产物,因此不应占用工作区。

迁移后的布局:

    工作区 (C:\\...\\Desktop\\1\\EdgeCoRAG-A)          约 0.2 GiB  仅脚本/代码/论文/结果
      ├── scripts/  docs/  reports/  papers/  third_party/
      ├── .venv-main  ->  junction  ->
      └── .venv-mrag  ->  junction  ->

    外部存储 (E:\\EdgeCoRAG-A-store)                  约 36 GiB
      ├── hf-cache/   HuggingFace 权重缓存(25.9 GiB)
      └── venvs/      两个虚拟环境(9.5 GiB)

用 **junction(目录联接)** 而不是移动后改路径:junction 对进程完全透明,
`HF_HOME`、虚拟环境里写死的 `pyvenv.cfg`/shebang 路径都无需修改,原命令照常可用。

用法:
    python scripts/bootstrap_store.py --check     # 只检查当前状态
    python scripts/bootstrap_store.py --apply     # 执行迁移(幂等,可重复运行)

执行前请确认没有正在运行的 Python 进程占用这些目录。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

ROOT = cfg.ROOT
STORE = cfg.store_root()


def dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def gib(n: int) -> str:
    return f"{n / 1024 ** 3:.2f} GiB"


def is_junction(p: Path) -> bool:
    if not p.exists():
        return False
    try:
        return bool(p.is_symlink()) or (hasattr(p, "is_junction") and p.is_junction())
    except OSError:
        return False


def link_target(p: Path) -> str:
    try:
        out = subprocess.run(["cmd", "/c", "dir", "/AL", str(p.parent)],
                             capture_output=True, text=True, errors="replace").stdout
        for line in out.splitlines():
            if p.name in line and ("<JUNCTION>" in line or "<SYMLINKD>" in line):
                parts = line.split("]")
                if len(parts) >= 2:
                    return parts[-2].split("[")[-1]
    except Exception:  # noqa: BLE001
        pass
    return "?"


def move_and_link(src: Path, dst: Path) -> bool:
    """把 src 移到 dst,并在原位置建立 junction。"""
    if is_junction(src):
        print(f"  · {src.name} 已是链接,跳过")
        return True
    if not src.exists():
        print(f"  · {src.name} 不存在,跳过")
        return True
    if dst.exists() and any(dst.iterdir()):
        print(f"  ! 目标已存在且有内容: {dst} —— 请人工确认后处理")
        return False

    size = dir_size(src)
    print(f"  移动 {src.name} ({gib(size)}) -> {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # robocopy /MOVE 在同一卷内是重命名,跨卷才真复制;比 shutil.move 更能保留 ACL
    r = subprocess.run(["robocopy", str(src), str(dst), "/E", "/MOVE",
                        "/NFL", "/NDL", "/NJH", "/NJS", "/R:1", "/W:1"],
                       capture_output=True, text=True)
    if r.returncode > 7:
        print(f"  ✗ robocopy 失败 exit={r.returncode}")
        return False
    if src.exists():
        shutil.rmtree(src, ignore_errors=True)
    m = subprocess.run(["cmd", "/c", "mklink", "/J", str(src), str(dst)],
                       capture_output=True, text=True)
    if m.returncode != 0:
        print(f"  ✗ 建立 junction 失败: {m.stderr.strip() or m.stdout.strip()}")
        return False
    print(f"  ✅ {src.name} -> {dst}")
    return True


TARGETS = [
    ("模型权重缓存", ROOT / "models", STORE / "hf-cache"),
    ("虚拟环境 .venv-main", ROOT / ".venv-main", STORE / "venvs" / "venv-main"),
    ("虚拟环境 .venv-mrag", ROOT / ".venv-mrag", STORE / "venvs" / "venv-mrag"),
]


def report() -> None:
    print(f"工作区 : {ROOT}")
    print(f"外部存储: {STORE}  (存在={STORE.exists()})\n")
    total_ws = 0
    for label, src, dst in TARGETS:
        j = is_junction(src)
        if j:
            tag = f"junction -> {link_target(src)}"
        elif not src.exists() and dst.exists():
            # 已迁出但未建链接(例如 HF 缓存靠 HF_HOME 环境变量指向外部)
            tag = f"{gib(dir_size(dst))} (在工作区外: {dst})"
        else:
            tag = f"{gib(dir_size(src))} (在工作区内)"
        if not j:
            total_ws += dir_size(src)
        print(f"  {label:22s} {tag}")
    other = sum(dir_size(ROOT / d) for d in
                ("scripts", "docs", "reports", "papers", "third_party", "tools", "outputs")
                if (ROOT / d).exists())
    print(f"\n  工作区实际占用: {gib(total_ws + other)}")
    print(f"  外部存储占用  : {gib(dir_size(STORE))}")
    print(f"\n  HF 缓存路径   : {cfg.hf_home()}")
    print(f"  HF 镜像       : {cfg.HF_MIRROR}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查状态")
    ap.add_argument("--apply", action="store_true", help="执行迁移")
    args = ap.parse_args()

    if args.check or not args.apply:
        report()
        if not args.apply:
            print("\n(加 --apply 执行迁移)")
        return 0

    # 安全检查: 不能有 python 进程在跑,否则文件被占用
    ps = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                        capture_output=True, text=True, errors="replace").stdout
    if "python.exe" in ps:
        print("⚠️ 检测到正在运行的 python.exe,可能占用虚拟环境文件。")
        print("   请先结束这些进程再执行迁移。")
        print(ps)
        return 1

    print(f"外部存储: {STORE}\n")
    ok = True
    for label, src, dst in TARGETS:
        print(f"[{label}]")
        ok &= move_and_link(src, dst)
    print()
    report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
