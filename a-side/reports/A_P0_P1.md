# reports/A_P0_P1.md — 复现进展与原论文差异

> 任务书提交清单第 4 项。记录**本项目实际做了什么、与原论文的差异、以及所有未验证的边界**。
> 原则：论文里已有的提升是**作者报告**；本项目**尚未**跑任何一条完整路径，不得把任务书或论文数字当作本项目结果。

- 项目目录：`EdgeCoRAG-A`
- 记录时间：2026-10-15
- 对应实验：A-P0-1（作者测试 + 20 题准备）、A-P0-2（图文检索）**进行中**

---

## 1. 环境基线（已实测）

| 项 | 值 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop, **8188 MiB**（可用约 7.1 GiB） |
| 驱动 | 592.00 / CUDA Version 13.1 |
| `.venv-main` | python 3.12.4, **torch 2.11.0+cu128**, transformers **5.19.0**, CUDA 12.8, BF16 ✅ |
| `.venv-mrag` | python 3.12.4, **torch 2.11.0+cu128**, transformers **4.57.6**, CUDA 12.8, BF16 ✅ |
| 额外 | bitsandbytes **0.50.2**（Windows + CUDA 可用，用于 4bit 量化） |

**双环境隔离的依据**（作者 `pyproject.toml` 原文）：

> Qwen3-VL needs >=4.57; the Ovis 2.5 / MiniCPM-V remote code targets the 4.x API
> (transformers 5.x removed attributes it relies on), so cap below 5.

**与原论文/任务书的差异**：任务书假设 RTX 5060 Laptop；本机是 RTX 4060 Laptop（同为 8 GB 级）。
任务书未提到需要量化，实测表明**量化是必须而非可选**（见 §3）。

## 2. A-P0-1：作者代码测试（✅ 完成）

在 `.venv-mrag` 下运行作者测试：

```
collected 23 items
tests/test_candidate_pool.py .....      [ 21%]
tests/test_mrag_bench_eval.py ......    [ 47%]
tests/test_topk_selection.py ......     [ 73%]
tests/test_true_false_logits.py ......  [100%]
============================= 23 passed in 2.31s ==============================
```

**结论：作者单元测试 23/23 通过**，无需模型权重。这是任务书 A-P0-1 的第一项。

**与原论文差异**：无。测试是作者提供的原样代码（commit `d5b9e573ece6`）。

**待办**：20 题候选 manifest（`manifest_20.jsonl`）尚未生成，依赖 MRAG-Bench 数据获取。

## 3. A-P0-2：EmbeddingGemma 2 图文检索（进行中）

### 3.1 已完成：模型可用性与维度截断验证

`scripts/smoke_embedding.py --self-test` 实测结果：

| 项 | 实测值 |
|---|---|
| 加载精度 | **bfloat16**（CUDA + BF16 支持） |
| 加载耗时 | 14.0 s |
| **显存占用** | **0.83 GiB**（理论 BF16 权重 1.39 GiB，实际更省） |
| query 编码 | **63.5 ms**（中位数，带 `task: search result \| query: ` 前缀） |
| 图像编码 | 3 张图共 473.9 ms ≈ **158 ms/张** |
| 数值健全性 | ✅ 无 NaN / Inf |
| 维度截断 128/256/512/768 | ✅ 截断后**全部重新归一化到单位范数** |
| 语义自检 | ✅ 棋盘 query 的 top1 = 棋盘图（4 个维度均正确） |

**这验证了任务书第 3 节的全部精度规则可落地**：
不用 FP16、用 BF16、`audio_config=None` 关音频、query 加前缀而图像不加、截断后重新归一化且查询与库同维度。

**与原论文差异**：原论文检索侧用 CLIP / SigLIP / OpenCLIP / BGE-VL 等；
本项目换成 **EmbeddingGemma 2**。→ **候选池构成改变，跨论文数字不可直接比对。**

### 3.2 待完成

