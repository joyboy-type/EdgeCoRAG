# B侧本批交付回执

日期：2026年10月17日（Asia/Shanghai）。实验基线仍为runtime-v1.10.1，本批只新增写作、证据对照、公开来源核验和后续方案。

| 任务 | 本批状态 | 交付 | 仍缺什么 |
| --- | --- | --- | --- |
| B-01 | 已完成阶段论文初稿 | [正文Markdown](B_phase_report.md)、[离线报告HTML](B_phase_report.html)、[canonical输入](B_phase_artifact.json) | 尚非投稿终稿或全课题结题；后续实证缺口随正文保留 |
| B-02 | 已完成记录层论断与案例状态对照 | [37条论断证据](B_claim_evidence.csv)、[20条案例状态](B_case_review_status.csv) | A@4dbeab85a0cef2cab8fc2fae928392bf14bc7994报告172条引用可获得；B待实际交接／完整性核验，视觉与机制审定均未做，R21仍部分完成 |
| B-03 | 部分完成 | [文献证据表](B_paper_evidence.csv)、[第二数据集可行性](B_external_dataset_feasibility.md)、[19次公开来源核验记录](B_public_source_checks.json)、[36行选定主表证据](B_paper_table_evidence.csv)、[评分合同草案](B_mmdocrag_scoring_contract.md) | 选定主表与10项静态接口发现已核对；未复现原论文全表；无judge独立适配器云端T01–T14通过；Mac T01–T14通过，T15依赖未齐，真实schema／许可仍未解决；无外部推理结果 |
| B-04 | 方法边界已交付，现有材料不可可靠来源聚类 | [统计决策](B_statistics_decision.md) | A-04已实质返回：现有字段无可信来源键，不能可靠来源聚类；R22部分完成 |
| B-05 | 预案已交付，执行未冻结 | [下一轮预案](next_experiment_decision.md) | A报告已读；优先MMDocRAG协议／本地适配，真实执行矩阵未冻结；独立重检索／utility／完整四路径暂缓但研究缺口保留 |

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

MMDocRAG发现论文与源码Overall F1聚合口径不同；静态审查共10项发现，另列15个未来合成验收规格。新增独立无judge适配器，云端仅虚构输入T01–T14通过；T15因NLTK和rouge-score缺失未完整验证。未import作者模块、未运行其顶层或judge；只提取两个无副作用函数AST做合成对照。Mac T01–T14实测通过，T15仍有依赖缺口。

Mac合成接入已完成；后续仍需明确许可依据，再安排最小真实schema核验和新协议。本批没有下载研究QA、图库或权重，没有启动推理或付费judge。

## A新交付接入与B结论

固定A提交`4dbeab85a0cef2cab8fc2fae928392bf14bc7994`，父提交由交接信息标识为`e3df9d3257d1c6bf4d02ca7f9df868e792cebb44`。仅将七份报告原样纳入当前B交付；未合并A分支，未运行A01，未取回图片。B对CSV结构核验得到172引用记录／20qid／152个不同SHA256：152是按A报告哈希去重的内容数，不是B已收到152文件。A约45MiB只是估计，本次没有图片传输。

最小清单见[B_case_handover_manifest.csv](B_case_handover_manifest.csv)。A原CSV没有path列；本清单按证据ID＋SHA＋尺寸与B@57fa7c4de31f2168a819395859bc638c1c1f25e2已提交的固定S1/S2图片索引核对并补充package_relative_path，标明路径来源commit；未在B本机逐图验证。proposed_deduplicated_target_path为B建议内容寻址布局，不是原生字段或实际落盘声明。优先复用已固定图片；交接时补包根／可访问位置、实际文件清单与总大小／hash；若按SHA去重，可保留172引用到152内容的映射。无交接位置不下载，更不取全量图库。

### 20案例简短审阅规则

这是答案与模型输出已经暴露的事后、非盲描述性案例审查，不是独立验证或因果机制证据。逐例分别记录查询图可辨识性（清楚／部分／无法判断）、S1与S2的支持程度（支持／不支持／无法判断）、干扰／冲突与不确定性；原图／query／完整证据顺序、具体依据、审核者、人工或模型辅助方法及可得revision、时间与媒体SHA须可追溯。视觉核验和mechanism_adjudicated保持独立；未知不强判，不据答错推断模型不会利用证据，不自动重新评分。当前20例visual_review_completed与mechanism_adjudicated全部false。

B-04不再等待A04：现有材料不足以可靠来源聚类；复用既有九场景分层、题级配对bootstrap2000／seed42而不重跑；来源相关性仍未处理，R22部分完成。B-05优先MMDocRAG最小共享证据准备，执行矩阵未冻。A03的any-hit/集合召回、效用logit/概率、CLIP来源、三次中位数/既有performance和4060配置边界五项待冻结意见已写入[next_experiment_decision.md](next_experiment_decision.md)，供A在同一B分支阅读；没有另发消息。

### A原样报告的SHA-256

| 文件（均在a-side/reports/next_stage_20261017/） | SHA-256 |
| --- | --- |
| A_return.md | `a4d4296d282f0de5ea4953ac6902063eb28d489df1ee0e610410bae473e24c4f` |
| case_image_availability.csv | `64c037004394d02028d68c956e96dcb95aaf40303f2cac4dc968d69e63872971` |
| corpus_access_and_license.csv | `332e73942493c1268665fa3c000251f16bd5c0b4a65862918d0e73ac63cf4109` |
| corpus_readiness.md | `44e985beba6b2601f286476e02d205525e2f7e1fc61873ea01118aa82e0a0087` |
| retrieval_selection_protocol.md | `cd9986538cff21c4a4dbe430a3a3ed1ffc9ac339c3d539f2fde354ea6c812afd` |
| routing_and_cost_protocol.md | `99cf50de4c311c38501bb92b47a0479e1a7c9aa16b70d34969c4dfad63dc6911` |
| source_group_feasibility.md | `30d2f64bcc18743b8ebf64ac25f2b7378cffd377c5d25f2e6f8cad444be8c152` |

### 本次执行位置与未完成项

云端Linux完成适配器合成检查，逐项记录[B_mmdocrag_synthetic_validation.cloud.json](B_mmdocrag_synthetic_validation.cloud.json)；不是Mac执行回执。T01–T14通过，T15两项词面指标依赖缺失，禁止自动安装或资源下载。Mac已核对HEAD、干净工作区及AGENTS，并应用本批增量；PR2／任务4更新以实际发布回执为准。

原runtime-v1.10.1的161任务、21927 question-runs、25组完整回执与132次格式失败计错均已完成并保持原样，不再沿用旧“GPU未验证”的状态。此处剩余缺口是新MMDocRAG词面指标的依赖与兼容性验证，不是重开旧实验。原Word／ZIP／备份保留。第二数据集许可、真实schema、split来源与新执行协议仍未解决，不能称第二数据集验证完成。


Mac实际合成回执：[B_mmdocrag_synthetic_validation.mac.json](B_mmdocrag_synthetic_validation.mac.json)，SHA-256：`c36348ae0c005908b89bf6d21b723f16830a060c67c7cd5f1b2dd332594bef28`。darwin／Python 3.12.14；T01–T14通过，T15因nltk与rouge-score缺失未完整验证；未自动安装或下载资源。
