# 检索与效用选择独立实验方案（retrieval_selection_protocol.md）

日期：2026-10-17。**本文件只做协议设计，不跑任何新的模型前向或检索。**

## 0. 前提与命名边界（不能覆盖本轮结果）

| 概念 | 定义 | 与本轮关系 |
|---|---|---|
| `official_retrieved_top3` | 数据集随附的已发布候选，按既有排名取 top-3（含 Incomplete） | **本轮 S1 就是这个**，名称与分数保留，不覆盖 |
| `reindexed_embeddinggemma` | 我方用 EmbeddingGemma 2 在**独立语料**上重检索的结果 | 未来路线，**不混入本轮表** |

两者是**不同 pool、不同结果表**。任何比较都要显式写 `pool_id`，不得把自主重检索叫作
「已发布候选」的加强版，也不得把官方候选冒称自主检索。

## 1. 检索器与嵌入口径（EmbeddingGemma 2）

| 项 | 取值 |
|---|---|
| 模型 | `google/embeddinggemma-2`（revision `914f7f89142e33e7`） |
| 精度 | BF16（CUDA 支持 BF16 时）；否则 FP32。**不用 FP16** |
| 主维度 | **768** |
| 对照维度 | 128 / 256 / 512（截断后） |
| 截断规则 | 取前 d 维后**重新归一化**（L2），查询与库同维度 |
| query 前缀 | `task: search result | query: `（文本 query 加前缀） |
| 图像侧 | 不加文本前缀；`config_kwargs={"audio_config": None}` 关音频 |
| 图像编码 | JPEG q95 重编码（原始字节不可得）；哈希与落盘字节同源 |

**维度对照目的**：量化「维度压缩对检索质量的代价」，与任务书 A-P0-2 对齐。
128/256/512 不是三套独立必做协议，是**同一检索器的维度消融**。

## 2. 检索器对照

**必须至少一个「有来源依据」的对照检索器**，否则无法判断 EmbeddingGemma 2 是否合理。
候选（按可取得性排序，最终择一）：

| 对照 | 依据 | 备注 |
|---|---|---|
| CLIP（OpenCLIP ViT-B/32） | 官方候选池产生方式未公开，但 README 称官方发布了语料用于检索；CLIP 是该类任务标准基线 | 需确认官方原始检索器是否即 CLIP |
| SigLIP 2 | 官方候选池命中率与 CLIP 风格一致 | 同上 |

**不选的**：不加来源依据的自造检索器；任何需要额外权重下载的检索器本轮不引入
（本批不下载模型）。

## 3. 指标定义（精确哈希命中 ≠ 语义支持）

| 指标 | 定义 | 分母 |
|---|---|---|
| **R@1 / R@5** | 检索返回的 top-k 中，**GT 图像精确字节哈希命中**的比例 | 有 GT 的题（非空） |
| **MRR** | 首个 GT 精确哈希命中位次的倒数的平均 | 有 GT 的题 |
| **GT 集合召回** | 任一 GT 命中（与「全部 GT 命中」分开报告） | 有 GT 的题 |
| **语义支持率** | 检索返回的图「确实支持答案」的比例（需人工/模型辅助语义判定） | 抽样子集 |

**关键区分**：
- **精确图像哈希命中**是确定性计算（字节 sha256），可自动；
- **语义支持率**不是哈希命中，需要看图判定，**不能**用 R@k 代替，也不能用
  「官方候选 55.9% 命中」反推语义支持。

**GT 不穷尽所有有效证据**：未命中 GT 不等于检索失败（可能有其它有效图）。
该限制在结果表显式声明。

## 4. 选择策略（cosine / utility / random）

| 策略 | 候选范围 | 选择数量 | 顺序 | 改变了什么变量 |
|---|---|---|---|---|
| **cosine** | 重检索 top-N 池 | k（与主实验对齐） | 按余弦降序 | 证据「相似度」作为选择依据 |
| **utility** | 重检索 top-N 池 | k | 按 Gemma 4 效用打分降序 | 证据「效用」替代「相似度」 |
| **random** | 重检索 top-N 池 | k | 固定种子随机 | 去除选择信号的下界对照 |

**随机种子**：固定（如 `20261017`），写入结果字段 `selection_seed`。
**对照含义**：cosine vs utility 回答「效用是否优于相似度」；random 是选择器下界。
三者**候选池相同**（同一重检索 top-N），只变「从中怎么选 k 张」，
从而分离「检索」与「选择」两个变量的贡献。

**规则冻结纪律**：任何选择阈值（如 utility 阈值、top-N 的 N）只能在**规定开发数据
（dev）**上确定；**不得**根据 frozen_test 结果反挑方案。已调试题（reviewed_ids）只进 dev。

## 5. Gemma 4 效用打分适配接口（本批只设计，不跑前向）

| 项 | 说明 |
|---|---|
| 打分语义 | 论文式 (6)：辅助二分类提问「Is this evidence helpful for answering the query?」取 "True" 末层 logit |
| 已核验基础 | Gemma 4 分词器 `True`=4339、`False`=9277 均为单 token；`Gemma4ForConditionalGeneration` 可取首步 logits（历史 `probe_gemma4_logits.py` 已验证 E2B 链路） |
| 待适配 | 作者 `utility_mrag/models/gemma.py` 硬编码 `Gemma3ForConditionalGeneration`，需改为 Gemma 4 |
| 依赖 | transformers 5.x（与检索环境 `.venv-main` 一致）；模型 Gemma 4 E2B（E4B 在 8 GB 不可行，见历史） |
| 输入 | 查询图/题面 + 候选证据图 → 辅助提问文本 |
| 输出 | 每候选 `score = ℓ("True")`（或 `p_true`） |
| 最小未来验证 | 先在小 dev 子集上确认能取到 logits 且排序稳定，再谈规模；本批不跑 |

## 6. 结果字段（未来，本批只声明）

每行必须含：`qid, pool_id, retriever_id, embedding_dim, top_k, selection_strategy,
selection_seed, retrieval_rank, retrieval_score, is_oracle`。
未知成本标 `未测`，不造数。真实检索指标与系统性能**待后续执行**，本批不产出。
