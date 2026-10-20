# 统一检索与选择接口 v1（冻结）

日期：2026-10-20。协议串：**`a-side/retrieval-interface-v1`**。
本文件是 A 侧检索/候选/选择/证据顺序的唯一权威口径；B 直接消费 §7 的产物，不必自己再建一套检索流程。

## 0. 这个接口解决什么

上一轮的排序差异定位（`A_retrieval_consistency.md`）证明：
- 算术/排序实现**不是**差异来源（0 条改序）；
- 真正的一阶差异来自**口径**：归一化位置（bf16 内 vs float32 重归一化，分数最大差 8.1e-3）、编码 dtype（bf16 vs fp32）、解码路径（原始字节 vs q95 重编码，向量差最大 1.4e-2）；
- 排序脆弱性普遍存在：83.3% 的题 top10 最小相邻分差 < 1e-3。

因此本接口把"口径"写死，并把残余风险显式标注（§6 `order_fragile`），而不是靠"双方小心一点"。

## 1. 版本与哈希（缺一项即不是本协议）

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench` rev `43620fde4044bb150e158c67ad7af6b6b11e1da2`，split `test` |
| 编码器 | `google/embeddinggemma-2` rev `914f7f89142e33e77833254d9c9b90c3cef7303b` |
| 权重文件 | `model.safetensors` sha256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79` |
| 配置 | `config.json` `b8f1e9931b57fbc054acdb445c41765d55b0074c58d145fa82839941ad1b5bb3`；`processor_config.json` `168f6a08522f3ce5dea596d94d003af2fd691742d4f41fe1f9d8cce76bfbf69c`；`preprocessor_config.json` `ea2ae257e901064abdd98dceb19f2b0da06af600bed15e0f99f5c85c37ee9d78` |
| 运行栈 | torch `2.11.0+cu128`、torchvision `0.26.0+cu128`、transformers `5.19.0`、sentence-transformers `6.1.0`、Pillow `12.3.0`、numpy `2.5.2` |
| 语料 | `corpus_v1`，4,712 个唯一内容，`content_digest` `31ade7b7e2454d0b9fcd58568247dd2a6862e15273fdd65e1d12ed50e373264e` |
| 产物清单 | `a-side/retrieval_if_v1/artifacts.json`（36 个文件 + 逐文件 sha256/字节/行数，合计 13,010,233 字节） |

## 2. 候选身份与语料（这是最容易被各自重建的一步）

| 项 | 冻结值 |
|---|---|
| 字节形态 | **JPEG q95 重编码后的字节**（数据集 parquet 里的 `struct<bytes>` 解码后按 q95 重新编码，再落盘；与既有 `packages/*` 和 `handover/samples` 完全同源） |
| 身份 | `sha256(上述字节)`，写为 `image_id` |
| 唯一性 | 同一 `image_id` 只保留一行（内容去重）。4,712 行 |
| 行序 | `image_id` 升序（**与题目顺序、角色、发现顺序无关**） |
| 角色映射 | `occurrences.csv`：每个 `(qid, role, rank)` 实例 → `image_id`（role ∈ query / gt / official_retrieved），共 14,475 行 |
| 与原始字节的关系 | 原始字节 sha256 亦为 4,712 个唯一值，与 q95 身份**一一对应**（两口径唯一数相等即证双射；200 次抽检 200/200 同一映射） |

**B 侧校验方法（不需要我传图片）**

```bash
# 1) 用 B 自己的数据集副本重建语料，逐文件复算 sha
python scripts/a06_build_corpus.py --verify
# 2) 比对 content_digest 与 corpus_manifest.csv 的 sha256 序列
```

**必须声明的语料边界（不能写成"复现了论文的检索语料"）**

本语料是**数据集内部图池**（数据集中出现过的全部图像的唯一内容），它天然偏相关：GT 唯一 3,618、官方候选唯一 1,558、交集 1,545。所以它的命中率明显高于历史缓存：

| | 本接口（4,712 图池） | B 侧历史缓存 |
|---|---:|---:|
| 768 维 top10 any-hit | 799/1033（77.35%） | 560/1033（54.21%） |

两者**不是同一语料**，数值不可互换。已发布 smoke 的索引规模 18,955 无法由公开数据集复现（实例 14,475 / 唯一 4,712），需要 B 的索引构建回执；在拿到之前，本接口的定位是**协议一致、可哈希复现的内部检索条件**，不是论文的独立检索语料条件。

## 3. 编码与打分（逐字实现要求）

