"""从 Windows 凭据管理器读取 git 凭证供推送使用。

**定位说明**

这是一个**临时/本地**工具: 本机没有安装 Git Credential Manager,
因此 Mingit 无法自动使用「凭据管理器」里已有的 `git:https://github.com` 条目。
本模块把该条目读出并以环境变量形式交给 git。

**安全约定**

* 只在本进程内存中持有 secret,**不写盘、不打印、不写进 remote 配置、不留在命令行**;
* 推送结束即丢弃;
* 由调用方决定是否使用(默认仅在 `--use-stored-credential` 时启用)。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

CRED_TYPE_GENERIC = 1


class _CREDENTIAL_ATTRIBUTE(ctypes.Structure):
    _fields_ = [("Keyword", wt.LPWSTR), ("Flags", wt.DWORD),
                ("ValueSize", wt.DWORD), ("Value", ctypes.POINTER(ctypes.c_byte))]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD), ("Type", wt.DWORD),
        ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
        ("LastWritten", ctypes.c_byte * 8),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
        ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR),
    ]


def read_github_credential() -> tuple[str, str] | None:
    """返回 (username, secret);找不到返回 None。

    Windows 凭据管理器里 git 的密码常以 UTF-16LE 存储,这里自动识别。
    """
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    advapi.CredReadW.restype = wt.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]

    for target in ("git:https://github.com", "git:https://github.com/",
                   "https://github.com"):
        p = ctypes.POINTER(_CREDENTIAL)()
        if not advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
            continue
        c = p.contents
        blob = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
        # UTF-16LE 判定: 偶数长度且奇数位为 0
        if len(blob) >= 2 and blob[1] == 0:
            secret = blob.decode("utf-16-le", errors="replace")
        else:
            secret = blob.decode("utf-8", errors="replace")
        user = c.UserName or ""
        advapi.CredFree(p)
        return user, secret.strip()
    return None
