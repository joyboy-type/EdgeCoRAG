"""探测到共创仓库的推送通道是否可行(不涉及凭证,只测连通性与可见性)。

用法: python scripts/probe_coauthor_repo.py [owner/repo]
"""

from __future__ import annotations

import socket
import sys

import requests

DEFAULT = "joyboy-type/EdgeCoRAG"
UA = {"User-Agent": "dsh-probe"}


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else DEFAULT

    print("=== 原始 TCP 443 ===")
    for h in ("github.com", "api.github.com", "codeload.github.com"):
        try:
            ip = socket.gethostbyname(h)
            s = socket.create_connection((ip, 443), timeout=10)
            s.close()
            print(f"  OK   {h:22s} {ip}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {h:22s} {type(exc).__name__}")

    print("\n=== API 可见性 ===")
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}", timeout=25, headers=UA)
        print(f"  {r.status_code}  api.github.com/repos/{repo}")
        if r.status_code == 200:
            j = r.json()
            print(f"      default_branch={j.get('default_branch')} "
                  f"private={j.get('private')} size={j.get('size')}KB")
        elif r.status_code == 404:
            print("      -> 404: 私有仓库,或 owner/repo 拼写有误")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {type(exc).__name__}: {exc}")

    print("\n=== git 智能 HTTP 通道(匿名) ===")
    url = f"https://github.com/{repo}.git/info/refs?service=git-upload-pack"
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "git/2.56.0"})
        print(f"  status={r.status_code}  {url}")
        head = r.text[:120].replace("\n", " ")
        print(f"  body[:120]={head!r}")
        if r.status_code == 401:
            print("      -> 401: 需要认证(私有仓库的正常表现)")
        elif r.status_code == 200:
            print("      -> 200: 匿名可读(公开仓库)")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {type(exc).__name__}: {exc}")

    print("\n=== 匿名 git ls-remote(用项目内便携 git) ===")
    import subprocess
    from pathlib import Path
    git = Path(__file__).resolve().parent.parent / "tools" / "mingit" / "cmd" / "git.exe"
    git_exe = str(git) if git.exists() else "git"
    try:
        p = subprocess.run([git_exe, "ls-remote", f"https://github.com/{repo}.git"],
                           capture_output=True, text=True, timeout=60,
                           env={"GIT_TERMINAL_PROMPT": "0", "PATH": str(git.parent),
                                "SYSTEMROOT": "C:\\Windows"})
        print(f"  exit={p.returncode}")
        out = (p.stdout or p.stderr).strip()
        print("  " + "\n  ".join(out.splitlines()[:6]))
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
