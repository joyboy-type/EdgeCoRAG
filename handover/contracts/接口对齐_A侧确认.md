# 与 B 侧的接口对齐（A 侧确认版）

> 依据：B 已有**通过验证的** `strict_choice_v1` 评分器。
> **A 侧不另写第二套评分器。** 本文件只声明 A 侧为适配它所做的约定与改动。

---

## 1. 结论：A 侧接受 B 的全部约定

| # | B 的约定 | A 侧处理 |
|---|---|---|
| 1 | 保留 `raw_id` 原始字符串 | ✅ 保留 `raw_id` 为原始 `item['id']` 原样字符串（不做数字转换） |
| 2 | 项目 qid 用 `mragb:<raw_id>` | ✅ 已采用；`raw_id` 与 `qid` 可互推（校验器已检查） |
| 3 | 由 B 适配旧样本和答案表 | ✅ A 侧不参与，仅保证 `raw_id`↔`qid` 映射稳定 |
| 4 | `task_payload` / 图片引用 / `scoring_only` 明确隔离 | ✅ 三个区独立；校验器有专门检查 |
| 5 | 对齐 `prediction_raw`/`raw_output`、解析器版本、失败状态 | ✅ 见 §3 |
| 6 | 条件名称一致（S1 / S3 / S3-pure） | ✅ 见 §4 |
| 7 | 每条结果可追溯模型/条件/协议/证据版本/批次 | ✅ schema 已含全部溯源字段，见 §5 |
| 8 | 官方评分格式作为**单独导出格式** | ✅ 见 §6，**不声称本 Schema 天然满足官方输入** |
| 9 | 失败不删题；主准确率用固定题单分母 | ✅ 见 §7 |
| 10 | 补充跨字段检查 | ✅ 见 §8，全部已实现并输出 |

---

## 2. ID 与命名（已冻结）

```
raw_id       : item['id'] 原样字符串        '0' / '42'
qid          : 'mragb:' + raw_id            'mragb:0'
evidence_id  : f"{qid}#{role}{rank}"         'mragb:0#official_retrieved0'
放盘路径      : images/<raw_id>/<role>_<raw_id>_<rank>.jpg
```

**路径根目录**：`handover/samples/`。JSONL 与 CSV 中的 `path` 均相对该目录。

**不改动 `raw_id` 的任何形态**：即使是 `'0'` 这样的数字字符串也保持字符串，
避免前导零/类型转换问题。

---

## 3. 结果行的字段对齐

B 侧已有 `strict_choice_v1`，A 侧**不定义解析器**，只保证输入字段齐全。

| 概念 | A 侧产物中的字段 | 说明 |
|---|---|---|
| 模型原始输出全文 | `prediction_raw` | 主字段 |
| 同上（别名） | `raw_output` | 与 `prediction_raw` **必须同值**；供 B 侧既有代码读取 |
| 官方脚本期望的字段名 | `output` | 仅为导出官方格式用，不再作为主字段 |
| 解析后的选项 | `prediction` | `'A'/'B'/'C'/'D'` 或 null |
| **解析器版本** | `parser_version` | 固定为 B 的 **`strict_choice_v1`**；A 侧不写值，由 B 填 |
| 失败状态 | `status` | 见 §7 枚举 |
| 抽取失败标记 | `extraction_failed` | `status` 的取值之一 |

> ⚠️ `prediction_raw` 与 `raw_output` 同时存在是**刻意的冗余**，
> 目的是让 B 的既有代码与 A 的 schema 不必互相迁就。
> 校验规则：两者若都存在则**必须相等**（已加入校验项）。

---

## 4. 条件名称（统一表）

**文档与 Schema 使用同一套名称，不得混用。**

| 条件 | 含义 | 证据来源 |
|---|---|---|
| `S0` | 无外部证据 | 无 |
| `S1` | 共享检索证据 | `official_retrieved_top5` 或 `reindexed_corpus_v1` |
| `S2` | GT 正确证据（**Oracle 上界**） | `gt_evidence` |
| `S3-pure` | 纯干扰证据 | `pure_distractor_v1` |
| `S3-mixed` | 正确证据混入干扰（固定 1 GT + 4 干扰） | 混合 |

**注意**：先前文档出现过 `S3` 与 `S3-pure` 混用。**现统一**：
- 泛指干扰实验时用 `S3`（作为类别）；
- 具体条件值一律用 `S3-pure` 或 `S3-mixed`。

`result_row.schema.json` 的 `condition` 枚举已按此更新。

---

## 5. 可追溯性（每条结果必须能回答"这是哪一次跑出来的"）

`result_row.schema.json` 已包含以下字段，**均为必填或强建议**：

