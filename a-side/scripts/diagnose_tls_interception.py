"""查清 github.com 被解析到 127.0.0.1 是否意味着本地存在 TLS 拦截。

背景: 之前 requests 访问 api.github.com 成功过(200),现在却报
  CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate
且 DNS 把 github.com / api.github.com 解析到 127.0.0.1。
需要判断: 是本地代理在拦截,还是解析被污染导致连接到了错误的服务。

用法: python scripts/diagnose_tls_interception.py
"""

from __future__ import annotations

import socket
import ssl
import subprocess
import sys

import requests

HOSTS = ["github.com", "api.github.com", "codeload.github.com", "pypi.org"]


def listening(port: int = 443) -> list[str]:
    """检查本机是否在监听 443。"""
    out = []
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                           capture_output=True, text=True, errors="replace", timeout=30)
        for line in (r.stdout or "").splitlines():
            if f":{port} " in line and "LISTENING" in line.upper():
                out.append(line.strip())
    except Exception as exc:  # noqa: BLE001
        out.append(f"<netstat 失败: {exc}>")
    return out


def peer_cert(host: str, port: int = 443) -> dict:
    """不带校验地取对端证书,看签发者是谁——若是本地代理会露出马脚。"""
    info: dict = {}
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ip = socket.gethostbyname(host)
        info["resolved_ip"] = ip
        with socket.create_connection((ip, port), timeout=12) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as ss:
                cert = ss.getpeercert()
                info["subject"] = cert.get("subject")
                info["issuer"] = cert.get("issuer")
                info["notAfter"] = cert.get("notAfter")
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def main() -> int:
    print("=== 本机 443 端口监听情况 ===")
    ls = listening(443)
    print("  " + ("\n  ".join(ls) if ls else "(无进程监听 443)"))

    print("\n=== DNS 解析 ===")
    for h in HOSTS:
        try:
            print(f"  {h:24s} -> {socket.gethostbyname(h)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {h:24s} -> DNS FAIL {exc}")

    print("\n=== 对端证书(不校验) ===")
    for h in HOSTS:
        info = peer_cert(h)
        print(f"  {h}")
        for k, v in info.items():
            print(f"      {k}: {v}")

    print("\n=== requests 带/不带校验 ===")
    for h in ("https://api.github.com/repos/joyboy-type/EdgeCoRAG",):
        for verify in (True, False):
            try:
                r = requests.get(h, timeout=25, headers={"User-Agent": "dsh"},
                                 verify=verify)
                print(f"  verify={verify!s:5s} -> {r.status_code}  {h}")
            except Exception as exc:  # noqa: BLE001
                print(f"  verify={verify!s:5s} -> {type(exc).__name__}: {str(exc)[:110]}")

    print("\n=== 系统的 CA 证书数量(判断是否为本地代签) ===")
    try:
        import certifi
        print(f"  certifi: {certifi.where()}")
        txt = open(certifi.where(), encoding="utf-8", errors="replace").read()
        print(f"  证书数: {txt.count('BEGIN CERTIFICATE')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  certifi 不可用: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
