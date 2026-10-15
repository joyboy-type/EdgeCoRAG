"""验证 MRAG-Bench 官方检索语料（image corpus）的可取得性。

**为什么单独做这一步**

检索侧主实验走"独立重检索"路线的前提是能拿到官方语料。官方 README 只给了
一个 Google Drive 分享链接，**没给文件名、大小、哈希或许可**。
在决定是否把重检索列为主实验路线之前，必须先给出**明确结论**：
"能拿到" / "拿不到" / "能拿到但许可不明"。

**本脚本只做探测，不下载大文件**（除非显式 --download）。

区分三种失败原因：
  1. 网络不可达（本机有代理/TLS 干扰，google.com 系域名可能不通）
  2. 文件不可访问（链接失效、需要登录、配额限制）
  3. 文件可访问但许可未声明

用法:
    python scripts/probe_corpus_access.py              # 只探测
    python scripts/probe_corpus_access.py --download    # 尝试下载并记录大小/哈希
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

FILE_ID = "1atwkNXH3aEtCLuqimZoB1Mifj5CwL3CL"
SHARE_URL = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"
DIRECT_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
OUT = cfg.ROOT / "outputs" / "corpus_probe" / "corpus_access.json"
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

HOSTS = ["drive.google.com", "docs.google.com", "googleusercontent.com",
         "www.googleapis.com", "lh3.googleusercontent.com"]


def tcp(host: str, port: int = 443, timeout: int = 12) -> dict:
    r: dict = {"host": host}
    try:
        ip = socket.gethostbyname(host)
        r["resolved_ip"] = ip
    except Exception as exc:  # noqa: BLE001
        r["dns_error"] = f"{type(exc).__name__}: {exc}"
        return r
    try:
        t0 = time.time()
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        r["tcp_ok"] = True
        r["connect_seconds"] = round(time.time() - t0, 2)
    except Exception as exc:  # noqa: BLE001
        r["tcp_ok"] = False
        r["tcp_error"] = f"{type(exc).__name__}: {exc}"
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--verify-tls", action="store_true",
                    help="启用证书校验（本机有本地中间人代理，默认关闭以便区分原因）")
    args = ap.parse_args()

    result: dict = {
        "script": "scripts/probe_corpus_access.py",
        "share_url": SHARE_URL,
        "direct_url": DIRECT_URL,
        "file_id": FILE_ID,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    print("=== 1. DNS / TCP 可达性 ===")
    reach = []
    for h in HOSTS:
        r = tcp(h)
        reach.append(r)
        if r.get("tcp_ok"):
            print(f"  ✅ {h:32s} {r['resolved_ip']}  {r['connect_seconds']}s")
        else:
            print(f"  ❌ {h:32s} {r.get('dns_error') or r.get('tcp_error')}")
    result["reachability"] = reach
    any_reach = any(r.get("tcp_ok") for r in reach)

    print("\n=== 2. HTTPS 访问分享页 ===")
    session = requests.Session()
    session.headers.update(UA)
    page: dict = {}
    try:
        r = session.get(SHARE_URL, timeout=40, verify=args.verify_tls,
                        allow_redirects=True)
        page["status"] = r.status_code
        page["final_url"] = r.url
        page["content_length"] = len(r.content)
        low = r.text.lower()
        # Drive 的典型提示
        for key, pat in (("signin_required", "sign in"),
                         ("quota_exceeded", "quota exceeded"),
                         ("not_found", "not found"),
                         ("virus_scan", "virus scan warning"),
                         ("file_name_hint", "mrag")):
            page[key] = pat in low
        print(f"  status={r.status_code}  len={len(r.content)}  final={r.url[:80]}")
        for k in ("signin_required", "quota_exceeded", "not_found", "virus_scan"):
            if page.get(k):
                print(f"    ⚠️ 页面提示: {k}")
    except Exception as exc:  # noqa: BLE001
        page["error"] = f"{type(exc).__name__}: {exc}"
        print(f"  ❌ 失败: {page['error'][:160]}")
    result["share_page"] = page

    print("\n=== 3. 直链响应头（不下载正文）===")
    direct: dict = {}
    try:
        r = session.get(DIRECT_URL, timeout=40, verify=args.verify_tls,
                        allow_redirects=True, stream=True)
        direct["status"] = r.status_code
        direct["final_url"] = r.url[:160]
        for h in ("Content-Type", "Content-Length", "Content-Disposition"):
            if h in r.headers:
                direct[h] = r.headers[h]
        print(f"  status={r.status_code}")
        for k, v in direct.items():
            if k not in ("status", "final_url"):
                print(f"    {k}: {str(v)[:100]}")
        # 小样本探测前 64KiB，判断是不是 HTML 登录页而不是文件
        chunk = next(r.iter_content(65536), b"")
        direct["first_bytes_hex"] = chunk[:8].hex()
        direct["looks_like_zip"] = chunk[:2] == b"PK"
        direct["looks_like_html"] = chunk[:5].lower() in (b"<!doc", b"<html")
        print(f"    首 8 字节: {direct['first_bytes_hex']}"
              f"  zip={direct['looks_like_zip']}  html={direct['looks_like_html']}")
        r.close()
    except Exception as exc:  # noqa: BLE001
        direct["error"] = f"{type(exc).__name__}: {exc}"
        print(f"  ❌ 失败: {direct['error'][:160]}")
    result["direct_link"] = direct

    # ---------------- 结论 ----------------
    print("\n=== 结论 ===")
    verdict = "unknown"
    drive_ok = any(r.get("tcp_ok") and "drive.google.com" in r.get("host", "")
                   for r in reach)
    if not drive_ok:
        # 关键: 区分"语料有问题"与"本机网络到不了 Google"
        verdict = "network_unreachable"
        print("  ⛔ **本机网络无法访问 Google 系域名** "
              "(drive/docs/www.googleapis.com 超时)。")
        print("     -> 这**不能**说明语料不存在或不可用；")
        print("        只能说明**在当前网络环境下无法验证**。")
        print("     -> 需要在能访问 Google 的环境重试，或向官方作者询问镜像/直链。")
        print("     -> 在取得语料前，重检索路线**不具备可执行条件**。")
    elif direct.get("looks_like_zip") and direct.get("Content-Length"):
        verdict = "downloadable"
        print("  ✅ 直链返回文件（ZIP），**可下载**。")
        print(f"     大小: {direct.get('Content-Length')} 字节")
        print("     -> 仍需单独确认**许可**（数据集 CC-BY-4.0 不覆盖该语料）。")
    elif direct.get("looks_like_html"):
        verdict = "requires_auth_or_confirmation"
        print("  ⚠️ 直链返回 HTML（登录页或确认页），**未能直接取得文件**。")
        print("     -> 可能需登录 Google 账号、或触发大文件确认页；也可能配额受限。")
        print("     -> 需人工在浏览器中确认。")
    else:
        print("  ⚠️ 未能判定。请查看上方各步骤输出。")

    result["verdict"] = verdict
    result["license_status"] = "unconfirmed"
    result["license_note"] = (
        "数据集本体是 CC-BY-4.0，但检索语料是**单独发布的压缩包**，"
        "官方未声明其许可，且其中各上游图片（Imagenet 等）许可不同。"
        "**在许可确认前，重检索结果不得对外发布。**")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