| 维度 | 字段 |
|---|---|
| 模型 | `model_id`、`model_revision`、`quantization` |
| 条件 | `condition`、`pool_id`、`protocol_version` |
| 协议 | `prompt_template_version`、`prompt_image_slots` |
| **证据版本** | `evidence_version`（对应冻结包版本号）、`evidence_ids_order` |
| **运行批次** | `run_batch_id`（任一批次内唯一） |
| 解析 | `parser_version`、`extraction_method` |
| 硬件 | `hardware`（gpu / vram_gb / driver） |
| 计时 | `retrieval_ms`、`encoder_ms`、`router_ms`、`generation_ms`、`e2e_ms`、`cold_start`、`repeat_index` |

> `evidence_version` 与 `run_batch_id` 是新增要求：没有它们，
> 冻结后的多版本结果无法区分，也无法复验。

---

## 6. 官方评分格式：作为**单独导出**，不作主格式

⚠️ **本 Schema 不声称满足官方 `score.py` 的全部输入要求。** 理由：

| 官方 `score.py` 期望 | 本 Schema | 处理 |
|---|---|---|
| `gt_choice` | `gt_choice` + `gold_choice` | 两字段都给，值必须一致 |
| `output` | `prediction_raw` / `raw_output` | 导出时复制为 `output` |
| `prompt` | `prompt` | 导出时带上 |
| `scenario` | `scenario` | 已含 |
| 按**行顺序**对齐（无 ID） | 按 `qid` 对齐 | ⚠️ 冲突 |

**处置**：提供一个**独立的导出步骤**生成官方格式文件，
并在导出时**按官方题单顺序排列、补齐缺行**，同时记录导出清单的哈希。

导出脚本的输入是 A/B 的主结果 JSONL，输出是官方格式 JSONL，
**两者不互相替代**。导出文件命名为 `*_official_export.jsonl`。

> 另注：官方 `score.py` 自身有 4 处缺陷（含会崩溃的类型错误），
> 详见 [`官方评测接口差异.md`](官方评测接口差异.md)。
> **导出是为了兼容，不代表官方脚本的输出可信。**

---

## 7. 失败处理

| 约定 | A 侧实现 |
|---|---|
| 失败**不得删题** | `status` 保留为失败值，行仍在清单中 |
| **主准确率用固定题单分母** | 题单由冻结包定义；分母 = 题单全量，不因失败而变 |
| 成功子集指标仅作补充 | 另报，且**必须给出覆盖率**（成功数 / 题单总数） |

`status` 枚举：`ok` / `extraction_failed` / `generation_failed` /
`missing_image` / `corrupt_image` / `retrieval_failed` / `excluded`。

⚠️ **失败记录不得被过严的必填图片字段阻止保存**：
A 侧 schema 中 `evidence_order` 允许为空数组（`minItems` 未设下限），
`question_image` 在失败场景下允许为 `null`。这样失败行**总能写入**，
不会被校验拒绝而丢失。**校验器对失败行只做宽松检查。**

---

## 8. 跨字段检查（已全部实现并输出）

要求补充的检查项，均已实现于
`a-side/scripts/verify_handover_sample.py`（样例）与
`a-side/scripts/validate_schema.py`（契约）：

| # | 检查 | 实现位置 | 样例结果 |
|---|---|---|---|
| 1 | 证据数量 == 列表长度 | `num_evidence == len(evidence_order)` | ✅ |
| 2 | 排名与列表对应 | `len(retrieval_ranks) == len(evidence_order)` | ✅ |
| 3 | 分数与列表对应 | `len(retrieval_scores) == len(evidence_order)` | ✅ |
| 4 | 图片路径有效 | 逐条 `base / path` 存在性 | ✅ |
| 5 | ID 唯一 | `evidence_id` 与 `qid` 各自唯一 | ✅ |
| 6 | **失败记录不被必填图片字段阻止保存** | 见 §7 | ✅（schema 已放宽） |
| 7 | **MRAG-Bench 四个选项完整** | `set(choices) == {A,B,C,D}` | ✅ |
| 8 | GT ID 与 GT refs 一一对应 | 顺序与内容一致 | ✅ |
| 9 | 顺序一致 | `evidence_order` 与 CSV `rank` 序列一致 | ✅ |
| 10 | 占位符数 == 证据数 + 1 | `prompt_image_slots == len(evidence_order) + 1` | ✅ |
| 11 | 无孤儿索引条目 | 每条 CSV 条目都能在 JSONL 找到声明来源 | ✅ |
| 12 | 区隔离 | `task_payload` 不含答案字段 | ✅ |

**实际输出**：`a-side/data/acceptance_report.json`（28/28 通过）。

---

## 9. 仍需 B 确认

1. `prediction_raw` / `raw_output` 双字段冗余是否接受。
2. 条件名称 `S3-pure` / `S3-mixed` 是否与 B 侧文档一致。
3. `parser_version` 由 B 侧填写 `strict_choice_v1`，A 侧置 null —— 是否可行。
4. 官方格式导出是否需要 A 侧实现，还是由 B 侧统一做。
5. 失败行「宽松校验」的具体口径是否与 B 的校验器一致。