```
解码：PIL.open(落盘 q95 字节).convert("RGB")     # 不缩放，不裁剪
模型：sentence-transformers SentenceTransformer(MODEL_ID, revision=REV,
        config_kwargs={"audio_config": None}, model_kwargs={"torch_dtype": torch.float32})
编码：.encode([{"image": im}], batch_size=1, normalize_embeddings=False)
      # 图像侧不加任何文本前缀；查询图同样按图像编码（本数据集的 query 是图像）
归一化：v32 = v.astype(float32); v32 /= max(||v32||, 1e-12)      # float32 层归一化
算术：torch.backends.cuda.matmul.allow_tf32 = False
      torch.backends.cudnn.allow_tf32 = False
打分：score = V32 @ q32            # numpy float32（BLAS），逐题
排序：order = lexsort(keys=(-score, image_id))     # 主键分数降序，次键 image_id 升序
```

**为什么必须是 fp32**：实测 fp32 下查询批大小 16→1 的排序差异 **0/1203**；bf16 下同样比较有 187/1203 改序、36 条改集合。fp32 的代价是编码变慢（本机 4060 上语料 0.33 s/图，单张查询约 0.4 s），这是**协议可复现性**换来的，成本实测另表记录。

**不需要固定批大小的部分**：语料编码批次不影响结果（fp32 下已证），但为了可复现仍要求写进回执。

### 3.1 栈依赖：`0/1203` 只绑定 A 的栈

上面那句"fp32 下批大小 16→1 排序差异 0/1203"是在 **A 的栈**上测的：

| 组件 | A 栈（测 0/1203 的环境） | B 服务器 / round-1 |
|---|---|---|
| torch | `2.11.0+cu128` | `2.8.0+cu128` |
| torchvision | `0.26.0+cu128` | `0.23.0+cu128` |
| Pillow | `12.3.0` | `11.3.0` |
| numpy | `2.5.2` | 未记录 |
| transformers | `5.19.0` | `5.19.0` |

**结论口径**：`0/1203` 是"A 栈内的性质"，**不是跨栈承诺**。B 必须用自己的环境跑 `a18_batch_sensitivity.py` 产出一份回执，跨栈是否一致以该回执为准；未跑之前，任何跨栈复用都必须标注"栈未验证"。

**为什么可能不同（不夸大，也不隐瞒）**：

- 编码器前向在 fp32 下仍受 cuDNN / cuBLAS / GPU 架构影响，kernel 选择与归约顺序可能带来 ~1e-7 量级的差异；这一步**无法保证逐位一致**，只能保证"是否改变排序"可测。
- 打分用的是 numpy float32 BLAS（CPU），BLAS 实现（MKL / OpenBLAS / Accelerate）与 numpy 版本不同会改归约顺序，量级同样在 1e-7。
- Pillow 版本影响解码结果（对 q95 文件重新解码的像素是否逐位相同）；Pillow 11.3 → 12.3 之间的 JPEG 解码路径是否有变化，A **没有证据**，标"未验证"。
- 由此可预期：与 1e-7 同量级的差异**只可能**在相邻分差 < 1e-6 的题上改序（本语料 1033 题中仅 1 题落在该档，见 `outputs/rank_stability/arith_variants.json` 的分档翻转率）。但这是推理，不是实测；以 `a18` 回执为准。

**`a18` 用法**（B 侧，只跑编码与排序，不涉及生成）：

```bash
python a-side/scripts/a18_batch_sensitivity.py --schema      # 先看回执字段
python a-side/scripts/a18_batch_sensitivity.py --self-check  # 纯逻辑自检，不需要模型/GPU
export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1
python a-side/scripts/a18_batch_sensitivity.py \
    --qids-file a-side/splits/smoke_20.v2.txt \
    --dtype fp32 --batches 16,1 --topk 10 \
    --weights-sha256 <model.safetensors 的 sha256> \
    --out receipt_a18_<你的栈>.json
```

回执核心字段：`results = {changed_order, changed_set, changed_top3, total, flip_rate}`，`verdict = stack_invariant | stack_sensitive`。

**判定阈值（写死，不许事后调整）**

| 条件 | verdict | 报告必须怎么写 |
|---|---|---|
| `changed_order == 0` **且** `changed_set == 0` | `stack_invariant` | 可写"该栈上批大小不影响排序"，并注明回执 sha256 与栈信息 |
| 其它情况 | `stack_sensitive` | 必须写 **"A 栈的 0/1203 不能外推"**，列出**改序题号**与该题 top10 的**最大分差**，并给出"统一到哪一栈"的建议；`changed_top3 != 0` 时还要说明选中的 3 张是否改变（直接影响下游输入） |