- 真实 MRAG-Bench 数据上的 R@1 / R@5 / MRR × 维度，产出 `retrieval_by_dim.csv`
- 任务书对照要求「CLIP/SigLIP 或论文作者检索候选」→ 需补一个对照检索器

## 4. ⭐ 核心移植风险已解除：Gemma 4 的 True/False logit 打分

这是任务书风险 1（「Utility-MRAG 的 2B surrogate / 8B main 不是 EmbeddingGemma 2 / Gemma 4，
跨模型移植性能未经证实」）中**技术可行性**的部分。结论：**技术链路完全打通**。

### 4.1 阶段 1：分词兼容性（✅ 无问题）

Gemma 4 E2B 分词器（词表 262,144）实测：

| 字符串 | token id | 单 token |
|---|---|---|
| `True` | **4339** | ✅ |
| `False` | **9277** | ✅ |
| ` True` | 6288 | ✅ |
| ` False` | 8450 | ✅ |

作者 `TrueFalseLogitExtractor` 解析得到 `positive_token_id=4339`、`negative_token_id=9277`，
**`warn_if_multi_token()` 无降级警告**。

→ 论文式 (6) `score = ℓ(v_+ | I)` 在 Gemma 4 上**不存在分词层面的障碍**。

### 4.2 阶段 2：真实前向取 logit（✅ 打通）

`Gemma4ForConditionalGeneration` + `output_scores=True` 实测：

| 项 | BF16 (`device_map=auto`) | **4bit nf4 (`device_map={'':0}`)** |
|---|---|---|
| 模型加载 | 10.5 s | 10.2 s |
| 显存已分配 | 1.83 GiB | **6.28 GiB** |
| **参数设备分布** | ❌ **cuda:0=19.2%, meta=80.8%** | ✅ **cuda:0=100.0%** |
| 生成耗时 | 3.3 s | **1.0 s** |
| 首步 logits | `(1, 262144)` | `(1, 262144)` |
| `true_token_id` / `false_token_id` | 4339 / 9277 | 4339 / 9277 |
| `true_is_single_token` | True | True |
| 打分 | `score=-4.65625`, `p_true≈9.6e-8` | `score=-6.15625`, `p_true≈2.2e-7` |
| 生成文本 | `'False<turn|>'` | `'False<turn|>'` |

**作者的打分器可以原样复用**，参数（`positive_token_id` / `negative_token_id` / `score` 语义）与论文一致。

### 4.3 ⚠️ 发现的关键问题：BF16 下 `device_map="auto"` 会静默退化

BF16 时 E2B 权重 9.54 GiB > 7.1 GiB 可用显存，`accelerate` 报
`Some parameters are on the meta device because they were offloaded to the cpu`，
设备分布变成 **`cuda:0=19.2% / meta=80.8%`**，且显存只分配了 1.83 GiB。

**这不是可用的实验配置**——在此配置下测出的任何 `generation_ms` / 显存数字都不可信。
**必须显式量化并强制 `device_map={"": 0}` 全驻显存**，才能得到可比较的时延与显存数据。

### 4.4 显存实测与理论值的偏差（需在报告中原样记录）

| 模型 | 理论 INT4 权重 | **实测 4bit 显存** | 差值来源（已定位） |
|---|---|---|---|
| E2B | 2.39 GiB | **6.28 GiB**（加载后） | 未量化组件 + 大词表 |
| E4B | 3.72 GiB | **8.685 GiB**（加载后，**空输入**） | 同上，见下方分解 |

### 4.5 ⛔ E4B 在本机 8 GB 显存上**不可行**（已实测确认）

`scripts/diagnose_vram.py` 对 E4B 的模块分解（4bit nf4，`device_map={"":0}`）：

| 顶层模块 | 参数量 | dtype | 推断显存 |
|---|---|---|---|
| `model` | 5.724 B | bfloat16 + **uint8**（4bit 量化） | ≈ 4.0 GiB |
| **`lm_head`** | **0.671 B** | **bfloat16（未量化）** | **≈ 1.34 GiB** |
| 合计 | 6.395 B | — | ≈ 5.3 GiB |

