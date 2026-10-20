# Utility-MRAG（ACL 2026）复现可行性（A9）

日期：2026-10-20。**本文件只做可行性判断，没有下载数据、没有加载模型、没有开 GPU。**
证据来源：`Hcnaeg/utility-mrag` 仓库的 GitHub API 元数据与关键文件原文（读取时间 2026-10-20，`master` 分支），文件已落地在 `outputs/_utility_mrag/` 供复核。

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 仓库是否公开可读 | **是**。`Hcnaeg/utility-mrag`，MIT，默认分支 `master`，315 KB，90 个文件，最后推送 2026-07-04，未归档未禁用 |
| 数据是否随仓库发布 | **否**。原始数据集、图像语料、模型权重、API key 都不随仓库发布 |
| 论文主表数字是否随仓库提供 | **否**。`docs/expected_results.md` 里 Table 1/2/4 的目标值**全部是 `tbd`**，文中写"Replace `tbd` with the values reported in the paper after release" |
| 能否复现其主表（Table 1） | **有条件可以**：需要 ≥24 GB（全 bf16 五模型建议 ≥48 GB）GPU、`transformers<5` 的环境、以及对照论文 PDF 的数值；数据侧**不需要**我们拿不到的 Google Drive 语料（见 §3.2） |
| 与我们已冻结口径的关系 | **评分定义一致**（都取 `ℓ("True")` 原始 logit）；但**代理模型不同**（他们是 Qwen3-VL-2B，我们冻结的是 Gemma 4 E2B），**候选池不同**（他们是官方候选，我们冻结的是 EG2 自主检索池）→ 数字不可互换 |
| 不可复现的部分 | 论文数值本身（仓库未给）、Visual-RAG 表（另一数据集 + 付费 LLM judge）、作者用的模型 revision 与 retriever checkpoint（仓库未 pin）、其 Linux + flash-attn 环境 |
| GPU 量级（估算，非实测） | 只做 MRAG Table 1：**约 2.5–4.5 GPU·小时**（surrogate 6,765 次 + 生成 20,295 次），24 GB 卡可跑 2B/8B/9B，**12B bf16 需 ≥24 GB 且余量紧张（更可能要 ≥48 GB 或量化）** |

## 1. 仓库身份（可复核）

| 项 | 值 |
|---|---|
| repo | `Hcnaeg/utility-mrag` |
| 描述 | `[ACL 2026] Utility-Oriented Visual Evidence Selection for Multimodal Retrieval-Augmented Generation` |
| 许可 | **MIT**（`LICENSE`，1,085 B） |
| 默认分支 / 体积 / 文件数 | `master` / 315 KB / 90 |
| 最后推送 | 2026-07-04T12:42:23Z |
| 引用 | `luo2026utility`，ACL 2026 Vol.1 pp. 35091–35124（`CITATION.cff` + README） |
| 随仓库发布的产物 | 只有代码、配置、测试、toy 样例；**无**图片、权重、原始数据集、密钥 |

## 2. 方法要点（按仓库原文）

1. **代理模型打分**：小模型（配置默认 `Qwen3-VL-2B`）对每个候选图问"*Is this image helpful for answering the query?*"，取**首步生成时 `True` 的末层 logit** 作为 helpfulness。
2. **Top-K**：按 helpfulness 取 K ∈ {1,3,5}，交给更大的主模型生成答案。
3. **主模型**（`configs/experiments/table1_mrag.yaml`）：`Qwen3-VL-8B`、`MiniCPM-V-4.5`、`Gemma3-12B`、`Ovis2.5-9B`、`InternVL3.5-8B`。
4. **配置里写的选分键**：`selection: {template: helpfulness, score_key: true_logit, top_k: [1,3,5]}` —— 即主表用的是**原始 logit**，与我们的冻结口径相同。
5. **数据形态**：manifest 里每题带 `query`、`question_image_path`（仅 MRAG）、`candidate_images`（含 `source: gt|retrieved`）、`gt_image_ids`、`choices`、`answer`。

## 3. 数据与许可

### 3.1 申报情况

