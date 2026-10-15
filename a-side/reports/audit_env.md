# audit_env.md — 环境审计（第二版 · 实测后更新）

任务书实验 **A-P0-1** 的交付物之一。第一版为会话初期的探针结果；本版补充网络约束、镜像选型、模型精确体积与显存可行性判断。

- 首次探针：本会话初期（文档标注 2026-10-14）
- 本版更新：2026-10-15（本机实测）
- 工作区：`C:\Users\zhang'cheng'xuan\Desktop\1`
- 项目目录：`EdgeCoRAG-A`

---

## 1. 硬件实测

| 项 | 任务书假设 | **本机实测** | 结论 |
|---|---|---|---|
| GPU | RTX 5060 Laptop 8GB | **NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB** | ⚠️ 型号不同，同为 8GB 级 |
| 驱动 | — | **592.00，报告 CUDA Version 13.1** | ✅ 支持 cu128 及更高 |
| 显存当前占用 | — | 约 1059 MiB（桌面环境） | 实际可用约 7.1 GiB |
| 磁盘 | — | C: 87 GB 可用 / 321 GB；E: 162/403；F: 96/200 | ✅ 够用 |
| CPU/内存 | — | 未测（非瓶颈） | — |

## 2. 软件环境（已完成部分）

| 项 | 状态 |
|---|---|
| Python | 3.12.4（系统） |
| **git** | ✅ 已装 **便携版 MinGit 2.56.0** → `tools/mingit/cmd/git.exe`（不写系统 PATH、不触发 UAC） |
| uv | ❌ 未装（作者 README 用 uv；已用 venv + pip 等价替代） |
| **`.venv-main`** | ✅ **torch 2.11.0+cu128 安装成功**；transformers 5.19.0 / sentence-transformers 6.1.0 等依赖安装中 |
| `.venv-mrag` | ⏸ 待建（utility-mrag 作者代码复现，需 transformers 4.x） |

**关键成果**：`torch` 已从 CPU-only 换成 **CUDA 构建**（此前系统 Python 里是 `2.11.0+cpu`，GPU 完全用不上）。
使用方式：`.venv-main\Scripts\python.exe`

### 2.1 遇到的依赖冲突（已修正）

`sentence-transformers 6.1.0` 要求 `huggingface-hub<2.0.0,>=1.3.0`，与显式钉的 `huggingface-hub==2.2.0`
冲突（`pip ResolutionImpossible`）。**已移除该钉版**，交由 pip 解析器决定。
另移除脚本里写死的 `torch==2.11.0`：已装的本地版本是 `2.11.0+cu128`，
写死版本号会让 pip 去 PyPI 重新下载 **CPU-only** 轮子覆盖 CUDA 构建（实测确实发生了）。

## 3. 网络约束（本机最重要的一组事实）

`scripts/probe_network.py` 与 `scripts/probe_mirrors.py` 的实测结果：

| 主机 | 状态 | 影响 |
|---|---|---|
| `github.com` | ❌ **TCP 443 阻断** | `git clone` **不可用** |
| `api.github.com` | ✅ 可用 | 可查仓库元数据 |
| `codeload.github.com` | ✅ 可用 | **可用 zipball 替代 clone** |
| `raw.githubusercontent.com` | ❌ **DNS 被劫持到 127.0.0.1** | 不能直接取单文件 |
| `objects.githubusercontent.com` | ❌ 同上 | — |
| `huggingface.co` | ❌ **DNS 被污染到 88.191.249.183 / Facebook 段 IPv6** | 模型与数据集直连**不可用** |
| **`hf-mirror.com`** | ✅ **可用** | **绕行方案：`HF_ENDPOINT=https://hf-mirror.com`** |
| `pypi.org` | ✅ 可用 | — |
| `aclanthology.org` / `arxiv.org` | ✅ 可用 | 论文 PDF 抓取正常 |

### 3.1 镜像实测速度（`scripts/probe_mirrors.py`）

| torch 轮子镜像 | 实测速度 | 选用 |
|---|---|---|
| **上海交大 SJTU** | **13.31 MB/s**（实测下载 2753 MB 时达 40 MB/s） | ✅ **首选** |
| pytorch 官方 | 8.51 MB/s | 回退 |
| 阿里云 | 1.24 MB/s | 否 |
| 清华 TUNA | ❌ 该镜像无 `pytorch-wheels` | 否 |

> ⚠️ **教训**：首次安装用 `download.pytorch.org` 时下载**完全停滞**（60 秒 0 字节，已终止）。
> 换 SJTU 后 2753 MB 的轮子约 45 秒下完。**慢源会伪装成"卡死"，应先测速再装。**

## 4. 模型的精确体积与显存可行性（**决定性数据**）

从 safetensors 元数据精确读出（`scripts/probe_model_sizes.py`），非 config 估算：

| 模型 | **真实参数量** | BF16 | INT8 | INT4 |
|---|---|---|---|---|
| `google/embeddinggemma-2` | **0.744 B** | 1.39 GiB | 0.69 GiB | 0.35 GiB |
| `google/gemma-4-E2B-it` | **5.123 B** | **9.54 GiB** | 4.77 GiB | **2.39 GiB** |
| `google/gemma-4-E4B-it` | **7.996 B** | **14.89 GiB** | 7.45 GiB | **3.72 GiB** |

**旁证**：任务书第 3 节称 EmbeddingGemma 2「文本+视觉加载 440M，总多模态 740M」——
实测 **744,371,992 参数**，与「740M」吻合，**任务书此处准确**。