实测：**加载完成、尚未输入任何数据时已占 8.685 GiB**（峰值 8.87 GiB），
而 GPU 总额仅 **8.00 GiB**；单图 448px、`max_new_tokens=4` 时峰值 reserved 达 **9.01 GiB**，
生成耗时 **23.0 s**（对比 E2B 的 **1.0 s**）。

**根因（关键发现，与直觉相反）**：

> **4bit 量化不覆盖 `lm_head` 与 embedding**。
> E4B 的 `lm_head` 为 `262144 × 2560 = 0.671 B` 参数，以 **bf16 未量化**存储，单此一项约 **1.34 GiB**；
> 而它对应的输入 embedding 是量化过的。这就是「参数量 × 0.5 字节」估算
> （预测 3.72 GiB）与实测 8.685 GiB 差 5 GiB 的主要来源。
> 超出总额的部分由 PyTorch 溢出到共享系统内存，通过 PCIe 逐层搬运，
> 因此生成时间从 1.0 s 恶化到 23.0 s（**23 倍**）。

**结论**：
1. **E2B 可用**（4bit 全驻显存，打分链路 1.0 s）→ 路径 **A0 / A1** 在本机可行。
2. **E4B 不可用**（超显存 8.7%，性能恶化 23 倍）→ 路径 **A2 / A3 在本机无法以可比的时延复现**。
   任务书风险 4 的警告（「作者仓库『需要约 16GB』不意味着本机一定能全流程复现」）**实测成立且更严重**。
3. 维度的视觉 token 固定为 **2520/图（448px）**，多图输入会线性放大 KV cache 与视觉激活，
   进一步压缩 E4B 的余量。

**可能的缓解方向（尚未验证，需实测）**：
- 跳过 `lm_head` / embedding 的量化豁免，改为 `llm_int8_skip_modules` 反向控制，或对 `lm_head` 单独做 int8/4bit；
- 降低输入图像分辨率以削减 2520 个视觉 token；
- 限制 `max_new_tokens` 与 batch 为 1，缩小 KV cache；
- 用 `device_map="auto"` 接受**受控**的 CPU offload，但必须如实记录时延（本实验的意义正是量化这个代价）；
- 8 GB 显存下若 A2/A3 不可行，则四路径对照应改为
  **「E2B 本地 + E4B 云端/他人机器」**并单列硬件差异，或把 E4B 换成 E2B 的量化-非量化对照。

## 5. 与原论文的差异汇总（**必须持续更新**）

| # | 维度 | 原论文 | 本项目 | 影响 |
|---|---|---|---|---|
| 1 | 检索器 | CLIP / SigLIP / OpenCLIP / BGE-VL / GME / VLM2Vec 等 | **EmbeddingGemma 2** | 候选池构成不同，数字不可直接比对 |
| 2 | surrogate | Qwen3-VL-2B (2.1B) / Ovis2.5-2B (2.6B) | **Gemma 4 E2B (5.123B)** | 代理更大，`N × Φ(M_surrogate)` 成本上升 |
| 3 | main | Qwen3-VL-8B / MiniCPM-V4.5 / Gemma3-12B / Ovis2.5-9B / InternVL3.5-8B | **Gemma 4 E4B (7.996B)** | 同家族不同规模，迁移假设更有利 |
| 4 | 精度 | 论文未明确 | **4bit nf4**（显存强制） | 量化会改变质量，必须单列 |
| 5 | 硬件 | 未详述 | RTX 4060 Laptop 8 GB | 影响时延与可复现规模 |
| 6 | 代码 | `Gemma3ForConditionalGeneration` 硬编码 | 需改为 `Gemma4ForConditionalGeneration` | **已定位，待改** |

