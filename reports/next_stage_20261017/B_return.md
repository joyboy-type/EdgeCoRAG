# B侧本批交付回执

日期：2026年10月17日（Asia/Shanghai）。实验基线仍为runtime-v1.10.1，本批只新增写作、证据对照、公开来源核验和后续方案。

| 任务 | 本批状态 | 交付 | 仍缺什么 |
| --- | --- | --- | --- |
| B-01 | 已完成阶段论文初稿 | [正文Markdown](B_phase_report.md)、[离线报告HTML](B_phase_report.html)、[canonical输入](B_phase_artifact.json) | 尚非投稿终稿或全课题结题；后续实证缺口随正文保留 |
| B-02 | 已完成记录层论断与案例状态对照 | [37条论断证据](B_claim_evidence.csv)、[20条案例状态](B_case_review_status.csv) | 正式原图可获得性待A-01；视觉与机制审定均未做，R21仍部分完成 |
| B-03 | 部分完成 | [文献证据表](B_paper_evidence.csv)、[第二数据集可行性](B_external_dataset_feasibility.md)、[19次公开来源核验记录](B_public_source_checks.json)、[36行选定主表证据](B_paper_table_evidence.csv)、[评分合同草案](B_mmdocrag_scoring_contract.md) | 选定主表与10项静态接口发现已核对；未复现原论文全表；真实schema、许可、适配实现／运行依赖未齐；无外部推理结果 |
| B-04 | 方法边界已交付，最终分组判断待依赖 | [统计决策](B_statistics_decision.md) | 等A-04的可信来源键；不编造来源聚类区间或概念类别映射 |
| B-05 | 预案已交付，执行未冻结 | [下一轮预案](next_experiment_decision.md) | 等A-02/A-03与B-03/B-04补齐；题单、正式矩阵、费用与执行范围尚未定稿 |

## 核验范围

- 从已保存quality正确数／分母重新检查准确率与跨模型点差；成本P95与performance表对账。两份CSV的少量末位表示差异最大约1.14e-13ms，采用1e-9ms容差，不修改原表或显示值。
- 11条真实SQLite查询只选择／整形已保存事实，未重新估计bootstrap区间；20条选例逐一对照台账模式，37条主要论断具有分母、定位和限制。
- [数据核验记录](B_phase_validation.json)与[HTML打包记录](B_phase_packaging_receipt.json)分别保留。HTML合同和结构验证通过；因无兼容headless-shell，图表显示、来源弹窗和交互未完成浏览器自动核验，不声称视觉QA通过。
- 官方网页／仓库／HF元数据与少量评分代码只读核验，没有下载外部QA、作者逐题响应、图片包或PDF语料，没有运行作者代码／judge。引用作者声明与本地实测严格分开。

## 约束与要求状态

未连接旧服务器、租卡、重启、调用模型、重试或修改冻结参数；原始结果、评分、代码身份和备份保持原样。旧Word与完整ZIP保留，新增阶段材料单独交付。

R05仍部分完成，R06仍待补，R21/R22/R24仍部分完成；阶段正文、任务单或预案存在不代表这些科学要求完成。A本批尚未回传到此工作副本的内容均保留依赖状态，不据此断言A没有在其他位置工作。

## B-03本次增量

四篇全文的选定主表已形成36行证据，见[核验说明](B_paper_table_audit.md)与[来源哈希](B_primary_paper_checks.json)。Utility与VisDoM相关主表页面已渲染检查；不是原论文所有附录／全部成绩的审阅或复现。原阶段论文MD/HTML保留此前快照，本补充单独说明新证据。

MMDocRAG发现论文与源码Overall F1聚合口径不同；静态审查共10项发现，另列15个未来合成验收规格。尚未实现适配器，未运行作者评分模块或judge；其顶层NLTK下载也没有执行。

下一步可先在本地实现无judge纯指标适配器并只用虚构输入验证，不需要GPU；同时等待A回执与明确许可依据，再安排最小真实schema核验和新协议。本批没有下载研究QA、图库或权重，没有启动推理或付费judge。
