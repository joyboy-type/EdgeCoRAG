# 新增可分发派生结果

所有新增文件仅包含模型输出的派生指标；不包含原题、选项文本、gold答案、文档名、原图、原始引用内容或完整模型回答。历史完整私有归档不随Git发布。

| 文件 | 行数 | 范围 |
|---|---:|---|
| no_self_scored_outcomes.jsonl.gz | 18045 | smoke20/dev150/frozen1033 × 五模型 × 三策略；严格评分派生台账 |
| legacy_self_match_scored_outcomes.jsonl.gz | 15495 | 旧自匹配混杂协议1033题；只用于历史对照，不作独立验证 |
| mmdocrag_evaluation_numeric_metrics.csv | 1000 | evaluation/setting15固定200题×五模型；仅引用及词面数值指标 |
| frozen1033_image_groups_and_transitions.csv | 1033 | 图像分簇的匿名组号、场景、cosine→utility精确命中变化类别 |

MRAG唯一键为(protocol,cohort,model,strategy,qid)。correct为冻结严格计分结果；parsed_choice是模型解析出的选项，不是gold。parse_status和generation_error_present保留失败信息，失败不从分母排除。

MMDocRAG唯一键为(dataset_revision,split,setting,q_id,model)，不能跨split按裸qid连接；judge_evaluated始终false，词面分数不代表语义准确率。因许可冲突，原始QA、候选、响应与逐题引用集合仍私有。

图像分组使用内容身份连通关系，匿名组号由组代表身份哈希生成；不是可靠文档/实体来源隔离。query_image_group为860簇，query_or_GT_image_component为564簇。证据变化类别为neither_exact_hit/gain_exact_hit/lose_exact_hit/both_exact_hit，仅作事后关联分析。

聚类bootstrap：每次有放回抽取K个完整簇，求答对差总和/抽中题数总和，10000次、seed42、95%百分位区间，未作多重比较校正。原协议逐题区间按场景分层2000次。不同方法、批次与分母不混合。