`stack_invariant` 表示该栈上批大小不影响排序；`stack_sensitive` 表示必须按"候选池固定顺序"消费，不能重排。
**不允许**用"基本一致""近似通过"等措辞收口：只有 0/0 才算一致。

## 4. 候选池构建（无自匹配 + 补足）

```
1) 全库打分                      score = V32 @ q32
2) 按 (-score, image_id) 排序
3) 剔除 image_id == 查询图 image_id 的行（其 query 角色身份见 occurrences.csv）
4) 取前 10  →  pool_id = "eg2_shared_top10"
5) 若剔除后不足 10，按原序补足，并置 refill_used=1（如实记录，不静默补齐）
```

- `is_self_removed` 字段恒为 0（被剔除的行不进入产物），自查指标在 `pool_quality/*`：`self_removed=1`、`n_candidates=10`。
- **不允许**用 gold/答案参与任何一步；gold 只在评分与 Oracle 分析中使用（§8）。

## 5. select3（三策略，共用同一候选池）

| 策略 | 规则 | 顺序 |
|---|---|---|
| **cosine** | 取候选池前 3 | 分数降序（即 rank 1,2,3） |
| **random** | 题内派生种子抽样 3 个（不放回） | `pcg64((qid_num*1000003+20261017) % (2^63-1))` 抽下标后**按分数降序**排列 |
| **utility** | 由 **B 回传** 每个候选的效用分数，取前 3 | 分数降序；并列按 `image_id` 升序 |

**效用打分口径（冻结，不再"任选"）**

- 取值为论文式 (6) 的 **`ℓ("True")` 原始 logit**（不是 p(True)、不是 True/False 二分类归一化概率；三者不是等价排序）。
- 打分模型：Gemma 4 E2B-it，BF16、无量化、thinking 关闭、greedy，固定 revision 与模板（模板由 B 侧 `shared_visual_mcq_v1` 与效用辅助问句共同决定，B 需把模板哈希写进回执）。
- 输入顺序：**按本接口候选池的 rank 顺序**逐个前向（或按固定批量大小整批）；B 必须回执 `utility_input_order` 与 `utility_batch_size`。

### 5.1 分工边界：B 只交分数，选 3 张与顺序由 A 的 `a15` 完成

这一条是为了避免"B 自己挑 3 张"导致两边选择逻辑不一致：

| 步骤 | 归属 | 说明 |
|---|---|---|
| 10 个候选及其身份 | **A** | `pools/<cohort>__dim<D>__top10.csv`，rank 1..10 |
| 每个候选的效用分 | **B** | 只回传 `qid,sha256,score` 三列；不筛、不排、不取前 3 |
| 选 top3 + 并列打破 + 顺序 | **A** | `a15_materialize_packets.py --strategy utility`：分数降序、并列按 `sha256` 升序、slot 1..3 |
| 物化证据包与 sha 复算 | **A** | 输出 `evidence_index.csv` / `evidence_list.jsonl` / `verify.json` |

**B 回传的分数表格式（严格）**

```csv
qid,sha256,score
mragb:10,83307f79a1c0...,0.812
mragb:10,df5cb3654e22...,0.408
```

要求：每题 10 行（候选池里那 10 个 sha 必须全覆盖）、`score` 为数值、不许多列、不许改 sha。

**可复制的完整 CLI（A 侧执行）**

```bash
export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1          # 或 --corpus 显式指定

# 1) cosine / random：直接物化
python a-side/scripts/a15_materialize_packets.py \
    --cohort dev_150 --dim 768 --strategy cosine \
    --corpus "$EDGECORAG_CORPUS" \
    --out  "$HOME/edgecorag/packets/dev_150_dim768_cosine"

# 2) utility：拿到 B 的分数表后物化（选 top3 由本脚本完成）
python a-side/scripts/a15_materialize_packets.py \
    --cohort dev_150 --dim 768 --strategy utility \
    --scores "$HOME/edgecorag/b_utility_scores_dev_150_dim768.csv" \
    --corpus "$EDGECORAG_CORPUS" \
    --out  "$HOME/edgecorag/packets/dev_150_dim768_utility"
# 分数缺任何候选 → 退出码 3，拒绝物化（不会用不完整分数凑 top3）
```