### 5.1 需改动的文件清单（任务书第 3 节硬性要求）

| 文件 | 改动 | 状态 |
|---|---|---|
| `utility_mrag/models/gemma.py` | `Gemma3ForConditionalGeneration` → `Gemma4ForConditionalGeneration`；量化配置 | ⏳ 待改 |
| `configs/models/gemma4_e2b.yaml` | **新增**（family/role/dtype/device_map） | ⏳ 待建 |
| `configs/models/gemma4_e4b.yaml` | **新增** | ⏳ 待建 |
| 检索模块 | 接入 EmbeddingGemma 2 作为检索器 | ⏳ 待做 |

> ⚠️ 这些改动应放在**本项目自己的目录**（`src/`）或明确记录为对 `third_party/` 的补丁，
> 避免与作者原码混淆。

## 6. 尚未验证的边界（**不得对外宣称**）

- ❌ 未跑任何一条完整生成路径（A0/A1/A2/A3）→ 无 `generation_paths.jsonl`
- ❌ 未测 MCQ Accuracy、未测 retrieval harm
- ❌ 未构建 Oracle、无 `four_path_matrix.csv`
- ❌ 未做 20 题 manifest
- ❌ A-P0-2 的真实数据指标（R@1/R@5/MRR）未产出
- ⛔ **E4B 已确认在本机 8 GB 显存不可行**（§4.5）→ **A2/A3 路径暂时无解**，需先决定对策
- ❌ 四路径的质量—效率前沿、路由成本、证据干扰比例**全部未测**

**任务书原话**：「当前项目未运行这些模型，不应把本任务书当作实验报告。」
→ 截至本文件，本项目已运行的是：作者单元测试（✅23/23）、EmbeddingGemma 2 检索接口（✅）、
Gemma 4 **E2B** 打分链路（✅）、Gemma 4 **E4B** 显存诊断（⛔ 不可行）；**生成与端到端评测尚未运行**。

## 6.1 磁盘与缓存现状（重资源已移出工作区）

| 位置 | 内容 | 占用 |
|---|---|---|
| **工作区** `EdgeCoRAG-A` | 脚本 / 论文 / 代码 / 结果 | **≈ 0.16 GiB** |
| `E:\EdgeCoRAG-A-store\hf-cache` | 三个模型的 HF 权重缓存 | 25.92 GiB |
| `E:\EdgeCoRAG-A-store\venvs\venv-main` | `.venv-main`（junction） | 4.92 GiB |
| `E:\EdgeCoRAG-A-store\venvs\venv-mrag` | `.venv-mrag`（junction） | 4.62 GiB |
| pip 缓存 | **已清理** | 0 |

**C: 可用空间：50 GB → 89 GB。**

迁移手段为 `robocopy /MOVE` + **junction**，因为 junction 对进程透明，
无需修改 `HF_HOME` 与虚拟环境内的写死路径。迁移后已复验：
`.venv-mrag` 下作者测试 **23 passed**、`.venv-main` 下 `cuda True`/`bf16 True`、
EmbeddingGemma 2 从新缓存正常加载。可重复执行：`python scripts\bootstrap_store.py --apply`。

> 本机实测 `huggingface_hub` 的 xet 后端把数据直接放在 `snapshots/`，`blobs/` 为空，
> **没有因缺少符号链接支持而产生重复存储**。

## 7. 下一步

1. **决策 E4B 对策**（阻塞 A2/A3）：受控 offload / 换更小输入 / 云端执行 / 换对照设计
2. 取回 MRAG-Bench 数据，锁定 revision/hash，固化 smoke/dev/frozen 三个 split
3. 生成 20 题候选 manifest（A-P0-1 剩余部分）
4. 在真实数据上跑 EmbeddingGemma 2 检索 → `retrieval_by_dim.csv`（A-P0-2）
5. 改写 `gemma.py` 支持 Gemma 4（E2B 已验证可行），跑通 E2B 无检索生成（A-P0-3）
