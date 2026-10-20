# A4：a21 归因 dry-run（只有 2 题 live，先跑通判定链）

日期：2026-10-20。**B 目前只有 `mragb:10` 与 `mragb:1049` 的 live 数据，其余 3 题待 GPU。**
本文件做两件事：① 证明 `a21` 的判定链在"没有数据"时会老实报 `insufficient_data`；② 用我自己的复现结果回答"**1049 是否落在批大小签名内**"。

## 1. dry-run：空表输入 → 5 题全部 `insufficient_data`

```bash
python a-side/scripts/a21_attribute_exclusion.py \
  --rows a-side/reports/next_stage_20261020/attribution_dryrun/threshold_rows.template.csv \
  --out  a-side/reports/next_stage_20261020/attribution_dryrun/attribution_template_run.json
```

输出（rc=0，**没有任何猜测性标签**）：

| qid | label | evidence | missing_evidence |
|---|---|---|---|
| mragb:1049 | `insufficient_data` | `{}` | 该题没有任何行 |
| mragb:1051 | `insufficient_data` | `{}` | 该题没有任何行 |
| mragb:1062 | `insufficient_data` | `{}` | 该题没有任何行 |
| mragb:1117 | `insufficient_data` | `{}` | 该题没有任何行 |
| mragb:10 | `insufficient_data` | `{}` | 该题没有任何行 |

**结论**：判定链能跑通、缺数据时**不会**输出 dtype/批大小之类的标签。这与"无数据不归因"的纪律一致。

## 2. 1049 是否落在批大小签名内？—— 用我自己的复现结果回答

来源：`outputs/rank_stability/rank_stability_by_qid.csv`（24 个变体 × 1,203 题），5 道 smoke 题的翻转情况：

| 变体组 | 会发生顺序变化的题 | 与实测 `{1049,1051,1062}` 是否吻合 |
|---|---|---|
| 只改**查询批大小**（`qbf16_b1` vs `qbf16_b16`，同一归一化） | **无（5 题全不变）** | ✗（一题都不中） |
| 改 **dtype 或归一化位置**（`idxbf16↔idxfp32` / `model_norm↔fp32_renorm`，20 个变体） | **`10`、`1049`、`1117`** | ✗（被翻转的是另一组：含 10/1117，不含 1051/1062） |
| 同配置重复 | 无 | — |

**没有任一变体恰好翻转 `{1049,1051,1062}`**（程序化检查：`any(set(v)==target) == False`，见 `variant_flip_matrix.json`）。

由此得到的判定口径（**不是结论**）：

- **`1049` 在"dtype/归一化"这一类扰动的签名内**（20/24 个变体都会翻转它），但它同时会带动 `10` 与 `1117` —— 而实测这两题**没有**变。所以**单凭 1049 不能定类**。
- **`1051` 与 `1062` 在我的所有变体里都没有被翻转过**：说明它们在 B 的环境里发生变化，需要**比"我测过的这些口径差"更大的扰动**，或者**语料不同**（我的是数据集内部图池 4,712，B 的索引是 18,955 —— 见 `index_receipt_adjudication.md`）。
- **批大小在本复现里一题都没中**（5/5 全不变），与"批大小不是原因"一致。

## 3. 什么数据能把它定下来（a21 需要的字段）

| 目的 | 需要 B 给 | a21 会怎么用 |
|---|---|---|
| 判断是否集合变化 | ② 的 `qid,source,rank,sha256,score`（两侧各 10 行） | 先比 sha 集合；不同即 `index_composition` |
| 判断是否精确并列 | 同上 | 被互换两候选的 `live_gap/history_gap < 1e-9` → `exact_tie_sort` |
| 判断归一化位置 | 同上 | Δ 对 history 分数回归：`r²≥0.8` 且斜率 1e-4~2e-2 → `normalization_locus` |
| 判断解码路径 | 同上 | 同题内分化（部分 \|Δ\|<1e-6、部分 ≥1e-3）→ `decode_path` |
| 判断 dtype | ④ 编码参数 + ② | `max\|Δ\|≤3e-3`、符号平衡 ≥0.2、dtype 不同 → `dtype` |
| 判断批组成 | ④ + ③ 向量指纹 | 指纹不同但 dtype/归一化相同 → 指向批组成（`batch_composition`） |

## 4. 纪律（写死）

- **不用历史分数冒充 live**：缺 live 就写 `insufficient_data`。
- **不把 2 题结论推广到 5 题**：`mragb:10` 只能作"未变化对照"，不能当样本。
- **不因为"`1049` 在 dtype 签名内"就写"1049 是 dtype 问题"**：它要求同时解释 `10/1117` 为何没变，而目前解释不了 —— 这正是需要 B 的 ②③④ 的原因。

## 5. 产物

| 文件 | 说明 |
|---|---|
| `a-side/reports/next_stage_20261020/attribution_dryrun/threshold_rows.template.csv` | 空模板（只有表头），给 B 的 ② 对齐格式 |
| `a-side/reports/next_stage_20261020/attribution_dryrun/attribution_template_run.json` | dry-run 输出（5 题 `insufficient_data`） |
| `a-side/reports/next_stage_20261020/attribution_dryrun/batch_signature_check.json` | 5 题在 3 个代表变体下的 `order_equal / top3_equal / min_adjacent_margin` |
| `a-side/reports/next_stage_20261020/attribution_dryrun/variant_flip_matrix.json` | 24 变体 × 5 题的翻转集合 |
