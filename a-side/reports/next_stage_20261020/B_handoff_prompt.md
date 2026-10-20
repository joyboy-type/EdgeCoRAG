# 给 B 的任务单（2026-10-20）

发布：2026-10-20。**本批没有新的 GPU 授权**：不租卡、不启动模型推理、不改历史结果。
A 侧交付在独立分支 `a-side/next-stage-20261017` @ `85a547d`，**未并入 `results/runtime-v1.10.1-delivery`**（不要等它进结果分支）。

## 0. A 已交付 —— 直接用，不要重做

| 项 | 结论 / 产物 |
|---|---|
| 排序差异定位 | 已排除"同配置随机性"（逐位一致）、"算术/排序实现"（改序 0 条，Δ≤7.7e-7）、"批大小作为充分原因"（签名率 10.6%，P(≥3/5)=0.01，且只中 `1117`）；**根因仍标未确认** |
| 三个一阶口径风险 | 归一化位置 8.1e-3（改序 76.2%）、dtype bf16↔fp32（改序 78.5%）、解码路径 q95↔原始字节（1.4e-2） |
| 冻结接口 v1 | EG2 @`914f7f89…`、fp32 + TF32 关闭 + float32 重归一化、`(-score, sha256 asc)`、自匹配剔除后补足 top10；**fp32 下批大小敏感性 0/1203** |
| 可消费产物 | `a-side/retrieval_if_v1/`：36 个哈希绑定文件（候选池/select3/脆弱度/检索指标），自校验 **失败 0** |
| 脆弱度新发现 | `min_adjacent_margin < 1e-3` 的题：768 维 83.35%、**128 维 94.97%** |
| 成本接口 | `a12_cost_recorder.py` + 段定义，自检 **11/11 通过** |
| 四路径 Oracle 上界 | 保真校验 30/30 格一致；frozen_test 固定最优 41.34% → **Oracle 61.96%（+20.6 pp，仅上界）** |
| 口径普查 | 公开数据集 14,475 实例 / 4,712 唯一内容，**都不等于报告的 18,955** |
| 分支卫生 | 未做任何 reset / clean / force push；A-01..A-04 交付物在远端逐字节一致 |

A **没有**做（这些是你的）：生成与评分、CPU 线程主查、端到端外层计时、MMDocRAG（B-03）、统计边界（B-04）、T15、可部署路由器实现、正式成本数值、四路径自主检索版本。

## 1. 先读

1. `reports/next_stage_20261020/A_return_20261020.md`（依赖清单总览）
2. `reports/next_stage_20261020/interface_freeze.md`（冻结口径，唯一权威）
3. `reports/next_stage_20261020/A_retrieval_consistency.md`（差异定位与"未确认"边界）

## 2. 你要做的 6 件事

### ① 独立校验产物（零依赖，今天可完成）

```bash
git checkout a-side/next-stage-20261017      # 或 fetch 到独立 worktree
python a-side/scripts/a17_verify_interface.py
#   预期：artifacts 校验 36 个文件、失败项 0、各维度 order_fragile 打印

python a-side/scripts/a06_build_corpus.py --store <你的目录>/corpus_v1 --verify
#   预期：content_digest = 31ade7b7e2454d0b9fcd58568247dd2a6862e15273fdd65e1d12ed50e373264e
#        corpus_manifest.csv 4,712 行、按 sha256 升序、mismatches = 0
```

`a17` 只读 CSV + hashlib，不需要模型与数据集。`a15_materialize_packets.py` 的语料路径是硬编码的（`E:\EdgeCoRAG-A-store\corpus_v1`），请改成你的路径；需要 `--corpus` 参数就提。

### ② 回传 A 定位那 3 题所需的 4 份数据（派生小数据，不含原题/gold/图片）