- `data/README.md`：原始数据集与图像语料**不随仓库发布**；MRAG-Bench 指向 HF `uclanlp/MRAG-Bench` + 官方 README 的 Google Drive 图像语料；Visual-RAG 指向另一个 GitHub（`Bingo-W/Visual-RAG`）。
- 许可：仓库自身 MIT；MRAG-Bench / Visual-RAG / 各模型 checkpoint 各按上游许可（原文明确提示）。

### 3.2 关键发现：主表**不需要** Google Drive 那份语料

README 的 "MRAG-Bench (zero-config)" 路径用 `scripts/prepare_mrag_bench_hf.py`，**直接从 HF 数据集的每题自带字段**（输入图 + GT + 官方 CLIP 候选）生成 manifest：

```bash
uv run python scripts/prepare_mrag_bench_hf.py \
    --output data/manifests/mrag_bench_candidates.jsonl \
    --image_dir data/images/mrag_bench --split test
```

也就是说：他们的候选池 = **数据集自带的 5 张官方候选**，与我们 S1 的 `official_retrieved_top3` 同源，而**不是**论文里那份独立检索语料。

对我们有两个直接后果：
1. **可行性**：我们被阻塞的"独立语料/Google Drive 不可达"不影响复现 Table 1（只影响"自主检索"这条线）。
2. **可比性**：他们的主表本质是"**在官方候选池内做 rerank**"，不是"自主检索 + 选择"。所以拿我们的 `eg2_shared_top10`（4,712 图池自主检索）结果去对他们的数字，是**两种证据条件混算**，不能并列成一张表。

## 4. 与我们冻结口径的对照（三者在数学上不可互换）

| 口径 | 定义 | 排序由什么决定 | 与其它两口径的关系 |
|---|---|---|---|
| **ℓ("True")**（我们冻结 / 他们 `score_key: true_logit`） | 首步 `True` 的**原始末层 logit** | `true` 本身 | 基准 |
| **p_pair(True)**（他们 `p_true`） | 只对 `[True, False]` 两 logit 做 softmax = σ(`true − false`) | `true − false` | 当 `false` 逐候选变化时，排序**可以与 ℓ("True") 不同**（单调性在差值上，不在 `true` 上） |
| **p_vocab(True)** | 全词表 softmax 的 `True` 概率 = exp(`true`)/Z | `true − log Z` | Z 逐候选变化 → 同样**不保证**与 ℓ("True") 同序 |

结论：**三者是三种不同的排序**，不能"任选一种"也不能互相换算后混用。我们的冻结口径取第一列，与他们的主表配置一致；若未来要做口径敏感性分析，必须按上表分别标注，不能只写"utility 分数"。

补充：他们的实现里还有 **multi-token 回退**（`"True"` 若被切成多片，就取第一片的 id，并把 `true_is_single_token=false` 记下来）。我们冻结时已核验 Gemma 4 的 `True`=4339 / `False`=9277 均为单 token；换成别的模型时必须重做这个核验，否则口径会悄悄变。

## 5. 复现所需资源

| 项 | 要求 | 我们现状 |
|---|---|---|
| Python / transformers | Python 3.11；`transformers >=4.57,<5`（Qwen3-VL 需 ≥4.57；Ovis2.5/MiniCPM 远程代码依赖 4.x API） | `.venv-main` 是 5.19.0（Gemma 4 需要），**不能**用；`.venv-mrag` 实测 **4.57.6**，满足 `>=4.57,<5` |
| torch | 2.12 / 0.27（CUDA 版按驱动；原文只说"matching your driver"，非硬 pin） | `.venv-mrag` 实测 torch **2.11.0+cu128**（tv 0.26.0），低一档但属可接受范围 |
| GPU | 原文："single CUDA GPU（≈16 GB is enough for the 2B models）"；主表五个模型 bf16 中 Gemma3-12B 权重约 24 GB | 本机 8 GB 不可行；B 的 24 GB 卡可跑 2B/8B/9B，12B 需量化（偏离论文设置） |
| 数据 | HF `uclanlp/MRAG-Bench`（我们本地已有该 revision） | **已具备**，无需新下载 |
| 额外依赖 | `uv sync --extra clip/eval/profile/datasets`；Visual-RAG 的 judge 需 `OPENAI_API_KEY` | 未安装；judge 需付费 API |

**量级估算（仅用于预算，非实测）**

