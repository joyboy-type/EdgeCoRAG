# S3-8B 与 Qwen3.5-9B 补跑结果（2026-10-28）

本批补齐 2026-10-26 预注册的两项 GPU 对照；新数字独立存放，不修改 172 条冻结数字或论文初稿。两项正式结果完整、rc=0；正式全量技术失败为 0，冷启动超时另列保留。核查并取回备份后，按用户后续明确授权关机。

## 结果入口与口径

- 登记：[PREREGISTRATION_20261026_completion.md](../paper_20261021/PREREGISTRATION_20261026_completion.md)；固定预热修订为 §9，执行前提交 `46c8fd5`。原 S3 执行器为 `2f35406`。执行前登记的精确字节见 [注册快照](PREREGISTRATION_registered_46c8fd5.md)，当前入口只追加执行回填。
- 数字与逐文件 SHA256：[completion_numbers_20261028.json](completion_numbers_20261028.json)。下表每个数字均可在该 JSON 的同名小节及所列 CSV 中复算。
- 这里只给点读数，不新增 bootstrap 或置信区间，不将旧五模型的区间用于新模型；不作因果、等价或纯模型规模解释。

## Qwen3.5-9B：正式全量

来源：`completion_numbers_20261028.json#/Qwen35_9B`、[receipt_qwen35_9b.json](receipt_qwen35_9b.json) 的 `condition_receipts`。每条件固定分母 1,033；总请求 3,099，技术失败 0。

| 条件 | 正确数 / 分母 | 准确率 | 图片数（含 query） | 评分产物 |
|---|---:|---:|---|---|
| S0 | 606/1,033 | 58.66% | 1 + 0 | [s0s1s2_qwen35_9b_S0.csv](s0s1s2_qwen35_9b_S0.csv) |
| S1 | 618/1,033 | 59.83% | 1 + 3 检索图 | [s0s1s2_qwen35_9b_S1.csv](s0s1s2_qwen35_9b_S1.csv) |
| S2 | 720/1,033 | 69.70% | 956 题：1 + 5 GT；77 题：1 + 1 GT | [s0s1s2_qwen35_9b_S2.csv](s0s1s2_qwen35_9b_S2.csv) |

### S1 的接口可得率与条件表现（描述性）

来源：`completion_numbers_20261028.json#/Qwen35_9B_conditioned_S1`、[qwen35_9b_conditioned_S1.csv](qwen35_9b_conditioned_S1.csv)。沿用 `join_v2.csv.gz` 的逐题 `top3_gt_hit`，校验原五模型映射完全一致；不是一次新的自主检索。

- 命中：516/1,033（49.95%）；命中题答对 357/516（69.19%）。
- 未命中：517/1,033；未命中题答对 261/517（50.48%）。
- 条件比例只描述该模型、本题集和本证据条件，不当作模型常数或外推预测器。本批未为这些比例补区间。

### 冷启动与固定预热：两套结果均保留

来源：`completion_numbers_20261028.json#/feasibility`、[receipt_feasibility_cold.json](receipt_feasibility_cold.json)、[receipt_warmed_feasibility.json](receipt_warmed_feasibility.json)。

- 原冷启动首题 `mragb:6` 在 Triton 自动调优时触及 30 秒门槛：30.05180157 s；rc=5，未通过，未启动该轮全量。
- 事后明确登记独立 warmed 验证；固定 S0 前三题 `mragb:6 / mragb:11 / mragb:12` 各预热一次，不按速度或正确性追加。预热输出不计入正式准确率。
- 三次预热耗时分别为 39.25021056 / 0.33505622 / 0.30947696 s；随后同进程逐题正式计时为 0.34453444 / 0.31748735 / 0.30698645 s，均 ≤30 s，warmed 门槛通过后才执行全量。
- warmed 通过不撤销原冷启动未通过，也不构成冷启动时延或正常回答长度成本的结论。

## S3：Qwen3-VL-8B 补齐

