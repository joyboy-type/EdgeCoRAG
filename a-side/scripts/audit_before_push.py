"""推送前的安全与体积审查。

检查:
  1. 是否误入凭证/密钥(git PAT、HF token、私钥、.env)
  2. 是否有超过阈值的文件
  3. 被 .gitignore 排除的目录是否真的没进版本库
  4. 提交内容清单是否符合预期

用法: python scripts/audit_before_push.py [--worktree <路径>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

DEFAULT_WT = cfg.store_root() / "_repo_work"
GIT = cfg.ROOT / "tools" / "mingit" / "cmd" / "git.exe"

# 凭证特征
SECRET_PATTERNS = [
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub PAT (classic, ghp_)"),
    (r"github_pat_[A-Za-z0-9_]{40,}", "GitHub PAT (fine-grained)"),
    (r"gho_[A-Za-z0-9]{30,}", "GitHub OAuth token"),
    (r"hf_[A-Za-z0-9]{30,}", "HuggingFace token"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI-style key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥"),
    (r"x-access-token:[^@\s]+@github\.com", "URL 内嵌 token"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
]

# 不该入库的路径特征
FORBIDDEN_PATHS = [
    (r"(^|/)\.env($|\.)", ".env 文件"),
    (r"\.safetensors$", "模型权重"),
    (r"\.parquet$", "数据集 parquet"),
    (r"\.gguf$", "量化模型"),
    (r"\.(pt|pth)$", "PyTorch 权重"),
    (r"(^|/)id_rsa$|(^|/)id_ed25519$", "SSH 私钥"),
    (r"\.pem$|\.key$", "PEM/KEY 文件"),
    (r"(^|/)\.venv", "虚拟环境"),
    (r"(^|/)__pycache__/", "Python 缓存"),
]

SIZE_LIMIT_MB = 25


def git(*args, cwd: Path):
    r = subprocess.run([str(GIT), "-c", "http.sslVerify=false"] + list(args),
                       cwd=str(cwd), capture_output=True, text=True,
                       errors="replace")
    return r.stdout or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worktree", type=Path, default=DEFAULT_WT)
    args = ap.parse_args()
    wt: Path = args.worktree

    if not (wt / ".git").exists():
        print(f"✗ 不是 git 仓库: {wt}")
        return 1

    files = [l for l in git("ls-files", cwd=wt).splitlines() if l.strip()]
    print(f"仓库: {wt}")
    print(f"已跟踪文件: {len(files)}\n")

    # 安全阀: 仓库为空或读取失败时,绝不能报告"通过"。
    # 实测踩过一次: .git 残留但无效 -> ls-files 返回空 -> 审查误判全部通过。
    if not files:
        chk = subprocess.run([str(GIT), "rev-parse", "--git-dir"], cwd=str(wt),
                             capture_output=True, text=True, errors="replace")
        print("❌ 仓库中没有已跟踪文件,无法完成审查。")
        if chk.returncode != 0:
            print("   原因: 该目录不是有效的 git 仓库(可能是残留的 .git 目录)。")
            print("   处理: 删除该目录后重新克隆。")
        else:
            print("   原因: 有效仓库但尚无已跟踪文件(尚未 add/commit)。")
        return 1

    problems: list[str] = []
    warnings: list[str] = []

    # 1. 凭证扫描
    print("=== 1. 凭证扫描 ===")
    hits = 0
    for rel in files:
        p = wt / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for pat, label in SECRET_PATTERNS:
            if re.search(pat, text):
                print(f"  ❌ {rel}  命中: {label}")
                problems.append(f"{rel}: {label}")
                hits += 1
    if hits == 0:
        print("  ✅ 未发现凭证/密钥特征")

    # 2. 禁止路径
    print("\n=== 2. 禁止入库的路径 ===")
    bad = 0
    for rel in files:
        for pat, label in FORBIDDEN_PATHS:
            if re.search(pat, rel):
                print(f"  ❌ {rel}  ({label})")
                problems.append(f"{rel}: {label}")
                bad += 1
    if bad == 0:
        print("  ✅ 无禁止路径")

    # 3. 体积
    print(f"\n=== 3. 大文件(阈值 {SIZE_LIMIT_MB} MiB)===")
    big = 0
    total = 0
    biggest: list[tuple[int, str]] = []
    for rel in files:
        p = wt / rel
        if not p.is_file():
            continue
        sz = p.stat().st_size
        total += sz
        biggest.append((sz, rel))
        if sz > SIZE_LIMIT_MB * 1024 * 1024:
            print(f"  ⚠️ {rel}  {sz / 1024 ** 2:.1f} MiB")
            warnings.append(f"{rel} 体积 {sz / 1024 ** 2:.1f} MiB")
            big += 1
    if big == 0:
        print(f"  ✅ 无超限文件")
    biggest.sort(reverse=True)
    print(f"\n  总计: {total / 1024 ** 2:.1f} MiB")
    print("  最大的 5 个:")
    for sz, rel in biggest[:5]:
        print(f"    {sz / 1024 ** 2:8.2f} MiB  {rel}")

    # 4. 顶层结构
    print("\n=== 4. 顶层结构 ===")
    tops: dict[str, int] = {}
    for rel in files:
        # 顶层目录取第一段;根目录下的散文件归入 "(根目录)"
        top = rel.split("/")[0] if "/" in rel else "(根目录)"
        tops[top] = tops.get(top, 0) + 1
    for k in sorted(tops, key=lambda x: -tops[x]):
        print(f"  {k:20s} {tops[k]:4d} 个文件")

    # 5. 结论
    print("\n" + "=" * 60)
    if problems:
        print(f"❌ 审查未通过: {len(problems)} 个阻断问题")
        for p in problems[:20]:
            print(f"    - {p}")
        return 1
    if warnings:
        print(f"⚠️ 通过,但有 {len(warnings)} 条提醒")
    else:
        print("✅ 审查全部通过,可以推送")
    return 0


if __name__ == "__main__":
    sys.exit(main())
