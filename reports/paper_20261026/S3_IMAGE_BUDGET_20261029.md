# S3 图像预算不一致：核查与表述限制（2026-10-29）

## 0. 结论

五模型 S3 表的五行，**图像预处理预算不同源**：

| 行 | 预算 | 仓库可否核验 |
|---|---|---|
| `qwen3vl_4b` | 模型自带默认（`size.longest_edge = 16777216`，几乎不封顶） | ❌ 回执未记录 |
| `qwen35_4b` | 同上 | ❌ 回执未记录 |
| `qwen3vl_8b` | 冻结协议 `min_pixels=50176, max_pixels=262144` | ✅ 回执已记录 |
| `gemma4_e2b` | 历史 `M` 日志，未记录 | ❌ |
| `gemma4_e4b` | 历史 `M` 日志，未记录 | ❌ |

因此：**S3 只支持同模型、同题的 S1→S3 转换读数；不得跨模型比较 S3 准确率。**

本文件只做核查与表述限制，不改任何既有 CSV、回执或冻结数字。

## 1. 三处证据

### 1.1 8B（2026-10-28）已记录，且为 262144

来源 `reports/paper_20261026/receipt_s3_qwen3vl_8b.json`：

- `runtime.image_processor_config.size = {"longest_edge": 262144, "shortest_edge": 50176}`
- `runtime.image_preprocessing = "unchanged protocol_main_v1.json image_processing.qwen: min_pixels=50176,max_pixels=262144,use_fast=False; no fit-to-memory changes"`

### 1.2 两个 Qwen 4B 行（2026-10-21）未记录，且执行器未传预算

`reports/next_stage_20261019/gpu_judge_s3_20261021/S3/receipt_qwen3vl_4b_*.json` 的字段仅为：

```
model, model_id, revision, split, n, n_correct, accuracy, dtype, do_sample,
max_new_tokens, review_method, disclosure, gold_sha256, input_sha256,
csv_sha256, elapsed_seconds
```

—— **不含** `processor_config` / `max_pixels`。`receipt_qwen35_4b_*.json` 字段更少，同样不含。

同一目录下已提交的执行器 `runner.py` 第 65 行：

```python
processor = AutoProcessor.from_pretrained(wdir, local_files_only=True, trust_remote_code=True)
```

**未传 `min_pixels` / `max_pixels`**，因此取模型自带 `preprocessor_config.json` 的默认值。

### 1.3 模型默认几乎不封顶

`https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct/raw/main/preprocessor_config.json`：

```json
{"size": {"longest_edge": 16777216, "shortest_edge": 65536},
 "patch_size": 16, "merge_size": 2}
```

无 `max_pixels` 字段。`Qwen/Qwen3.5-9B` 的同名字段完全相同。

## 2. 差异量级

按 Qwen2VL 系列图像处理规则（16×16 patch，2×2 merge → 约每 1024 像素 1 个视觉 token）：

| 预算 | 单图上限像素 | 单图视觉 token（约） |
|---|---:|---:|
| 模型默认 `16777216` | 16,777,216 | 16,384（实际受原图限制） |
| 冻结协议 `262144` | 262,144 | 256 |

实测 S3 干扰图常见尺寸 976×1352 ~ 1536×2246（约 1.3–3.4 M 像素）：

- 默认预算下 ≈ **1,300–3,370 token/图**
- 262144 预算下 ≈ **256 token/图**

**单图相差约 5–13 倍，四图同量级。** 故两个 4B 行与 8B 行不是同一输入条件。

## 3. 对结论的影响

| 结论 | 是否可用 | 说明 |
|---|---|---|
| 同模型内 S1 → S3 的逐题转换（救回 / 伤害 / 不变） | ✅ 可用 | 每题预算恒定，转换读数不受预算差异影响 |
| 各行 S3 准确率本身 | ✅ 可用 | 仅作为"该行在该预算下"的读数 |
| **跨模型比较 S3 准确率**（如"8B 比 4B 更抗干扰"） | ❌ **不可用** | 输入条件不同 |
| 跨尺度鲁棒性结论 | ❌ 不可用 | 另受 29 题、AI 辅助、非盲审限制 |
| 把 S3 与主实验 S1 放同表比较 | ❌ 不可用 | 主实验为 262144，与 4B 行 S3 不同源 |

## 4. 补救路径

### 路径 A：统一到 262144，重跑两个 Qwen 4B 行（未执行）

- 规模：36 题 × 2 模型，约 20 分钟；24 GB 卡在 262144 下足够。
- 前置：需要 S3 输入与媒体图，**它们不在仓库内**。
- 媒体确切出处：GitHub Release 资产
  `evidence-packages-v1.0/frozen_test_s3.zip`（571,949,633 字节，
  sha256 `8b907e5013c29daae36e1f0ca2f51021bbcd279d8d2a92de71935e641962257e`），
  见 `b-side/reception/all_20261016/frozen_test/frozen_test_s3.transport.json`；
  `internal_holdout`、`dev` 各有对应资产。
- 下载后须经 `b-side/integrate_condition_packages.py` 重建
  `integrated/<split>/s3/{inputs/S3-pure.json, media/, scoring/answers.json}`，
  并按 8B 回执的 `input_sha256` 校验一致，方可视为同一输入。
- 同时须核验 Gemma 两行的历史预算；若亦为 262144，则只有两行 4B 需要重跑。
- 重跑须另立产物与新版本号，**不覆盖** `reports/next_stage_20261019/gpu_judge_s3_20261021/S3/` 下的既有 CSV。

### 路径 B（本次采用）：限制表述范围

- 既有五份 CSV 与回执**原样不动**。
- 论文与附录只按 §3 的可用范围写；跨模型 S3 比较一律不写。
- 本文件作为该限制的登记证据。

## 5. 论文可直接使用的表述

附录 S3 小节表注（建议原文）：

> S3 为 AI 图像辅助、label-aware、非人工盲审的小子集（dev 5 / holdout 2 / frozen 29）。
> 各行的图像预处理预算不同源：`qwen3vl_4b` 与 `qwen35_4b` 使用模型默认
> （`size.longest_edge = 16777216`），`qwen3vl_8b` 使用冻结协议的
> `min_pixels = 50176, max_pixels = 262144`；Gemma 两行的历史预算未记录。
> 因此本表只支持**同模型、同题**的 S1 → S3 转换读数，**不支持跨模型比较 S3 准确率**，
> 也不支持任何跨尺度鲁棒性结论。

正文如引用，只能写形如：

> 在被干扰图替换证据后，各模型在同题上的 S1 → S3 转换分别为 …（逐模型列出），
> 但各模型的图像预算不同源，故不比较它们之间的抗干扰强弱。

## 6. 本文件未做的事

- 未下载 Release 资产，未重建 S3 输入，未重跑任何模型。
- 未修改任何既有 S3 CSV、回执或 `reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`。
- 未核验 Gemma 两行的历史 `max_pixels`：仓库内无该字段，需查历史执行记录或原始归档。
