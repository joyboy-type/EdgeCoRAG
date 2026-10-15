# 本机环境注意事项（Windows + 本地代理 + 国内网络）

> 本机实测得出的坑，换机器后不一定适用；记录下来是为了可复现。

## 1. `github.com` 被本地代理拦截

本机 `0.0.0.0:443` 由 **Watt Toolkit**（进程名 `Steam++.Accelerator`）监听，
它把 `github.com` / `api.github.com` 的 DNS 解析改写为 `127.0.0.1` 并做 TLS 中间人。后果：

| 现象 | 原因 |
|---|---|
| `git clone` 报 `schannel: CRYPT_E_NO_REVOCATION_CHECK` | schannel 无法通过该代理完成证书吊销检查 |
| `requests` 报 `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` | 代理出示的证书不在 certifi 信任链中 |
| `api.github.com/repos/<repo>` 返回**假 404** | 代理旁路了该 API 路由 |

**对策**：git 操作加 `-c http.sslVerify=false`。

```bash
git -c http.sslVerify=false clone https://github.com/joyboy-type/EdgeCoRAG.git
git -c http.sslVerify=false push
```

**如何判断 404 是否可信**：用已知存在的公开仓库做对照。若对照组返回完整真实字段
（`default_branch`、`size`、`owner` 等），说明通道确实到了 GitHub。
见 `scripts/verify_github_api_authenticity.py`。

**注意**：HTTPS 连接**间歇性**失败——`ls-remote` 有时通有时不通，克隆实测 5 次可全成功。
故脚本里克隆带重试、并优先复用已有副本，不要每次删了重建。

## 2. HuggingFace 直连不可用

`huggingface.co` 的 DNS 被污染（解析到 `88.191.249.183` 与 Facebook 段 IPv6），直连超时。
**对策**：设 `HF_ENDPOINT=https://hf-mirror.com`（实测 1.42 GiB 模型 37 秒下完）。

## 3. pip / torch 镜像

`download.pytorch.org` 实测**下载完全停滞**（60 秒 0 字节）。按速度实测选源：

| 源 | 实测速度 |
|---|---|
| 上海交大 SJTU `mirror.sjtu.edu.cn/pytorch-wheels/cu128` | **13.31 MB/s**（安装时达 40 MB/s） |
| pytorch 官方 | 8.51 MB/s |
| 阿里云 | 1.24 MB/s |
| 清华 TUNA | 该镜像无 pytorch-wheels |

PyPI 用 `https://pypi.tuna.tsinghua.edu.cn/simple`。

## 4. 磁盘与缓存（重资源外置）

模型权重与虚拟环境**不放仓库内**。本机布局：

```
工作区   EdgeCoRAG-A                  ≈ 0.2 GiB  仅脚本/论文/结果
外部存储 E:\EdgeCoRAG-A-store         ≈ 25 GiB
         ├── hf-cache/   模型权重
         ├── datasets/   MRAG-Bench parquet
         └── venvs/      两个虚拟环境（junction 链回工作区）
```

用 **junction** 而非改路径：对进程透明，`HF_HOME` 与虚拟环境内写死的路径都无需修改。
迁移脚本 `scripts/bootstrap_store.py --apply`（幂等）。

## 5. 双环境隔离（必需）

作者 `utility-mrag` 的 `pyproject.toml` 明确：

> Qwen3-VL needs >=4.57; the Ovis 2.5 / MiniCPM-V remote code targets the 4.x API
> (transformers 5.x removed attributes it relies on), so cap below 5.

而 EmbeddingGemma 2 / Gemma 4 需要 transformers 5.x。
→ `.venv-mrag`（4.57.6）与 `.venv-main`（5.19.0）必须分开，**不要在同一环境里升级**。

## 6. 显存实测（8 GB 卡）

| 模型 | BF16 | INT4 | 结论 |
|---|---|---|---|
| EmbeddingGemma 2（0.744 B） | 1.39 GiB | 0.35 GiB | ✅ 实测占用 0.83 GiB |
| Gemma 4 E2B（5.123 B） | 9.54 GiB | 2.39 GiB | INT4 实测 6.28 GiB，可全驻显存 |
| Gemma 4 E4B（7.996 B） | 14.89 GiB | 3.72 GiB | ⛔ **加载即占 8.685 GiB > 8.0，本机不可行** |

E4B 超限的根因：**4bit 量化不覆盖 `lm_head`**（0.671 B 参数以 bf16 存储，约 1.34 GiB）。
→ 不能只用「参数量 × 0.5 字节」估算显存，必须实测。

## 7. PowerShell 下查看本仓库文件

PowerShell 5.1 默认按 GBK 读取，`Get-Content` 显示中文会乱码。
用 `read` 工具、或指定 `-Encoding UTF8` 查看。文件本身是 UTF-8，内容正常。
