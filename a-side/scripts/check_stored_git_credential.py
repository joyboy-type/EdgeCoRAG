"""只读检查 Windows 凭据管理器中是否存在可用的 GitHub 凭证。

**只判断"有没有、能不能用",不打印 secret 内容。**
若找到,用它做一次 git 认证探测(不推送任何东西,只问远程"我是谁")。

用法: python scripts/check_stored_git_credential.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

GIT = cfg.ROOT / "tools" / "mingit" / "cmd" / "git.exe"

CRED_TYPE_GENERIC = 1
CRED_MAX_CREDENTIAL_BLOB_SIZE = 5 * 512


class CREDENTIAL_ATTRIBUTE(ctypes.Structure):
    _fields_ = [("Keyword", wt.LPWSTR),
                ("Flags", wt.DWORD),
                ("ValueSize", wt.DWORD),
                ("Value", ctypes.POINTER(ctypes.c_byte))]


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD),
        ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR),
        ("LastWritten", ctypes.c_byte * 8),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTE)),
        ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


def main() -> int:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi.CredReadW.restype = wt.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]

    targets = ["git:https://github.com", "git:https://github.com/",
               "https://github.com"]
    found = None
    for t in targets:
        p = ctypes.POINTER(CREDENTIAL)()
        ok = advapi.CredReadW(t, CRED_TYPE_GENERIC, 0, ctypes.byref(p))
        if not ok:
            print(f"  ✗ 未找到: {t}  (err={ctypes.get_last_error()})")
            continue
        c = p.contents
        blob = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
        print(f"  ✅ 找到: {t}")
        print(f"     用户名     : {c.UserName}")
        print(f"     类型       : {c.Type} (1=Generic)")
        print(f"     secret 长度: {len(blob)} 字节")
        print(f"     secret 前缀: {blob[:4]!r}  (只看前 4 字节,不泄露全文)")
        # 判断 secret 形态: Windows 凭据管理器常把密码存成 UTF-16
        is_utf16 = len(blob) >= 2 and blob[1] == 0 and blob[0] != 0
        plain = blob.decode("utf-16-le", errors="replace") if is_utf16 else blob.decode("utf-8", errors="replace")
        print(f"     编码       : {'UTF-16LE' if is_utf16 else 'UTF-8/ASCII'}")
        print(f"     形态       : {'疑似 PAT' if plain[:4] in ('ghp_','gith','gho_') else '非 PAT 前缀(可能是 OAuth/其它)'}")
        found = (t, c.UserName, plain)
        advapi.CredFree(p)
        break

    if not found:
        print("\n结论: 凭据管理器中无可用的 github 凭证")
        return 1

    t, user, secret = found
    print("\n=== git 认证探测(不推送,只查身份)===")
    import os
    import subprocess
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    # 用 GIT_ASKPASS 传凭证,避免出现在命令行
    ap = cfg.store_root() / "_askpass_probe.cmd"
    ap.write_text("@echo off\r\necho %PROBE_USER%\r\necho %PROBE_SECRET%\r\n",
                  encoding="ascii")
    env["PROBE_USER"] = user
    env["PROBE_SECRET"] = secret
    r = subprocess.run(
        [str(GIT), "-c", "http.sslVerify=false", "-c", f"core.askPass={ap}",
         "ls-remote", "https://github.com/joyboy-type/EdgeCoRAG.git"],
        capture_output=True, text=True, errors="replace", env=env, timeout=90)
    ap.unlink(missing_ok=True)
    ok = r.returncode == 0
    print(f"  ls-remote exit={r.returncode} -> {'✅ 凭证可用' if ok else '❌ 凭证不可用'}")
    if not ok:
        print(f"  {(r.stderr or '').strip()[:300]}")
    else:
        print("  (注: ls-remote 只需读权限,不能证明有写权限)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
