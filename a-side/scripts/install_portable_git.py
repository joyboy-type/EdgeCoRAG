"""下载便携版 MinGit（不写入系统 PATH、不触发 UAC），供 git clone 使用。

用法:
    python scripts/install_portable_git.py
    python scripts/install_portable_git.py --check

产物: tools/mingit/cmd/git.exe
脚本会自动把该目录加入当前进程 PATH 的提示方式打印出来;
acquire_sources.py 通过 tools/mingit/cmd 探测 git。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DEST = TOOLS / "mingit"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/vnd.github+json"}


def find_git() -> str | None:
    """返回可用的 git 可执行文件路径。"""
    exe = DEST / "cmd" / "git.exe"
    if exe.exists():
        return str(exe)
    return shutil.which("git")


def latest_mingit_url() -> str:
    """从 GitHub Releases API 找 MinGit 的 64 位 zip 资产。"""
    api = "https://api.github.com/repos/git-for-windows/git/releases/latest"
    r = requests.get(api, headers=UA, timeout=60)
    r.raise_for_status()
    rel = r.json()
    tag = rel.get("tag_name", "?")
    candidates = []
    for asset in rel.get("assets", []):
        name = asset["name"]
        if name.startswith("MinGit-") and "64-bit" in name and name.endswith(".zip") \
                and "busybox" not in name:
            candidates.append((asset["name"], asset["browser_download_url"], asset["size"]))
    if not candidates:
        raise RuntimeError(f"release {tag} 中未找到 MinGit 64-bit zip")
    # 选体积最大的（通常是完整版）
    candidates.sort(key=lambda x: -x[2])
    print(f"release {tag} 候选:")
    for n, _, s in candidates:
        print(f"  {n}  ({s / 1024 / 1024:.1f} MB)")
    return candidates[0][1]


def install() -> int:
    if find_git():
        print(f"git 已可用: {find_git()}")
        return 0

    url = latest_mingit_url()
    print(f"\n下载 {url}")
    r = requests.get(url, headers={"User-Agent": UA["User-Agent"]}, timeout=600, stream=True)
    r.raise_for_status()
    total = int(r.headers.get("Content-Length", 0))
    buf = io.BytesIO()
    got = 0
    for chunk in r.iter_content(1 << 20):
        buf.write(chunk)
        got += len(chunk)
        if total:
            print(f"\r  {got / 1e6:.1f}/{total / 1e6:.1f} MB", end="", flush=True)
    print()

    TOOLS.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    print(f"解压到 {DEST}")
    with zipfile.ZipFile(buf) as zf:
        zf.extractall(DEST)

    print("清理不必要的文档以缩小体积")
    for junk in ("mingw64/share/doc", "mingw64/share/man", "mingw64/share/gitweb"):
        p = DEST / junk
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    git = find_git()
    if not git:
        print("解压后仍未找到 git.exe,请检查产物结构")
        return 1
    print(f"\ngit 就绪: {git}")
    v = subprocess.run([git, "--version"], capture_output=True, text=True)
    print(f"版本: {v.stdout.strip() or v.stderr.strip()}")
    print(f"\n脚本内使用方式: 把 {DEST / 'cmd'} 前置到 PATH")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查是否已有 git")
    args = ap.parse_args()
    if args.check:
        g = find_git()
        print(f"git: {g or '不可用'}")
        return 0 if g else 1
    return install()


if __name__ == "__main__":
    sys.exit(main())
