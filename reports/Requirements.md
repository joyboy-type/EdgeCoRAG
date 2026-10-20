# 任务书与仓库文档要求整合

截至 2026年10月17日。对照用户提供的《张.docx》和父提交上的25份仓库Markdown文档，共26份来源。完整清单及核对时的文件哈希见 [document_inventory.json](v1.10.1/document_inventory.json)。未提供的其他文档不在核对范围内。

任务书是研究目标，仓库中的旧提示词、命令和待批准说明是历史参考；它们不会授权本轮启动额外实验。当前实际执行范围由冻结矩阵、用户后续批准与完成回执确定。本轮161任务执行完成，不等于任务书全部研究要求完成。

文档冲突按以下方式处理：旧首页的“尚未完成正式实验”由当前结果入口替代；冻结模型注册表及接收回执保留原始字节和当时状态；原计划“来源隔离、人审S3、端到端性能”等没有因技术通过而自动达成。Qwen3.5 9B及其他可选项目不被改写为必做。

| 编号 | 来源 | 要求 | 状态 | 证据 | 限制或下一步 |
| --- | --- | --- | --- | --- | --- |
| R01 | 张 §1 §6 | 五模型 S0 S1 S2 公平主实验 | 已完成 限冻结范围 | reports/B_comparison.md; reports/v1.10.1/quality.csv | 使用发布的官方候选 top3，不是新 EmbeddingGemma 检索 |
| R02 | 张 §1 §3 §6 | Qwen3.5 9B 与更大模型 | 后置可选 | b-side/configs/model_registry.json | 未运行，不纳入当前五模型计划 |
| R03 | 张 §1 §6 | 各家最佳固定 RAG 补充 | 已完成 限已归档三策略dev选择 | reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv; reports/next_stage_20261019/quality_closure_20261021/paired_differences.csv; reports/next_stage_20261019/quality_closure_20261021/dev_fixed_selection.csv; reports/next_stage_20261019/quality_closure_20261021/C_fixed_rag_and_paths.md | 仅在dev150选择cosine/random/utility，固定平局规则，frozen1033只评估。不是所有RAG系统的全局最优；P4是post hoc Oracle上界，不可部署。 |
| R04 | 张 §2 §4 | MRAG 1353 题 schema 与官方接口核验 | 已完成 | handover/contracts/官方评测接口差异.md; b-side/configs/sources_and_integrity.json | strict_choice_v1 为项目主评分；不冒称复现官方排行榜 |
| R05 | 张 §2 §10 | B_papers 逐论文方法 数值 许可 复现状态 | 部分完成 | reports/B_papers.md; source_manifest.csv; reports/next_stage_20261017/B_paper_evidence.csv; reports/next_stage_20261017/B_paper_table_evidence.csv; reports/next_stage_20261017/B_paper_table_audit.md; reports/next_stage_20261019/quality_closure_20261021/papers_matrix.csv | 六篇逐论文对照已生成，四篇36个原表单元可核验；RAGRouter/VQQP原文数字、分母与适配许可仍未独立核验，不能称全部逐论文复现闭环。 |
| R06 | 张 §2 §4 §9 | 第二数据集 MMDocRAG 或 VisDoM | 部分完成 | reports/next_stage_20261017/B_mmdocrag_evaluation_report.md; reports/next_stage_20261017/B_mmdocrag_evaluation_summary.json; reports/next_stage_20261019/quality_closure_20261021/mmdocrag_judge_feasibility.json; reports/next_stage_20261019/B_judge_protocol.json; reports/next_stage_20261019/B_judge_cost_scenarios.csv; reports/next_stage_20261019/B_judge_feasibility.md; reports/next_stage_20261019/B_visdom_feasibility.json; reports/next_stage_20261019/B_visdom_feasibility.md | 固定200题五模型1000次无judge生成和指标已交付；本批只补judge协议、一致性/人审及非实测条件成本算术。未执行、不得引用语义准确率；README CC BY-NC与HF Apache冲突未澄清。VisDoM仅可行性，依赖/许可/吞吐未验证。 |
| R07 | 张 §2 | Utility MRAG 方法对照 | 待补 A侧 | reports/next_stage_20261019/EdgeCoRAG_无自匹配协议复核结果_20261019.md | 已观察20/150/1033题五模型三策略18045条预测已完成，禁止重跑；不等于完整Utility MRAG方法/论文数字复现，可部署路由仍缺。 |
| R08 | 张 §2 | VQQP 图像降质鲁棒性 | 后置可选 | source_manifest.csv | 未开展 |
| R09 | 张 §3 §5 | 模型 revision 与独立环境 | 已完成 限本次硬件 | configs/model_registry.yaml; provenance/v1.10.1/execution_receipt.json | 原始 registry 中 GPU_unverified 是冻结前状态，实测见独立回执 |
| R10 | 张 §3 §6 | 精度 thinking 采样 输出预算不变 | 已完成 | b-side/configs/protocol_main_v1.json; logs/B_predictions.jsonl.gz | BF16 无量化 无offload greedy64 seed42 TF32关闭 |
| R11 | 张 §6 | 共享证据顺序 内容 topk | 已完成 | logs/B_input_contexts.jsonl.gz; b-side/reception/ | S1 3张；S2 常规5张 Incomplete1张；证据数不同影响解释 |
| R12 | 张 §6 | 输入像素 预处理 实际tokens | 已完成 限所记录字段 | logs/B_predictions.jsonl.gz; logs/B_input_contexts.jsonl.gz | 不同原生视觉tokenizer并非严格等token |
| R13 | 张 §6 | 统一图像尺寸限制与公平预算 | 部分完成 | configs/model_registry.yaml | 共享原图；Qwen像素限制与Gemma soft-token限制不同，不能声称同实际视觉token |
| R14 | 张 §6 | Gemma S3 干扰实验 | 已完成 限补充子集 | reports/v1.10.1/s3_subsets.csv | dev5 holdout2 frozen29，AI图像辅助且label-aware，非人工盲审 |
| R15 | handover/docs/04_S3干扰证据规范.md | S3 字节 近重复 语义审阅与覆盖率 | 已完成 限已批准子集 | b-side/reception/; b-side/configs/final_binding_v1.json | 不能推出普遍语义无关；88排序违例114未决按原序保留；4冻结近重复失败组排除 |
| R16 | 张 §6 | 三次warmup 热启动P50 P95 | 已完成 限生成边界 | reports/v1.10.1/performance.csv; provenance/v1.10.1/execution_receipt.json | 483 warmup不评分；主组100观测；S3 25观测不报P95 |
| R17 | 张 §6 §8 | 检索 编码 索引驻留与完整端到端时延显存 | 待补 | reports/next_stage_20261019/EdgeCoRAG_同机端到端smoke实测_20261020.md; b-side/session_runner.py; tests/test_session_runner.py | 5题32请求技术smoke已完成，禁止重跑；线程与排序已本地闭环，本轮仅CPU编排测试，正式三策略成本、真实机器线程/向量距离、目标设备未获批测量。 |
| R18 | 张 §6 | 能耗与顺序切换成本 | 未测或不适用本轮 | reports/B_comparison.md | 功耗可选；无offload，不将未测值写成0 |
| R19 | 张 §7 §10 | 逐题结构化输出 raw answer 与完整矩阵 | 已交付 | logs/B_predictions.jsonl.gz | 含21,927条，解压后为B_predictions.jsonl；性能不能加入质量分母 |
| R20 | 张 §7 | 处理器完整rendered_prompt与图片清单 | 部分完成 | logs/B_input_contexts.jsonl.gz; reports/next_stage_20261019/quality_closure_20261021/O4_measurement_gap_contract.json; b-side/next_interface_bridge.py; tests/test_next_interface_bridge.py; reports/next_stage_20261019/B_record_gaps.md | 历史rendered_prompt、整卡峰值、系统RAM、能耗不可回溯。新代码只为后续请求记录脱敏实际渲染/整卡采样最大值与host RAM；energy缺测明确标状态。CPU合同通过不等于GPU采样已验证。 |
| R21 | 张 §7 §8 | 未检索到 已出现没答对 检索伤害四类机制 | 部分完成 | reports/next_stage_20261019/quality_closure_20261021/mechanism_breakdown.csv; reports/next_stage_20261019/quality_closure_20261021/D_mechanisms_and_concepts.md; reports/next_stage_20261019/quality_closure_20261021/O2_upgrade_limitations.json; reports/next_stage_20261019/quality_closure_20261021/mechanism_samples.csv; reports/next_stage_20261019/quality_closure_20261021/O2_partition_and_Holm_references.csv; reports/next_stage_20261019/B_mechanism_four_class.csv; reports/next_stage_20261019/B_mechanism_four_class.md; reports/next_stage_20261019/B_mechanism_availability.json | 原a/b/c可重叠，d为模型对质量/成本属性，不能伪造互斥四分区回加1033。公开21927行可算S0/S1伤害；本工作树缺A pools/ranks与公开GT身份联接，a/b和d未知留空。跨零只写不能排除无差异，正式同负载成本待GPU。 |
| R22 | 张 §8 | 按题或文档来源聚类95%配对CI | 已完成 限既有图像关联分量 | reports/next_stage_20261019/quality_closure_20261021/source_cluster_ci.csv; reports/next_stage_20261019/quality_closure_20261021/analysis_receipt.json; reports/next_stage_20261019/B_source_cluster_ci.csv; reports/next_stage_20261019/B_holm_summary.json | D1仅用公开18045行与1033题/564关联分量复算，10000次seed42，描述性、未预注册；15策略均跨零，5预定P3模型比较不跨零。Holm兼容联合矩形数值等同Bonferroni，step-down p另列，不作因果或替代。并非真实文档来源组。 |
| R23 | 张 §7 §8 | 同证据跨模型配对差距 | 已交付 描述性 | reports/v1.10.1/cross_model_paired.csv | 历史交付范围与原始证据保留；后续门槛见 stats_contract，不在本行降级。 |
| R24 | 张 §8 | 类别分层 OCR 图表 跨图关联等 | 已完成 限待审概念映射与敏感性 | reports/next_stage_20261019/quality_closure_20261021/concept_mapping.csv; reports/next_stage_20261019/quality_closure_20261021/concept_sensitivity.csv; reports/next_stage_20261019/quality_closure_20261021/D_mechanisms_and_concepts.md | 概念映射，未经独立标注审定；官方场景不能识别OCR/图表，两类为空不报准确率；提供暂定与全部归其他的敏感性结果。 |
| R25 | 张 §8 §10 | 质量与P95 显存Pareto图 | 已交付 限离线生成 | figures/v1.10.1/quality_latency_pareto.png; figures/v1.10.1/quality_memory_pareto.png | 历史交付范围与原始证据保留；后续门槛见 stats_contract，不在本行降级。 |
| R26 | 张 §9 Gate B1 | 停止普遍超越大模型叙述 | 已执行 | reports/B_comparison.md | 同S1下Gemma与Qwen仍有明显观察差距；聚焦边界与负结果 |
| R27 | 张 §10 | model_registry.yaml | 已交付 | configs/model_registry.yaml | JSON兼容YAML精确镜像，唯一运行权威仍是b-side/configs/model_registry.json |
| R28 | 张 §10 | source_manifest.csv | 已交付 部分核验 | source_manifest.csv | 既有已核验来源与未独立核验字段分开，许可unknown不等于可再分发 |
| R29 | handover/contracts/接口对齐_A侧确认.md | qid raw_id 别名 strict parser 失败保留 | 已完成 | logs/B_predictions.jsonl.gz; b-side/score_minimal.py | raw_output=prediction_raw，格式失败严格计错 |
| R30 | handover/contracts/接口对齐_A侧确认.md | 官方格式独立导出与顺序补齐 | 已完成 限官方格式独立导出 | reports/next_stage_20261019/quality_closure_20261021/official_export_receipt.json; reports/next_stage_20261019/quality_closure_20261021/official_export_validation.json; reports/next_stage_20261019/quality_closure_20261021/official_schema_validation.json; reports/next_stage_20261019/B_official_export_receipt.json; reports/next_stage_20261019/B_official_export_validation.json | 75份新导出补真实选项数、20295全量槽位、117解析失败原样保留；独立源字段反查和固定官方score.py静态字段核验通过。无重解析，未执行官方scorer，官方新分数未测；私有gold/原始输出不入库，非1353新盲测。 |
| R31 | handover/docs/03_证据规则.md | GT与答案仅评分Oracle 离线分析 | 已完成 限本次流程 | b-side/batch_inputs.py; logs/B_input_contexts.jsonl.gz | S3 label-aware审核单独披露；不称整体盲测 |
| R32 | handover/docs/official_pool_provenance.md | 官方候选来源与命中率不当作泄漏证明 | 已披露 | handover/docs/official_pool_provenance.md; reports/v1.10.1/gt_overlap_by_scenario.csv | 本轮top3精确GT哈希命中率已分场景报告，不是独立检索R@k、语义支持或泄漏证明 |
| R33 | a-side/plans/STATUS.md 与 NEXT_STEPS_AND_BLOCKERS.md | A侧 EmbeddingGemma 检索 R@1 R@5 MRR 维度对照 | 待补 A侧 | reports/next_stage_20261019/EdgeCoRAG_无自匹配检索维度消融_20261019.md; reports/next_stage_20261019/A_dimension_inputs_manifest.json; reports/next_stage_20261019/A_retrieval_interface_freeze.json; analysis/next_stage_20261019/build_dimension_inputs.py | 历史1203题×4维排名离线消融已完成，禁止重跑；本轮仅准备dev150×4维no-self输入，utility共6000补分和三策略1800生成待获批GPU；不读gold、不按frozen_test挑维度；部署路由及目标设备仍缺。 |
| R34 | a-side/plans/SPLIT_V2_CHANGES.md 与 REVIEWED_IDS.md | 固定split 暴露登记 相关性限制 | 已完成 并披露限制 | a-side/splits/; b-side/reception/all_20261016/label_aware_audit_registry.json | 20/150/150/1033；1338题精确图像连通大组，不是实体隔离盲测 |
| R35 | handover/freeze/冻结清单模板.md 与 b-side/RUN.md | 代码矩阵配置与环境哈希及完整回执 | 已完成 | provenance/v1.10.1/; b-side/package_hashes.json; b-side/session_runner.py; tests/test_session_runner.py; reports/next_stage_20261019/A_local_preparation_validation.json; reports/next_stage_20261019/quality_closure_20261021/source_archive_supplement.json; reports/next_stage_20261019/quality_closure_20261021/source_pin_reproducibility.csv; reports/next_stage_20261019/B_source_archive_validation.json; reports/next_stage_20261019/B_pin_reproducibility.csv | 历史代码/环境哈希与回执齐全。仅追加source_archive指针；旧键/旧pins/cpu_thread_warning=true保持，14/14归档成员复算，实际A脚本pins为2项，不虚报4项。新增运行代码与旧快照不同已明确。 |
| R36 | b-side/RUN.md 用户后续批准 | runtime v1.10.1 技术失败与正常格式失败分离 | 已完成 | b-side/runtime_change_v1.10.1.json; tests/test_runtime_format_gate.py | 提示词64token严格评分BF16未改；正常格式失败不重试 |
| R37 | 用户备份完成信息与本次请求 | 本地备份 整理 清理可上传版 | 已交付 | reports/Delivery.md; provenance/v1.10.1/delivery_manifest.json | 完整原始备份不动；公开版不含权重图像新增副本认证环境缓存数据库 |

机器可读版本见 [requirements_matrix.csv](v1.10.1/requirements_matrix.csv)。

另见 [两阶段重建说明](Reconstruction.md)：原绑定pin仍锁定v1.10.0依赖文件，补丁目录的旧finalizer/closeout入口不能直接用于全新绑定。本次保留真实执行源码与历史pin，未将该限制伪装为一键复现通过。

A侧决策文档附加要求也纳入如下：实际top3 GT哈希命中与未命中分组准确率、分场景命中率已补到`gt_overlap_strata.csv`和`gt_overlap_by_scenario.csv`（对应R21/R32）；EmbeddingGemma主768维及128/256/512维对照、截断后归一化、索引构建成本、cosine/utility/random策略和四路径Oracle路由矩阵仍归入R07/R33的A侧待办。Oracle路由不能用真实路径输出或测试标签冒充可部署路由器，不能与S2的GT证据Oracle混称。官方5/1对照、D2、S3-mixed属于后置版本，不混入本轮top3表。
