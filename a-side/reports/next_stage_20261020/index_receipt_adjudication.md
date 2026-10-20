# 索引行数三方对账：三种假设与"回执里应出现什么"（A3）

日期：2026-10-20。**本文件只列假设与可证伪的特征值，不下结论。** B 的回执到位前，任何"18,955 就是 X"的写法都不允许。

## 0. 三个已知数字

| 口径 | 数值 | 来源 |
|---|---:|---|
| 题目数 | 1,353 | 数据集 `test` split |
| 图像**实例**数（每题 1 查询 + 5 GT + 5 候选，Incomplete 题 1 GT） | **14,475** | `outputs/census/image_census.json`（逐 parquet 统计） |
| **唯一内容**数（sha256(JPEG q95 字节) 去重） | **4,712** | `corpus_v1/corpus_meta.json`；原始字节口径同为 4,712 |
| 已发布 smoke 报告里的索引条目 | **18,955** | `EdgeCoRAG_同机端到端smoke实测_20261020.md` |

算术观察（**不是结论**）：`18,955 − 14,475 = 4,480`；`18,955 − 4,712 = 14,243`。两个差都没有独立来源解释，不能反推。

## 1. 假设 H1：按"每题的 14 个实例"计数（同图多实例，不去重）

若索引是把每题的查询图、GT、候选逐条入册（同一张图在不同题下算多行）：

| 字段 | 应出现的值 |
|---|---|
| `index.entries` | **14,475**（不是 18,955） |
| `dedup.by_identity` | `false` |
| `dedup.kept_duplicates` | **9,763**（= 14,475 − 4,712） |
| `row_order.rule` | `question_order` 或 `insertion_order` |
| `counts.*` | 1,353 / 14,475 / 4,712 |
| `sources[]` | 通常 2 条：题目清单 + 语料清单（都来自 HF 数据集） |
| 交叉检验 | 索引里重复内容的出现次数之和 = 14,475 |

**H1 被证伪的条件**：`index.entries != 14,475`，或 `dedup.by_identity=true`。

## 2. 假设 H2：按唯一内容建索引，但保留了副本（去重不彻底）

| 字段 | 应出现的值 |
|---|---|
| `index.entries` | > 4,712 且 < 14,475（若真去重）；**或** = 14,475（若完全没去重） |
| `dedup.by_identity` | `true` |
| `dedup.kept_duplicates` | 按本表应为 **0**；若 >0 说明去重逻辑有例外（需注明例外条件） |
| `row_order.rule` | `sha256_asc`（去重后通常按身份排序） |
| `identity.rule` | `sha256_jpeg_q95` 或 `sha256_raw_bytes` |
| 交叉检验 | 索引内 sha 去重后 == `counts.unique_contents` |

**H2 被证伪的条件**：`dedup.by_identity=false`，或去重后条目数仍显著大于唯一内容数。

## 3. 假设 H3：索引里含额外语料（不是数据集自身的图池）

| 字段 | 应出现的值 |
|---|---|
| `index.entries` | **18,955**（或与之相近），且 ≠ 14,475、≠ 4,712 |
| `counts.unique_contents` | **> 4,712**（说明图池比数据集更大） |
| `sources[]` | **≥3 条**，其中至少一条是**非** `uclanlp/MRAG-Bench` 的语料来源（例如作者语料、另一个 gallery），并给出其 sha256 |
| `identity.rule` | 可能与我们的 q95 口径**不同**（若是原始字节或别的重编码，必须写明） |
| 交叉检验 | `index.entries − 4,712` 能由该额外来源的规模解释 |
| 后果 | **两批结果的证据条件不同**：`reconciliation.verdict = matches_neither`，在 B 补出额外来源前不得配对 |

**H3 被证伪的条件**：`sources[]` 全部指向 HF 数据集、且 `counts.unique_contents == 4,712`。

## 4. 判定所需的**最小**字段集（任何一条缺失就写"数据不足以判定"）

1. `index.entries`（唯一的硬数字）
2. `dedup.by_identity` + `dedup.kept_duplicates`
3. `identity.rule`（原始字节 / q95 / 其他）
4. `row_order.rule`（是否按 sha 升序）
5. `sources[]` 的条数与每条的 sha256（用来判断是否含额外语料）
6. `counts.unique_contents`（若 B 另有语料，这个数会大于 4,712）
7. `corpus_encode.batch_size` 与 `dtype.storage`（用于解释"为什么当时能跑出 18,955 条"）

## 5. 三种假设下 A 侧的对账口径

| 假设 | `reconciliation.verdict` | 允许的后续动作 | 禁止的表述 |
|---|---|---|---|
| H1 | `matches_instances` | 可逐题配对；重排/去重差异按"实例 vs 内容"解释 | 不能说"索引多了 4,480 张新图" |
| H2 | 依 `entries` 而定（4,712 → `matches_unique`） | 可配对；按内容对齐 | 不能把"条目多"当成图多 |
| H3 | `matches_neither` | **只能做机制分析**，不能把两侧排名/分数放进同一张表 | 不能说"同一索引下复现" |

## 6. 与逐题归因（`a21_attribute_exclusion.py`）的关系

- 若 `verdict = matches_neither`，`a21` 会在每道题的输出里附 `caveat`：即使逐题数值特征匹配某一类（dtype/归一化/解码/批组成），也**不能排除索引成分差异**，归因只能是"候选类"。
- 若 `verdict = matches_instances` 或 `matches_unique`，`a21` 的逐题归因才是完整结论。

## 7. 明确未做的事

- 没有下载任何语料去凑 18,955。
- 没有把 `18,955 − 14,475 = 4,480` 解释成"额外语料"——那只是一个算术差，H3 需要 `sources[]` 来支撑。
- 没有修改 36 个产物或任何索引/排序结果。
