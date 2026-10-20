# 已完成实验结果总入口

更新至2026-10-20。这里只列已执行或已完成的离线分析；其他agent的未执行提案和正在修改的代码不作为实测数据发布。原始预测/源数据保留边界见下表。

| 实验 | 完成范围 | 公开结果入口 |
|---|---|---|
| 冻结五模型S0/S1/S2与批准S3 | 161任务、21927次question-runs | [基线报告](B_comparison.md)、[逐题记录](../logs/README.md)、[原始执行回执](../provenance/v1.10.1/execution_receipt.json) |
| MMDocRAG跨数据集补充 | 40技术、160开发、1000正式预测；15技术预热；无judge | [正式报告](next_stage_20261017/B_mmdocrag_evaluation_report.md)、[汇总JSON](next_stage_20261017/B_mmdocrag_evaluation_summary.json)、[技术回执](next_stage_20261017/B_mmdocrag_technical_gpu_receipt.json)、[开发回执](next_stage_20261017/B_mmdocrag_development_gpu_receipt.json) |
| 无自匹配三策略复核 | 20/150/1033题，五模型三策略，18045条预测 | [报告](next_stage_20261019/EdgeCoRAG_无自匹配协议复核结果_20261019.md)、[准确率CSV](next_stage_20261019/无自匹配协议_准确率汇总.csv) |
| 旧自匹配协议历史对照 | 1033题五模型三策略，15495条派生评分 | [旧值汇总](results_20261020/legacy_self_match_quality.csv)、[新旧对照](next_stage_20261019/无自匹配协议_与旧协议对照.csv)；旧自匹配是已知混杂 |
| 检索维度离线消融 | 1203查询×4维度=4812条排名复核 | [报告](next_stage_20261019/EdgeCoRAG_无自匹配检索维度消融_20261019.md)、[指标CSV](next_stage_20261019/无自匹配检索_维度消融.csv) |
| 图像相关性与证据变化 | 860查询图像簇/564关联分量；30聚类区间、135场景剔除单元 | [报告](next_stage_20261019/EdgeCoRAG_图像相关性与证据变化分析_20261020.md)、[聚类CI](next_stage_20261019/图像相关性_聚类置信区间_20261020.csv)、[证据分层](next_stage_20261019/证据变化_分层答案变化_20261020.csv) |
| 同机端到端技术smoke | RTX3090同驻EG768与GemmaE2B，32请求、30测量 | [报告](next_stage_20261019/EdgeCoRAG_同机端到端smoke实测_20261020.md)、[逐次计时](next_stage_20261019/同机端到端_smoke逐次测量_20261020.csv)、[公开回执](../provenance/results_20261020/e2e_smoke_public_receipt.json) |

## 可下载数据与校验

- [新增逐题派生结果与字段说明](../logs/results_20261020/README.md)：无自匹配、历史混杂协议、MMDocRAG数值指标与匿名图像分组。失败保留，未附原题、gold、原始响应或图片。
- [已完成实验身份与计数](../provenance/results_20261020/completed_experiments.json)。
- [本次公开文件SHA256清单](../provenance/results_20261020/public_manifest.json)。历史v1.10.1 manifest继续保持其原快照身份。

## 研究与分发边界

- 各批次任务、预算、证据形式与分母不同，不把这些行数相加成统一质量样本。缓存分析、已观察数据复核和新盲测分别表述。
- MMDocRAG许可冲突尚未澄清，原始QA、候选、图片、PDF、完整模型响应及逐题引用集合保持私有；这里只发布派生数值与聚合研究结果。新增MRAG台账同样去除原题与gold。
- private归档、权重、索引/嵌入、认证与连接信息、运维授权、环境缓存和本地绝对路径不加入本次提交。公开receipt中的私有源文件SHA仅用于身份核验，不表示公开源文件内容。
- E2E仅为5题技术smoke，每路径15测量，不报告P95；存在CPU线程warning和3题历史top10内部排序差异，不视为正式基准。
- 图像分簇不等于独立来源分组，统计区间为未做多重校正的描述性结果；无因果、普遍替代或真实边缘设备成本结论。
- 这次发布不合并草稿PR、不启动GPU、不改写历史预测。下一轮实验另行固定协议和预算。

部分已发布早期文档使用“当前”描述历史阶段；对上述实验的完成状态，以本页所列结果及日期明确的真实回执为准。
