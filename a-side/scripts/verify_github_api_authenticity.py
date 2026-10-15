"""在 TLS 被本地代理拦截的情况下,判断 API 返回是否是"真 GitHub"。

问题: 绕过证书校验(verify=False)后能拿到响应,但必须排除"本地代理伪造响应"的可能。
方法: 用**已知存在的公开仓库**做对照。若它们返回正常的完整数据,
说明通道确实到了 GitHub;那么对 joyboy-type/EdgeCoRAG 的 404 就是可信的。

用法: python scripts/verify_github_api_authenticity.py
"""

from __future__ import annotations

import json
import sys

import requests

requests.packages.urllib3.disable_warnings()  # noqa: E402

H = {"User-Agent": "dsh-probe", "Accept": "application/vnd.github+json"}
# 这些是确定存在的公开仓库,用作对照
CONTROLS = ["mragbench/MRAG-Bench", "Hcnaeg/utility-mrag", "torch/torch"]
# 待查目标
TARGETS = ["joyboy-type/EdgeCoRAG"]

# 真实的 GitHub API 响应一定含这些字段
EXPECT_KEYS = {"id", "full_name", "default_branch", "owner"}


def probe(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}"
    try:
        r = requests.get(url, headers=H, timeout=30, verify=False)
    except Exception as exc:  # noqa: BLE001
        return {"repo": repo, "error": f"{type(exc).__name__}: {exc}"}
    out = {"repo": repo, "status": r.status_code,
           "server": r.headers.get("server"), "ctype": r.headers.get("content-type")}
    if r.status_code == 200:
        try:
            j = r.json()
            out["keys_present"] = sorted(EXPECT_KEYS & set(j))
            out["looks_like_github"] = EXPECT_KEYS.issubset(set(j))
            out["full_name"] = j.get("full_name")
            out["default_branch"] = j.get("default_branch")
            out["private"] = j.get("private")
            out["size_kb"] = j.get("size")
            out["pushed_at"] = j.get("pushed_at")
            out["permissions"] = j.get("permissions")
        except Exception as exc:  # noqa: BLE001
            out["json_error"] = str(exc)
    else:
        out["body_head"] = r.text[:160].replace("\n", " ")
    return out


def main() -> int:
    print("=== 对照组(确定存在的公开仓库)===")
    controls_ok = 0
    for repo in CONTROLS:
        res = probe(repo)
        ok = res.get("looks_like_github")
        controls_ok += int(bool(ok))
        tag = "✅ 真 GitHub 响应" if ok else "❌ 异常"
        print(f"  {repo:28s} status={res.get('status')} {tag}")
        if ok:
            print(f"      default_branch={res['default_branch']} size={res['size_kb']}KB")
        else:
            print(f"      {json.dumps(res, ensure_ascii=False)[:200]}")

    print(f"\n  对照组通过 {controls_ok}/{len(CONTROLS)}")
    channel_real = controls_ok == len(CONTROLS)

    print("\n=== 目标仓库 ===")
    for repo in TARGETS:
        res = probe(repo)
        print(f"  {repo}")
        for k, v in res.items():
            if k != "repo":
                print(f"      {k}: {v}")

    print("\n=== 结论 ===")
    if channel_real:
        print("  ✅ 通道确实到达 GitHub(对照仓库返回完整真实数据)")
        print("     -> 对目标仓库的 404 可信: 该仓库为**私有**或 owner/repo 拼写有误")
        print("     -> 无法匿名读取,推送需要凭证")
    else:
        print("  ❌ 对照组未全部通过,无法断言 404 的真实性")
        print("     -> 先修好本地代理的证书信任,再重试")
    return 0


if __name__ == "__main__":
    sys.exit(main())
