# index_receipt 字段映射表（B 侧可直接填，不是"未知量"）

日期：2026-10-20。**目的**：解除 "字段未知" 的误判——下列字段全部可以由 B 从 round-1 的交付包里直接读出并填值，不需要重新实验。
模板：`index_receipt.example.json`；校验：`a20_validate_index_receipt.py`（`errors=[]` 才算过）。**未回传才留 `null`；已知值必须填。**

## 1. 直接填（round-1 包内已有）

| 字段 | 填什么 | 允许值 / 说明 | a20 会检查 |
|---|---|---|---|
| `identity.rule` | `sha256_raw_bytes` | 语义＝**源 JPEG 字节的 sha256**；身份字符串格式在 `identity.notes` 写成 `image:<sha256>` | 必须是枚举值之一 |
| `identity.notes` | 例如 `身份字符串 image:<sha256>；源为 round-1 包内 JPEG 原始字节` | 自由文本 | — |
| `dedup.by_identity` | `true` | 按身份去重 | 布尔 |
| `dedup.kept_duplicates` | `0` | 18,955 个身份互不重复 | 去重为 true 时必须是 `0` |
| `dtype.storage` | `float32` | 索引向量落盘精度 | 枚举 |
| `dtype.compute` | `bfloat16` | 编码前向精度 | 字符串 |
| `dtype.tf32` | `false` | — | 布尔 |
| `normalization.locus` | `post_cast_float32` | 即"编码后转 float32 再 L2 归一化" | 枚举 |
| `normalization.applied_to` | `corpus_and_query` | 语料与查询同一口径 | 枚举 |
| `normalization.vector_norms_observed` | 实测范数范围，如 `1.000` | 未测写 `null` | — |
| `corpus_encode.batch_size` | `4` | round-1 建索引时的批大小 | 整数/字符串/null |
| `row_order.rule` | `insertion_order` | 即"原始语料顺序"，18,955 行与索引逐行一致 | 枚举 |
| `row_order.explicit_tiebreak_key` | 按实情：并列由行序决定填 `false`，另按 sha 决定填 `true` | 布尔 | — |
| `index.entries` | `18955` | 索引条目数 | 整数 |
| `index.kind` | `flat_bruteforce` | 若用 IVF/HNSW 改枚举 | 枚举 |
| `index.artifact_files[]` | 排序缓存/索引文件：`path, bytes, sha256` | 逐文件 | sha256 形态 + bytes |
| `counts.questions` | `1353` | — | — |
| `counts.unique_contents` | `18955` | **该索引内**互不重复的身份数；与 A 侧 4,712 不同是正常的，需在 notes 说明来源 | 与 A 基线不同只告警 |
| `counts.image_instances` | 你的语料实例数（不知道就 `null`） | — | 同上 |
| `sources[]` | 至少 1 条：`role=corpus` 的语料清单/图池，`path, sha256, bytes` | 若含**额外语料**必须**单列一条** `role=corpus`，这正是区分假设 H3 的关键 | role 枚举 + sha256 |
| `corpus_encode.device` / `seconds` | 实测值，未测写 `null` | — | — |
| `query_encode.*` | `batch_size=1`、`composition="单题"`、`per_request_batching=true` | smoke 报告称现场是 batch=1 | — |

## 2. 允许保留 `pending`（但必须写 notes）

| 字段 | 填什么 |
|---|---|
| `reconciliation.claimed_entries` | `18955` |
| `reconciliation.public_instances` | `14475` |
| `reconciliation.public_unique` | `4712` |
| `reconciliation.delta_vs_instances` / `delta_vs_unique` | `null`（由 A 计算） |
| `reconciliation.verdict` | **`pending`**（表示"等 A 裁定"） |
| `reconciliation.notes` | **必填非空**，例如 `等 A 侧按 14,475/4,712 口径对账后改 verdict` |

**规则**：`verdict=pending` 是合法状态，但 `reconciliation.notes` 为空会被 `a20` 判错（`errors` 里会写"pending 时必须在 reconciliation.notes 写明在等什么"）。**不要为了通过校验删字段或改成 `matches_*`。**

## 3. 不要让 A 猜的部分

- `sources[]` 里"多出来的语料"是哪一份、它的 sha256 是什么 —— 只有你能给。
- `index.artifact_files[]` 的真实字节数与 sha256。
- `corpus_encode.seconds`、`normalization.vector_norms_observed` —— 未测就写 `null`，不要写 0。

## 4. 两个例子

**最小可过（pending）**

```json
{
  "schema": "a_side_index_receipt/v1",
  "reconciliation": {"claimed_entries": 18955, "public_instances": 14475,
                     "public_unique": 4712, "delta_vs_instances": null,
                     "delta_vs_unique": null, "verdict": "pending",
                     "notes": "等 A 侧按 14,475/4,712 口径对账"}
}
```

**pending 但漏 notes（会被拒）**

```json
{"reconciliation": {"verdict": "pending", "notes": null}}
→ errors: ["reconciliation.verdict=pending 时必须在 reconciliation.notes 写明在等什么…"]
```

## 5. 与 A3 判定矩阵的关系

本表填完后，`reconciliation.verdict` 仍是 `pending`——**A 侧的裁定不靠 B 改 verdict**，而是 A 用这张表里的 `entries / dedup / sources / row_order / dtype / batch` 去判 H1/H2/H3（见 `reports/next_stage_20261020/index_receipt_adjudication.md`）。
