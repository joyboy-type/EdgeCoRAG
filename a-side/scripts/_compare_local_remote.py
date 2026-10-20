"""比较本地 git worktree 与远端 ref 的文件级分歧（blob sha 对齐，只读）。

背景：本机 github.com:443 TCP 被中断，git fetch 不可用，但 api.github.com 可用。
因此用 git ls-tree（本地对象）与远端 tree JSON（_gh_api.py tree 产出）逐路径比较 blob sha，
在不做任何 fetch/reset/clean/force-push 的前提下给出一致的分歧清单。

用法:
    python scripts/_compare_local_remote.py <worktree> <remote_tree.json> [--out report.md]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GIT = Path(__file__).resolve().parent.parent / "tools" / "mingit" / "cmd" / "git.exe"


def ls_tree(worktree: Path, rev: str = "HEAD") -> dict[str, tuple[str, str]]:
    out = subprocess.run(
        [str(GIT), "ls-tree", "-r", "-z", "--long", rev],
        cwd=worktree,
        capture_output=True,
        check=True,
    ).stdout
    res: dict[str, tuple[str, str]] = {}
    for rec in out.split(b"\x00"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, sha, size = meta.split()
        if typ != b"blob":
            continue
        res[path.decode("utf-8")] = (sha.decode(), size.decode())
    return res


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    worktree = Path(sys.argv[1]).resolve()
    remote = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    local = ls_tree(worktree)

    rem: dict[str, str] = {}
    for e in remote["entries"]:
        if e["type"] == "blob":
            rem[e["path"]] = e["sha"]

    identical, differ, only_local, only_remote = [], [], [], []
    for p in sorted(set(local) | set(rem)):
        if p in local and p in rem:
            (identical if local[p][0] == rem[p] else differ).append(p)
        elif p in local:
            only_local.append(p)
        else:
            only_remote.append(p)

    lines = [
        "# 本地与远端文件级分歧",
        "",
        f"- 本地 worktree：`{worktree}`",
        "- 远端 ref：`2975d9cae550339628681dc397d80ed9ab6e0158`（results/runtime-v1.10.1-delivery）",
        f"- 远端 tree sha：`{remote['sha']}`",
        f"- 本地 blob 数：{len(local)}；远端 blob 数：{len(rem)}",
        "",
        f"- 内容一致：{len(identical)}",
        f"- 内容不同：{len(differ)}",
        f"- 仅本地存在：{len(only_local)}",
        f"- 仅远端存在：{len(only_remote)}",
        "",
    ]
    for title, key in (("仅远端存在（远端领先）", only_remote), ("仅本地存在（本地领先）", only_local), ("同名但内容不同", differ)):
        lines.append(f"## {title}（{len(key)}）")
        lines.append("")
        if key:
            for p in key:
                lines.append(f"- `{p}`")
        else:
            lines.append("（无）")
        lines.append("")

    text = "\n".join(lines)
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    print(f"identical={len(identical)} differ={len(differ)} only_local={len(only_local)} only_remote={len(only_remote)}")
    # 便于后续脚本消费
    print(json.dumps({"differ": differ, "only_local": only_local, "only_remote": only_remote}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