- surrogate 打分：1,353 题 × 5 候选 = **6,765 次**单图前向（2B，bf16）。按 0.3–0.6 s/次 ≈ **0.6–1.1 h**。
- 生成：5 主模型 × K∈{1,3,5} × 1,353 = **20,295 次**。按 0.3–0.6 s/次 ≈ **1.7–3.4 h**（另加 5 次模型加载）。
- 合计 ≈ **2.5–4.5 GPU·小时**；按 1.48 元/时 ≈ **4–7 元**（另计数据盘/取回）。这是 MRAG Table 1 一项；Table 2 基线与 Visual-RAG 另计。

## 6. 不可复现 / 不可比的部分（必须写清）

1. **论文数值不可核对**：仓库 `docs/expected_results.md` 全部 `tbd`，没有随发布给出目标值。要对照必须拿 ACL 2026 论文正文（PDF/Anthology），且其数值是在**作者自己的模型 revision 与 retriever checkpoint** 下得到的，仓库未 pin 这些版本。
2. **模型 revision 未固定**：`configs/models/*.yaml` 只给 `model_name`（如 `Qwen/Qwen3-VL-2B-Instruct`、`google/gemma-3-12b-it`），没有 revision/hash。复现结果天然带版本漂移。
3. **与我们的证据条件不同**：他们 rerank 官方候选，我们用自主 EG2 检索池；我们的 S1（官方 top3）才是与他们同源的对照。两批数字不能合成一张表。
4. **Visual-RAG 部分**：需要第二个数据集 + LLM-as-judge（OpenAI），属于另一条线，不在本轮范围。
5. **环境不可移植到本机**：本机 8 GB 显存 + Windows（无 flash-attn，只能用 `sdpa`），不是他们的测试环境；本机只能做"零模型"的代码级核验。
6. **代理模型不同**：我们冻结的是 Gemma 4 E2B 作 utility scorer，他们是 Qwen3-VL-2B；即使口径相同，"谁打分"也改变了结果含义。要做同口径对比，必须显式声明 scorer。

## 7. 如果将来要复现，最小范围建议（本轮不执行）

1. 环境：单独 venv（`transformers` 4.57.x + torch 2.12 轮子），不与 `.venv-main` 混用。
2. 数据：直接用本地 HF `uclanlp/MRAG-Bench@43620fde…`；`prepare_mrag_bench_hf.py --limit 20 --num_candidates 5` 先跑通，再全量。
3. 模型：先只跑 **surrogate(Qwen3-VL-2B) + 一个主模型（Qwen3-VL-8B）**，K=1/3 → 2 × 1,353 ≈ 4,059 次生成，约 0.5–1 h；确认流程后再加其余四个模型。
4. 数值：只报我们自己的实测，明确标"未与论文数值对照（仓库未提供 `tbd` 之外的参考值）"。
5. 停止条件：显存不足、transformers 版本冲突、模型卡需登录（`docs/model_setup.md` 提到 gated models 需 HF token）任一成立即停。

## 8. 与我们三条研究线的关系

| 我们的线 | 与 utility-mrag 的关系 |
|---|---|
| 冻结五模型基线（S0/S1/S2） | S1 = 官方候选 top3，**与他们 Table 1 的证据条件同源**，但因主模型集合不同（我们是 Gemma4/Qwen3-VL/Qwen3.5），不能直接对表 |
| 自主检索 + 选择（本轮接口 v1） | 我们的 EG2 池 + cosine/utility/random，是**他们没有做的**条件（他们只在官方候选内 rerank） |
| 四路径 / 路由 | 与 utility-mrag 无关，不借用其数字 |

## 9. 复现证据（本地可复核）

- 仓库元数据与文件原文保存在 `outputs/_utility_mrag/`：`README.md`、`docs/reproduction.md`、`docs/expected_results.md`、`data/README.md`、`configs/experiments/table1_mrag.yaml`、`configs/models/*.yaml`、`utility_mrag/scoring/true_false_logits.py`、`tests/test_true_false_logits.py` 等。
- 复算方式：按 GitHub API 重新拉取即可（`api.github.com/repos/Hcnaeg/utility-mrag/contents/<path>?ref=master`）。