1. **索引构建回执**：条目数（报告写 18,955）、身份口径（原始字节/重编码）、是否内容去重、行序规则、dtype、归一化发生在哪一层、语料编码 batch。
2. **5 题的两份 10 行记录**（`mragb:10/1049/1051/1062/1117`）：`qid,source(history|live),rank,sha256,score`。
3. **现场查询向量指纹**：`sha256(float32 序列化后的向量字节)`；有历史缓存指纹一并给。
4. **编码参数回执**：dtype、`Normalize` 是否启用、现场编码的 batch 组成。

### ③ 固定 CPU 线程

`libgomp: Invalid value for environment variable OMP_NUM_THREADS` 出现 2 次。固定合法值，并把**实际生效值**写进计时回执的 `hardware.cpu_thread_env`（`a12_cost_recorder.py` 已预留，缺项写不进）。保留原日志，不悄悄重跑。

### ④ 修回执里的悬空引用

`provenance/results_20261020/e2e_smoke_public_receipt.json` 的 `source_pins` 指向 `a-side/scripts/evidence_selection.py` 与 `a-side/scripts/independent_retrieval.py`，这两个文件**在任何分支都不存在**。补齐源码或改指向真实文件，否则该回执不可复算。

### ⑤ 按冻结接口接入，不要另建一套

- **顺序以 A 的产物为准**：沿用 `pools/<cohort>__dim<D>__top10.csv` 的 rank 顺序，**不要重新打分再排**。
- **维度只用 dev_150 选**；`frozen_test` 的检索数值只作描述。
- **utility 口径冻结**：`ℓ("True")` 原始 logit；回传 `qid,sha256,score`，并回执 `utility_input_order` 与 `utility_batch_size`。
- **gold 只进评分/Oracle**。
- **计时用方案 A**：`a12_cost_recorder.py` 作外层，生成段包 `rec.segment("generation_decode_seconds")`；utility 单独记 `utility_scoring_seconds`（上一轮合在 `selection_request_build_seconds` 里，无法分离）。整卡显存/系统 RAM/能耗必须由外部实测写入，A 的模块里恒为 `null`。

### ⑥ 回传汇总

| # | 内容 | 格式 |
|---|---|---|
| 1 | `a17` 校验结果 | 终端输出或 `verify.json` |
| 2 | 语料重建校验 | `content_digest` + `mismatches` |
| 3 | 索引构建回执 | ②-1 |
| 4 | 5 题 × 2 份 10 行 | CSV |
| 5 | 查询向量指纹 + 编码参数 | JSON |
| 6 | `OMP_NUM_THREADS` 生效值 | 字符串 |
| 7 | `source_pins` 修正 | commit |
| 8 | 对接口的异议/缺字段 | 文字（冻结前最后一次改口径机会） |

## 3. 不要做

- 不重算候选池；不重新排序。
- 不把 S1（官方候选 top3）改称"自主 EmbeddingGemma 检索"。
- 不把 Oracle 上界（+20.6 pp）写成"路由器可达收益"；不与 S2 的 GT 证据 Oracle 混称。
- 不用 `frozen_test` 选维度、阈值或策略；已观察数据复核不写成"新盲测"。
- 不扩大 holdout 评测（A 的产物里 `internal_holdout` 为空是有意的）。
- 不改 v1.10.1 的 prompt / 64 token / 严格评分 / BF16 / split / 原有结果；新实验用新版本与独立目录。
- 不 `reset` / `clean` / `force push`；原题、图片、完整原始响应、权重、私有归档不上传。

## 4. GPU 门槛

第 ①②③⑤ 完成、接口异议关闭后才一起提最小对照范围：`smoke_20` 四路径各 1 次 → `dev_150` 四维度选择 → `frozen_test` 只跑选定维度一次。
量级估算（**非实测**）：约 9,464 次生成 + 11,830 次 utility 前向 ≈ 5 h GPU，按 1.48 元/时约 7.4 元；须附费用上限、硬停机时间、保全方案与停止条件。

B-03（MMDocRAG 许可）、B-04（统计边界）、T15 仍归你，与本批并行推进。