来源：`completion_numbers_20261028.json#/S3_8B`、[receipt_s3_qwen3vl_8b.json](receipt_s3_qwen3vl_8b.json)。query + 3 张干扰图，共 4 图；三个 split 共 36 题，技术失败 0。

| split | 正确数 / 分母 | 准确率 | 评分产物 |
|---|---:|---:|---|
| dev | 1/5 | 20.00% | [s3_qwen3vl_8b_dev.csv](s3_qwen3vl_8b_dev.csv) |
| internal_holdout | 1/2 | 50.00% | [s3_qwen3vl_8b_holdout.csv](s3_qwen3vl_8b_holdout.csv) |
| frozen_test | 11/29 | 37.93% | [s3_qwen3vl_8b_frozen.csv](s3_qwen3vl_8b_frozen.csv) |

### 与原 S1 的同题转换

来源：`completion_numbers_20261028.json#/S3_vs_existing_S1`、[s3_qwen3vl_8b_S1_pairs.csv](s3_qwen3vl_8b_S1_pairs.csv)；原预测来自 `logs/B_predictions.jsonl.gz`。固定筛 `model_key=qwen3vl_8b, condition=S1, repeat_index=0`，dev 使用 `stage=development,split=dev`，其余使用对应 split 的 `stage=quality`。金标逐题一致。

| split（分母） | S1 答对 | S3 答对 | 均答对 | S1 对→S3 错 | S1 错→S3 对 | 均答错 |
|---|---:|---:|---:|---:|---:|---:|
| dev（5） | 4 | 1 | 1 | 3 | 0 | 1 |
| internal_holdout（2） | 2 | 1 | 1 | 1 | 0 | 0 |
| frozen_test（29） | 15 | 11 | 7 | 8 | 4 | 10 |

**边界**：S3 为 AI 图像辅助、label-aware、非人工盲审的小子集，只作上述子集描述，不声称完整基准或跨尺度鲁棒性。9B 属 Qwen3.5，与 Qwen3-VL 家族不同；未跑 S2@3，因此不进入 956 题同张数结论 A。

## 环境与来源

具体参数见两份模型回执的 `runtime`：bf16、无量化、greedy、seed=42、max_new_tokens=64、SDPA，Qwen 图像预算沿原协议 `min_pixels=50176,max_pixels=262144,use_fast=false`。新硬件为 4090 48GB；不声称跨硬件逐位等同。

9B 使用 torch 2.8.0+cu128 / CUDA toolkit 12.8 / Triton 3.4.0 / transformers 5.19.0。FLA 0.6.0 曾因引用 Triton 缺失的 Gluon 接口阻塞；无卡修复固定 flash-linear-attention 与 fla-core 为 0.4.2，causal-conv1d 1.7.0。其余已冻结依赖未改。见 [environment_repair_receipt.json](environment_repair_receipt.json) 与 [environment_constraints_20261028.txt](environment_constraints_20261028.txt)。

公开 CSV 保留题号、选项、金标与正确性，直接复制原评分字节。原图、模型权重、原始 QA、完整生成 JSONL 与完整私有归档不入库；其哈希见 [private_archive_manifest_20261028.json](private_archive_manifest_20261028.json)，可向项目持有者申请合法归档。公开校验只能重算已发布评分，不能替代从私有输入重新生成。

## 离线复算

从仓库根运行（标准库即可，不连接 GPU）：

```sh
python analysis/next_stage_20261026/recompute_completion.py --verify
python -m unittest discover -s analysis/next_stage_20261026 -p "test_*.py"
```

脚本校验六份 CSV 的字节哈希、固定分母、唯一题号、正确性标志、冷启动/预热判据、共享命中映射与 S3 同题来源；再逐字节核对新 JSON 和两份派生 CSV。此处不执行模型、不重解析旧预测、不增加区间。

交付验证：项目测试 157、旧分析测试 64、上一轮补实验测试 14、本轮测试 22，合计 257 项通过；离线复算通过。回执见 [validation_20261028.json](validation_20261028.json)，逐文件字节哈希见 [final_receipt_20261026.json](final_receipt_20261026.json)。
