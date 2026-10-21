# 数据清单：什么在仓库里，什么不在，怎么重建

本仓库是公开的，因此只收录代码、派生结果与回执；原始图像、模型权重与私有标注不入库。
本文件的作用是消除"clone 下来发现数据缺失"的歧义：每一样不在仓库里的东西，
这里写明它在哪、为什么不在、以及如何从公开数据重建。

## 一、在仓库里（可直接核对）

| 类别 | 路径 | 规模 |
|---|---|---|
| 逐题预测与评分 | `logs/B_predictions.jsonl.gz` | 21,927 行 |
| 冻结数字（论文唯一数字入口） | `reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json` | 172 条 |
| 配对比较区间 | `reports/paper_20261021/T2_paired_intervals.md` | 15 行 |
| 2×2 分格与伤害 overlay | `reports/next_stage_20261019/error_partition_20261021/` | 四类相加 = 1,033 |
| Gate A1 裁决 | `reports/next_stage_20261019/gate_a1_20261021/` | 含数字与反例 |
| 跨栈 a18 回执 | `reports/next_stage_20261019/gpu_scores_20261021/` | `changed_order = 0` |
| 索引对账 | `reports/next_stage_20261019/index_reconciliation_20261021/` | 18,955 / 14,475 / 4,712 |
| 排序分析 | `reports/next_stage_20261019/order_diff_20261021/` | 含 bf16-cast 消融 |
| GPU judge 与 S3 | `reports/next_stage_20261019/gpu_judge_s3_20261021/` | 1,000 条判分 + 6 份 csv |
| 能耗与成本 | `reports/next_stage_20261019/gpu_cost_20261021/`、`p4_frozen_20261021/` | 4.35 Wh / 三模型 pilot |
| 论文物料 | `reports/paper_20261021/` | 大纲、F4 图与脚本、T2 表、参考文献 |
| 代码与测试 | `b-side/`、`analysis/`、`tests/` | 153 + 54 测试 |

## 二、不在仓库里（按原因分类）

### A. 体积或许可原因排除，且可由公开数据重建

| 对象 | 体积 | 位置 | 重建方式 |
|---|---|---|---|
| MRAG-Bench 原始 parquet（28 片） | 4.1 GB | 私有归档 `datasets/mrag_bench/43620fde…/data` | 从 HuggingFace `uclanlp/MRAG-Bench` 拉取对应 revision |
| 研究语料 corpus_v1（4,712 张 q95 图） | 1.25 GB | A 侧 `E:\EdgeCoRAG-A-store\corpus_v1` | `a-side/scripts/a06_build_corpus.py --store <dir> --verify`（纯本地，不需网络、不需 GPU） |
| 历史索引图像 18,955 张 | 数 GB | B 侧归档 ZIP | 从 round-1 归档获取；仅用于身份对账，不参与本研究定量 |
| 语料向量 V.npy / Q.npy | 14.5 MB / 15 KB | GPU 会话包 `session.tar.gz`（本地） | 用 `b-side/encode_pool.py` 在 corpus_v1 上重新编码 |
| 完整像素身份表 | 10.8 MB（A）/ 42 MB（B） | 本地 | 用 `pixel_identity_spec.md` 的算法从原图重算；仓库只收三列键表（约 0.9 MB / 3.5 MB） |
| 模型权重 | 8–19 GB / 模型 | HuggingFace | 按 `b-side/configs/model_registry.json` 的 revision 下载 |

### B. 许可或数据协议原因排除，不重建

| 对象 | 原因 |
|---|---|
| MMDocRAG 私有 gold、原始 QA | 数据协议不允许再分发；仓库只收聚合指标与回执 |
| 需求审计的四份私有输入 | 含私有路径与授权信息；公开检出下裸审计按设计返回 `rc=1` |
| 模型生成的原始图像（S3 干扰图） | AI 生成图像，许可与来源需单独说明；只收受控子集的统计结果 |

### C. 尚未入库

| 对象 | 说明 |
|---|---|
| 论文初稿（中/英） | 待定稿后入库；当前放在 `reports/paper_20261021/draft/` |

## 三、被明确放弃的部分（不是遗漏）

| 对象 | 状态 | 原因 |
|---|---|---|
| S3 的 Qwen3-VL-8B | 未执行 | bf16 + 多图需 23.4 GB，超出 24 GB 单卡；8bit 需 `accelerate` 未安装 |
| Qwen3.5-9B | 阻塞 | 线性注意力需 `flash-linear-attention` + `causal_conv1d`；评估环境无 `nvcc` 无法编译，参考实现下单题 >10 分钟 |
| 五模型完整成本矩阵 | 部分执行 | 成本 pilot 覆盖三个模型、20 题、每请求 2 token |
| MMDocRAG 语义 judge 之外的开放问答人审 | 未执行 | 无人审预算 |
| 能耗整机测量 | 未执行 | 仅有 GPU 功耗点采样（4.35 Wh / 83.5 s 窗口） |

## 四、自证方式

- 每一份入库产物的 sha256 都在对应回执里；`final_receipt.json` 的哈希按 **LF 规范化字节** 计算。
- 逐题数据可用 `python -m unittest discover -s tests` 与 `analysis` 侧测试复验（153 + 54）。
- 私有输入缺失时，审计脚本按设计返回 `rc=1`，这是 fail-closed 行为，不是故障。
