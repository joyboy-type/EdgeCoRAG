"""网络可达性探针:区分「原始 TCP 阻断」与「HTTP 层可用」,为抓取策略提供依据。

用法: python scripts/probe_network.py
"""

from __future__ import annotations

import socket
import time

import requests

HOSTS = [
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "hf-mirror.com",
    "pypi.org",
    "aclanthology.org",
    "arxiv.org",
]

URLS = [
    "https://api.github.com/repos/Hcnaeg/utility-mrag",
    "https://codeload.github.com/Hcnaeg/utility-mrag/zip/refs/heads/master",
    "https://codeload.github.com/OwwO99/RAGRouter/zip/refs/heads/main",
    "https://pypi.org/simple/",
    "https://hf-mirror.com/api/models/google/embeddinggemma-2",
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dsh-probe"}


def main() -> int:
    print("=== 原始 TCP 443 ===")
    for h in HOSTS:
        try:
            ip = socket.gethostbyname(h)
        except Exception as exc:  # noqa: BLE001
            print(f"DNSFAIL {h:34s} {exc}")
            continue
        try:
            t0 = time.time()
            s = socket.create_connection((ip, 443), timeout=12)
            s.close()
            print(f"OK      {h:34s} {ip:16s} {time.time() - t0:.2f}s")
        except Exception as exc:  # noqa: BLE001
            print(f"BLOCKED {h:34s} {ip:16s} {type(exc).__name__}")

    print("\n=== HTTP GET (requests, 跟随重定向) ===")
    for u in URLS:
        try:
            t0 = time.time()
            r = requests.get(u, timeout=30, headers=UA, stream=True, allow_redirects=True)
            print(f"OK   {r.status_code}  {time.time() - t0:.2f}s  {u}")
            r.close()
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {type(exc).__name__}: {exc}  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
