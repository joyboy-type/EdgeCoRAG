"""小型 GitHub API 读取工具：只读远端快照，不修改本地仓库。

用途：本机到 github.com:443 的 TCP 连接被中断（Watt Toolkit），git fetch/push 不可用，
但 api.github.com 可用。因此用 contents/trees API 读取远端指定 ref 的文件内容与 blob sha。

用法:
    python scripts/_gh_api.py tree <ref> [--out FILE]      # 递归列出 tree（含 sha/size）
    python scripts/_gh_api.py get <path> <ref> <localdir>  # 下载单文件到 localdir/path
    python scripts/_gh_api.py list <dir> <ref>             # 列出目录
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

REPO = "joyboy-type/EdgeCoRAG"
H = {"User-Agent": "dsh", "Accept": "application/vnd.github+json"}
API = "https://api.github.com"


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers=H, timeout=90, verify=False)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {url}\n{r.text[:400]}")
    return r


def tree(ref: str) -> dict:
    j = _get(f"{API}/repos/{REPO}/git/trees/{ref}?recursive=1").json()
    if j.get("truncated"):
        raise RuntimeError("tree truncated")
    return j


def get_file(path: str, ref: str, outdir: Path) -> dict:
    j = _get(f"{API}/repos/{REPO}/contents/{path}?ref={ref}").json()
    if isinstance(j, list):
        raise RuntimeError(f"是目录不是文件: {path}")
    if j.get("encoding") != "base64" or j.get("content") is None:
        # 大文件走 blob API
        blob = _get(f"{API}/repos/{REPO}/git/blobs/{j['sha']}").json()
        data = base64.b64decode(blob["content"])
    else:
        data = base64.b64decode(j["content"])
    dest = outdir / Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"path": path, "sha": j["sha"], "size": len(data)}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "tree":
        ref = sys.argv[2]
        j = tree(ref)
        blob = {
            "sha": j["sha"],
            "truncated": j.get("truncated", False),
            "entries": [
                {"path": e["path"], "type": e["type"], "sha": e.get("sha"), "size": e.get("size")}
                for e in j["tree"]
            ],
        }
        if "--out" in sys.argv:
            out = Path(sys.argv[sys.argv.index("--out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"wrote {out} entries={len(blob['entries'])}")
        else:
            print(json.dumps(blob, indent=2, ensure_ascii=False))
        return 0
    if cmd == "get":
        path, ref, outdir = sys.argv[2], sys.argv[3], Path(sys.argv[4])
        print(json.dumps(get_file(path, ref, outdir), ensure_ascii=False))
        return 0
    if cmd == "list":
        d, ref = sys.argv[2], sys.argv[3]
        j = _get(f"{API}/repos/{REPO}/contents/{d}?ref={ref}").json()
        for x in j:
            print(f"{x['type']:4} {x['size'] if x.get('size') is not None else '':>9} {x['name']}")
        return 0
    print(f"未知命令 {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
