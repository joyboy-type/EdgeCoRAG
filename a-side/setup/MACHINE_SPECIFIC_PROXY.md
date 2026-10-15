# 本机特有的代理与 TLS 问题（**不是项目标准做法**）

> ⚠️ **这不是安装步骤。** 项目标准步骤见 [`STANDARD_INSTALL.md`](STANDARD_INSTALL.md)。
> 本文件只记录**某一台机器**上观察到的环境异常及绕行办法，换机器后大概率不适用。

---

## 0. 为什么单独放一个文件

本机曾把 `-c http.sslVerify=false` 当成常规克隆方式写进说明。
**这是错的**：关闭 TLS 校验会放弃证书验证，**不应作为通用方案**。
正确做法是修好本地代理的证书信任链。下面记录的只是**临时绕行**。

---

## 1. 现象

本机 `0.0.0.0:443` 被 **Watt Toolkit**（进程名 `Steam++.Accelerator`）监听，
它把 `github.com` / `api.github.com` 的 DNS 解析改写为 `127.0.0.1` 并做 TLS 中间人。

| 现象 | 原因 |
|---|---|
| `git clone` 报 `schannel: CRYPT_E_NO_REVOCATION_CHECK` | schannel 无法通过该代理完成证书吊销检查 |
| `requests` 报 `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` | 代理出示的证书不在 certifi 信任链中 |
| **`api.github.com/repos/<repo>` 返回假的 404** | 代理旁路了该 API 路由 |
| `git ls-remote` 有时通过、有时报同样的错 | 间歇性，取决于代理解析结果 |

**诊断脚本**：`a-side/scripts/diagnose_tls_interception.py`、
`a-side/scripts/verify_github_api_authenticity.py`。

---

## 2. 临时绕行（仅在本机）

```bash
# 只在确认存在本地中间人代理、且暂时无法修证书链时使用
git -c http.sslVerify=false clone https://github.com/joyboy-type/EdgeCoRAG.git
git -c http.sslVerify=false push
```

**注意**：

- **不要**把它写进 `git config --global`，否则全局降级安全。
- **不要**把它当作 CI 或他人机器的标准步骤。
- 更好的办法：在 Watt Toolkit 里关闭对该域名的加速/证书替换，使证书链恢复正常。

---

## 3. 如何判断 GitHub API 的 404 是否可信

代理会造成**假 404**。判断方法：用**已知存在的公开仓库**做对照。
若对照组返回完整的真实字段（`default_branch`、`size`、`owner` 等），
说明通道确实到了 GitHub，此时对目标仓库的 404 才可信。

```bash
python a-side/scripts/verify_github_api_authenticity.py
```

本机实测：对照组 3/3 返回真实数据；对目标仓库的 API 返回 404，
但 `git ls-remote` **能读到分支**，说明该仓库可读（API 路由被代理旁路）。

---

## 4. 连接间歇性失败

本机 HTTPS 到 GitHub **时通时断**（实测克隆 5 次可全成功，也曾连续失败）。
因此脚本必须：

1. **优先复用已有工作副本**，不要每轮删除重建（一次失败会把成功副本也弄丢）；
2. 克隆带**退避重试**；
3. 用 `git rev-parse --git-dir` 校验目录**确实是有效仓库**——
   实测出现过 `.git` 目录残留但 git 不认的情况。

`a-side/scripts/publish_to_repo.py` 已实现以上三点。

---

## 5. 其它网络问题（同属本机环境，非项目标准）

| 现象 | 绕行 |
|---|---|
| `huggingface.co` DNS 被污染（解析到 `88.191.249.183` 与 Facebook 段 IPv6） | 设 `HF_ENDPOINT=https://hf-mirror.com`（实测 1.42 GiB 模型 37 秒） |
| `download.pytorch.org` 下载**完全停滞**（60 秒 0 字节） | 改用镜像，见下 |
| `raw.githubusercontent.com` DNS 被劫持到 `127.0.0.1` | 改从 API 取内容 |

**torch 轮子镜像实测速度**：

| 源 | 速度 |
|---|---|
| 上海交大 SJTU `mirror.sjtu.edu.cn/pytorch-wheels/cu128` | **13.31 MB/s**（安装时达 40 MB/s） |
| pytorch 官方 | 8.51 MB/s |
| 阿里云 | 1.24 MB/s |
| 清华 TUNA | 该镜像无 pytorch-wheels |

**结论**：慢源会**伪装成卡死**。安装前先测速（`a-side/scripts/probe_mirrors.py`），
不要盲目等待。

---

## 6. 给协作者的提示

如果你在**另一台机器**上克隆本仓库并遇到上述错误，
说明你的机器也有本地 TLS 代理。**建议先修证书链**，
只有在确认无法修复时才使用 §2 的临时绕行，**并在 PR 或 issue 中说明**。
