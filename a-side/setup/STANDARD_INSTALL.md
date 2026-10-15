# 标准安装步骤（与机器无关）

> **这才是项目标准步骤。** 若你的机器没有本地 TLS 代理拦截，`git` 命令**不带任何额外参数**。
> 本机特有的代理/证书问题见 [`MACHINE_SPECIFIC_PROXY.md`](MACHINE_SPECIFIC_PROXY.md)，
> **那是本机的绕行方案，不是项目标准做法。**

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| Python | ≥ 3.10（本项目在 3.12.4 上验证） |
| GPU | 建议 ≥ 8 GB 显存；**E4B 在 8 GB 上不可行**（见 §5） |
| 磁盘 | 预留 ≥ 30 GiB（模型权重 + 数据集 + 虚拟环境） |
| git | 任意近期版本（含 `git-lfs` 可选） |

## 2. 获取代码（标准做法）

```bash
git clone https://github.com/joyboy-type/EdgeCoRAG.git
cd EdgeCoRAG
```

**不需要** `-c http.sslVerify=false` 之类的参数。若你的环境要求关闭 TLS 校验，
说明存在本地中间人代理，应先修好证书信任链，而不是降低安全要求。

## 3. 环境配置

本项目的 Python 依赖安装在项目目录之外（权重与虚拟环境不入仓库）。
`a-side/scripts/project_config.py` 统一定义缓存位置，解析优先级：

```
EDGECORAG_STORE 环境变量  →  HF_HOME  →  默认路径
```

**推荐做法**：先用环境变量指定一个**工作区之外**的存储盘：

```bash
# Linux / macOS
export EDGECORAG_STORE=/path/to/edgecorag-store

# Windows PowerShell
$env:EDGECORAG_STORE = "E:\EdgeCoRAG-A-store"
```

然后建两个**互相隔离**的环境（原因见 §4）：

```bash
python -m venv .venv-main      # transformers 5.x：EmbeddingGemma 2 / Gemma 4
python -m venv .venv-mrag      # transformers 4.x：utility-mrag 作者代码
```

安装依赖：

```bash
# .venv-main
.venv-main/bin/python -m pip install -r a-side/reports/requirements-main.lock.txt

# .venv-mrag
.venv-mrag/bin/python -m pip install -r a-side/reports/requirements-mrag.lock.txt
```

> Windows 下把 `bin/` 换成 `Scripts/`。

**PyTorch 必须装 CUDA 构建**：默认 `pip install torch` 在部分环境会拿到 CPU-only 轮子。
用官方索引显式指定：

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

（`cu128` 按你的驱动支持的 CUDA 版本调整；本机驱动 592.00 报告 CUDA 13.1，cu128 可用。）

## 4. 为什么必须两个环境

作者 `utility-mrag` 的 `pyproject.toml` 原文：

> Qwen3-VL needs >=4.57; the Ovis 2.5 / MiniCPM-V remote code targets the 4.x API
> (transformers 5.x removed attributes it relies on), so cap below 5.

而 EmbeddingGemma 2 / Gemma 4 需要 transformers 5.x。
**不要在同一环境里升级**——`transformers` 5.x 移除了作者代码依赖的属性。

## 5. 硬件边界（实测，与机器相关但结论通用）

| 模型 | 参数量 | BF16 | INT4 | 8 GB 显存结论 |
|---|---|---|---|---|
| EmbeddingGemma 2 | 0.744 B | 1.39 GiB | 0.35 GiB | ✅ 实测占用 0.83 GiB |
| Gemma 4 E2B | 5.123 B | 9.54 GiB | 2.39 GiB | ✅ INT4 实测 6.28 GiB |
| Gemma 4 E4B | 7.996 B | 14.89 GiB | 3.72 GiB | ⛔ **加载即占 8.685 GiB > 8.0，不可行** |

E4B 超限的根因：**4bit 量化不覆盖 `lm_head`**（0.671 B 参数以 bf16 存储 ≈ 1.34 GiB）。
→ **不能只用「参数量 × 0.5 字节」估算显存，必须实测。**

## 6. 数据获取

```bash
python a-side/scripts/download_dataset.py          # parquet（约 4.0 GiB）
python a-side/scripts/download_dataset.py --inspect
```

数据版本锁定为 `uclanlp/MRAG-Bench` @
`43620fde4044bb150e158c67ad7af6b6b11e1da2`，许可 CC-BY-4.0。

> 若你的网络无法直连 `huggingface.co`，设置 `HF_ENDPOINT` 指向可用镜像。
> 这属于网络环境问题，见 `MACHINE_SPECIFIC_PROXY.md`。

## 7. 模型权重

```bash
python a-side/scripts/download_models.py --check
python a-side/scripts/download_models.py --model embeddinggemma
python a-side/scripts/download_models.py --model e2b
```

## 8. 验证安装（标准冒烟）

```bash
# CUDA 与 BF16
.venv-main/bin/python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.is_bf16_supported())"
# 期望: 2.x.x+cu1xx True True

# 检索接口
.venv-main/bin/python a-side/scripts/smoke_embedding.py --self-test

# 作者单元测试（不需要权重）
.venv-mrag/bin/python -m pytest third_party/utility-mrag/tests -q
# 期望: 23 passed
```

## 9. 交接包自检

```bash
.venv-main/bin/python a-side/scripts/verify_handover_sample.py
.venv-main/bin/python a-side/scripts/validate_schema.py
```

期望 `28/28` 项通过。