路径解析规则：`--corpus` > 环境变量 `EDGECORAG_CORPUS` > 报错（不再硬编码任何平台路径）；接口目录同理，`--iface` > `EDGECORAG_IFACE` > 仓库内 `a-side/retrieval_if_v1`。

## 6. 残余风险标记（不许假装不存在）

`pool_quality/<cohort>__dim<D>__margins.csv` 逐题给出：
`top1_score, top2_score, top3_score, gap_top1_top2, gap_top1_top3, mean_top10, min_adjacent_margin`。

- **`min_adjacent_margin < 1e-3` 的题**：在不同口径下 top10 内部顺序**不可复现**（实测该档翻转率 13.4%，更小档 40%+）。
- 这类题的下游结论必须带标记；如果 B 的流程会重排/重选，必须使用本接口产物的固定顺序，而不是重新计算。
- 建议在结果表里加一列 `order_fragile`（= `min_adjacent_margin < 1e-3`），并在分析里分层报告。

## 7. 产物清单（B 直接消费）

```
a-side/retrieval_if_v1/
  pools/<cohort>__dim<D>__top10.csv          qid,pool_id,retriever_id,embed_dim,rank,sha256,score,is_self_removed,refill_used
  select3/<cohort>__dim<D>__cosine+random.csv qid,strategy,embed_dim,slot,sha256,score,selection_seed,order_rule
  pool_quality/<cohort>__dim<D>__margins.csv 逐题分数结构与脆弱度
  metrics/retrieval_metrics_by_dim.csv       any-hit/set-recall/all-GT/MRR（按维度与 cohort）
  metrics/retrieval_metrics.json             口径定义 + 纪律声明
  packages/smoke_20_dim768_cosine/           逐图物化示例（20 题 80 图，sha 全对）
  artifacts.json                             36 个文件的 sha256/字节/行数
```

cohort × 维度：`smoke_20 / dev_150 / frozen_test` × `768 / 512 / 256 / 128`。
**holdout（`internal_holdout.v2.txt`）不产出任何产物**，避免评测面扩大。

对 B 的最小物化方式（不需要 1 GB 图片包）：

```bash
# B 侧已有数据集副本 → 建 corpus_v1（约 190 s）→ 物化任意 cohort/维度/策略
export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1
python a-side/scripts/a06_build_corpus.py --store "$EDGECORAG_CORPUS" --verify
python a-side/scripts/a15_materialize_packets.py --cohort dev_150 --dim 768 --strategy cosine \
    --corpus "$EDGECORAG_CORPUS" --out "$HOME/edgecorag/packets/dev_150_dim768_cosine"
# 物化时逐文件复算 sha，verify.json 里 mismatch 必须为 0
```

维度/策略的选择准则见 `selection_policy.md`（L1 检索层用 `any-hit@10` + 等价带，L2 用 dev 生成准确率；`order_fragile` 题**分层报告但不剔除**）。

## 8. gold 的使用边界（写进协议，不只是口头约定）

| 允许 | 禁止 |
|---|---|
| 评分（`strict_choice_v1`） | 进入候选池、排序、选择、prompt 组装 |
| S2 的 GT 证据 Oracle 条件（显式标注 `is_oracle=true`） | 用 GT 命中率调阈值、选维度、选策略 |
| 离线错误分析（明确标注"已观察数据上的事后分析"） | 把 GT 命中当作语义支持或泄漏证明 |

## 9. 什么时候必须升版本

以下任一变化必须开新协议串（`...-v2`）与新目录，不得覆盖 v1 产物：

1. 语料组成/身份口径/行序变化；
2. 编码器 revision、dtype、归一化位置、解码路径变化；
3. top-k / select-k / 排序键 / 抽样种子规则变化；
4. 效用打分口径（logit ↔ 概率 ↔ 二分类）变化；
5. 模板或输入顺序规则变化。

**变更登记要求**：新版本必须同时给出 `artifacts.json` 与 `corpus_meta.json`，并跑一次 `smoke_20` 的一致性复核，才能用于正式规模实验。

## 10. 已知未完成（不要写成已完成）

- 论文的**独立检索语料**（论文 Table 3 的 CLIP 检索器 + 其语料）仍不可得：Google Drive 域不可达、许可未声明。本接口不宣称复现该条件。
- 18,955 索引的构成未解（待 B 回执）。
- 效用分数的**顺序敏感度**未实测（需要 E2B 前向）。
- 正式规模成本（索引驻留、查询编码、检索、utility、切换）未测，只有接口与自检（见 `cost_measurement_interface.md`）。
