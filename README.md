# EdgeCoRAG

研究小型多模态模型在共享视觉证据下的能力边界，以及质量、生成时延与显存的关系。
五个模型（Gemma 4 E2B/E4B、Qwen3-VL 4B/8B、Qwen3.5 4B）× 四种证据条件 × MRAG-Bench
1,033 题冻结评估。

## 当前状态（补跑更新至 2026-10-28）

实验已封板，进入论文阶段。

| 项 | 状态 |
|---|---|
| 主实验（五模型 × S0/S1/S2，1,033 题） | 完成 |
| 2×2 命中×答对分格 + 伤害 overlay | 完成 |
| Gate A1 裁决 | 完成（`insufficient_evidence`） |
| 跨栈 a18 回执 | 完成（`changed_order = 0`） |
| 索引身份对账 | 完成（18,955 / 14,475 / 4,712，交集 4,282） |
| 成本 pilot + 能耗 | 完成（三模型 / 20 题 / 4.35 Wh） |
| MMDocRAG 语义 judge | 完成（1,000 条，自洽率 1.0） |
| S3 干扰子集 | 原四模型保留；Qwen3-VL-8B 已补齐 dev5/holdout2/frozen29 |
| Qwen3.5-9B | 已补齐 S0/S1/S2 各 1,033；冷启动未通过，独立 warmed 验证通过后完成全量 |
| 论文 | 初稿进行中（见 `reports/paper_20261021/draft/`） |

补跑的六份评分 CSV、完整运行回执、边界与离线复算入口见 [2026-10-28 补跑结果](reports/paper_20261026/COMPLETION_RESULTS_20261028.md)。9B 的 S0/S1/S2 为 606/618/720（各分母 1,033）；这些新数字独立存放，不改原五模型冻结表。

## 原五模型冻结结果

1. **共享检索的配对读数**：S1−S0 为 −2.52 / −0.29 / −0.87 / +2.90 / +0.97 pp，
   四条区间跨零，无法与无变化区分。
2. **正确证据有效**：S2−S0 为 +4.65 至 +10.36 pp，全部不跨零。
3. **检索天花板**：GT 接口精确身份进 top-3 为 516/1,033，另 517 题未命中；这不等于模型无法从其他图片或已有知识答对。
4. **利用率差异**：命中 516 题中答对 219（Gemma 4 E2B）至 343（Qwen3-VL 8B），约 42%–66%。

以上数字的唯一入口是
[`frozen_numbers.json`](reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json)（172 条，逐条带来源与筛选条件）。

## 仓库导航

| 想知道什么 | 去哪 |
|---|---|
| 实验总入口 | [`reports/EXPERIMENT_RESULTS.md`](reports/EXPERIMENT_RESULTS.md) |
| 什么在仓库、什么不在、怎么重建 | [`reports/paper_20261021/DATA_INVENTORY.md`](reports/paper_20261021/DATA_INVENTORY.md) |
| 论文大纲 / T2 区间 / 参考文献 / 初稿 | [`reports/paper_20261021/`](reports/paper_20261021/) |
| 需求完成情况（37 项） | [`reports/Requirements.md`](reports/Requirements.md) |
| 五模型比较 | [`reports/B_comparison.md`](reports/B_comparison.md) |
| 逐题结果与输入上下文 | [`logs/`](logs/) |
| 文献与复现状态 | [`reports/B_papers.md`](reports/B_papers.md) |
| 交付与清理说明 | [`reports/Delivery.md`](reports/Delivery.md) |

## 复现

```bash
python -m unittest discover -s tests
python -m unittest discover -s analysis/next_stage_20261019
python analysis/next_stage_20261019/audit_requirement_evidence.py   # 缺私有输入时 rc=1（设计如此）
```

私有输入齐全时审计返回 `rc=0, errors=[]`；缺失时 fail-closed 返回 `rc=1`，这是预期行为。
离线复算方法见 [`analysis/v1.10.1/README.md`](analysis/v1.10.1/README.md)。

## 边界：本文不主张什么

- post hoc Oracle 上界（+6.87 至 +10.55 pp）不是可部署收益，未评估任何路由策略；
- 区间是描述性、未预注册，跨零一律表述为"不能排除无差异"；
- MMDocRAG 只报检索/生成指标与 judge 评分，不主张语义准确率等于人工评估；
- 成本仅覆盖三模型 / 20 题 / 每请求 2 token，不能外推为完整成本曲线；
- 能耗是 GPU 功耗点采样（83.5 秒窗口），不是整机能耗。

<details>
<summary>历史导航（2026-10-17 版，原 main 首页内容，保留备查）</summary>

已完成实验数据集中在 **[实验结果总入口](reports/EXPERIMENT_RESULTS.md)**：原五模型基线、MMDocRAG固定200题、无自匹配三策略复核、检索维度离线消融、图像相关性分析及真实同机端到端技术smoke。

新增[可分发逐题派生结果](logs/results_20261020/README.md)与[文件哈希清单](provenance/results_20261020/public_manifest.json)。原题、gold、私有MMDocRAG原始响应、图库、权重及完整私有归档不包含在这次发布中。

截至2026年10月17日，runtime-v1.10.1批准的161任务、21927次问答已全部完成并本地备份核验。五模型技术通过，132次正常格式失败全部计错。

- [下一阶段任务：A](reports/next_stage_20261017/A_TASKS.md) / [B](reports/next_stage_20261017/B_TASKS.md)
- [B 阶段论文初稿](reports/next_stage_20261017/B_phase_report.md)
- [论断证据表](reports/next_stage_20261017/B_claim_evidence.csv)
- [第二数据集可行性](reports/next_stage_20261017/B_external_dataset_feasibility.md)
- [统计补强决策](reports/next_stage_20261017/B_statistics_decision.md)
- [下一轮实验预案](reports/next_stage_20261017/next_experiment_decision.md)
- [下一步应该做什么](reports/Next_steps.md)
- [任务书与全部要求整合](reports/Requirements.md)
- [原始绑定与补丁运行的两阶段重建](reports/Reconstruction.md)

</details>