### 4.1 结论：8 GB 显存下的硬约束

1. **E2B (BF16, 9.54 GiB) 装不进 8 GB 显存**；**E4B (BF16, 14.89 GiB) 更不可能**。
   → 任务书风险 4「RTX 5060 Laptop 8GB 可能需要顺序运行和量化 Gemma 模型」**实测成立，且是必须而非可选**。
2. **必须量化**：INT4 下 E2B=2.39 GiB、E4B=3.72 GiB，加上视觉塔、KV cache、激活值后才有可能驻留。
3. **不能同时驻留**：EmbeddingGemma 2 (1.39 GiB) + 一个 INT4 生成模型 + KV cache ≈ 已接近上限。
   → 检索与生成**必须顺序执行**，并如实计入任务书要求的 `encoder_ms` / `generation_ms` 与冷启动开销。
4. **架构确认**：E2B/E4B 的 `architectures` 均为 **`Gemma4ForConditionalGeneration`**，
   `model_type=gemma4`，`pipeline_tag=any-to-any`。
   → 作者仓库 `utility_mrag/models/gemma.py` **硬编码 `Gemma3ForConditionalGeneration`**，
     **Gemma 4 必须改写该封装**（这是本项目最核心的移植工作）。
5. 三个模型 `gated=False`，**无需 HF token**，可直接从镜像下载。

## 5. 磁盘布局（重资源已移出工作区）

本项目合法的磁盘需求超过 35 GiB，全部**可重新生成**，因此已迁出工作区：

| 位置 | 内容 | 体积 |
|---|---|---|
| **工作区** `EdgeCoRAG-A` | 脚本、论文、代码、结果 | **≈ 0.16 GiB** |
| `E:\EdgeCoRAG-A-store\hf-cache` | 模型权重缓存（三个模型） | **25.92 GiB** |
| `E:\EdgeCoRAG-A-store\venvs\venv-main` | `.venv-main`（junction 指回工作区） | 4.92 GiB |
| `E:\EdgeCoRAG-A-store\venvs\venv-mrag` | `.venv-mrag`（junction 指回工作区） | 4.62 GiB |
| `C:\...\AppData\Local\pip\cache` | **已清理**（释放 3.69 GB） | 0 |

**手段**：`robocopy /MOVE` + **junction（目录联接）**。选 junction 而非改路径，
是因为它对进程完全透明——`HF_HOME` 指向、虚拟环境里写死的 `pyvenv.cfg`/shebang 都无需修改。

**迁移后实测验证**（全部通过）：

| 验证项 | 结果 |
|---|---|
| `.venv-main` 经链接运行 | `torch 2.11.0+cu128`, `cuda True`, `bf16 True` |
| `.venv-mrag` 经链接运行 | `transformers 4.57.6` |
| 作者测试经链接运行 | **23 passed** |
| 模型经新缓存加载 | ✅ EmbeddingGemma 2（BF16、0.83 GiB 显存、维度截断全部正确） |
| 磁盘变化 | C: 50 GB → **89 GB 可用** |

**可重复执行**：`python scripts\bootstrap_store.py --check | --apply`（幂等）。
缓存路径统一在 `scripts/project_config.py`，优先级 `EDGECORAG_STORE` → `HF_HOME` → 默认路径。

> E:/F: 与 C: 是**同一块 NVMe（Disk0, 954 GB）上的分区**，非外接盘，迁移不影响 I/O 性能。

## 6. 环境配置现状与后续步骤

```powershell
# 已完成
python scripts\install_portable_git.py        # 便携 git
python scripts\setup_env.py main              # .venv-main: torch cu128 + transformers 5.x

# 待执行
python scripts\setup_env.py mrag              # .venv-mrag: transformers 4.x（作者代码复现）

# 模型下载必须带镜像变量
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HOME     = "models\_hf_home"          # 缓存放项目内，便于统计体积
```

**验证通过标准**：
```powershell
.venv-main\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.is_bf16_supported())"
# 期望: 2.11.0+cu128 True True
```

## 7. 阻断项与已解决项

| 项 | 状态 |
|---|---|
| PowerShell 沙箱运行器故障（`--temp is not an existing directory`） | ✅ 已解决（文件策略切到 `danger-full-access` 后 shell 恢复） |
| `git clone` 因 github.com 阻断失败 | ✅ 已解决（改用 `codeload` zipball + API 取 commit SHA） |
| HuggingFace 直连失败 | ✅ 已解决（`HF_ENDPOINT=https://hf-mirror.com`） |
| torch 官方源下载停滞 | ✅ 已解决（改用 SJTU 镜像） |
| pip 依赖冲突 | ✅ 已解决（移除冲突钉版） |
| VisDoM 仓库与数据集**无许可证** | ❌ **未解决，使用前必须先处理** |
| VisDoM 仓库 1.6 GB 未下载 | ⏸ 待定（等许可结论） |
| `uv` 未装 | ⏸ 低优先级（venv+pip 已可替代；若需严格复现作者 `uv.lock` 则应补装） |

## 8. 待办清单

- [ ] 完成 `.venv-main` 依赖安装并验证 BF16
- [ ] 建立 `.venv-mrag`（transformers 4.x）并跑通 `pytest tests`
- [ ] 用镜像下载 EmbeddingGemma 2（1.39 GiB），跑通图文检索 smoke test
- [ ] 验证 Gemma 4 能否取到「True/False」token 的 logit（移植核心风险）
- [ ] 取回 MRAG-Bench 数据集并锁定 revision/hash
- [ ] 确认 VisDoM / 各仓库许可证
