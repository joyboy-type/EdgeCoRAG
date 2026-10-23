# 金标证据相对检索证据的逐题转换

我们在同一冻结题集上，按题配对检索证据条件S1与金标证据条件S2。每模型固定分母为1,033题，划分为“救回”（S1错、S2对）、“伤害”（S1对、S2错）和“不变”（两条件同对或同错）；三类互斥且穷尽。“不变”仅指正确性标记不变，不要求输出文本相同。[M；J.models.*.n/categories]

|模型|救回：题数；占比 [95%区间]|伤害：题数；占比 [95%区间]|不变：题数；占比 [95%区间]|S2−S1：pp [95%区间]|
|---|---|---|---|---|
|Qwen3-VL-4B|161；15.59% [13.46, 18.01]|39；3.78% [2.71, 5.03]|833；80.64% [78.22, 82.96]|+11.81 [9.20, 14.42]|
|Qwen3-VL-8B|143；13.84% [11.81, 15.97]|33；3.19% [2.23, 4.26]|857；82.96% [80.64, 85.09]|+10.65 [8.23, 13.07]|
|Gemma 4 E2B|141；13.65% [11.62, 15.78]|66；6.39% [4.94, 7.94]|826；79.96% [77.54, 82.38]|+7.26 [4.65, 9.97]|
|Gemma 4 E4B|128；12.39% [10.36, 14.43]|62；6.00% [4.65, 7.36]|843；81.61% [79.19, 84.03]|+6.39 [3.87, 9.00]|
|Qwen3.5-4B|124；12.00% [10.16, 14.13]|86；8.33% [6.68, 9.97]|823；79.67% [77.15, 81.99]|+3.68 [1.16, 6.49]|

每行分母均为1,033；三类占比区间的单位为%，净增益及其区间的单位为pp。数字逐项对应[J] `models.{model}.categories.{rescued,harmed,unchanged}.{n,percent,ci95_percent}`及`delta_pp/net_ci95_pp`。净增益等于救回比例减伤害比例，不能用两列区间端点相减求区间。表内区间均由保持场景样本数的题级配对bootstrap获得（2,000次、seed 42、双侧95% percentile、线性分位数插值），属于描述性区间，非聚类区间，未作多重比较校正。冻结表相关区间采用564分量聚类bootstrap；与本节题级、场景分层配对口径不是同一套，不互换引用。[J.method；J.reporting_scope.interval_distinction] 三类题数、净增益及其区间与既有配对表[V]逐模型一致；三类占比区间为本次新增离线统计。[J.models.*.official_interval_reproduced]

**正确证据相对检索证据的净增益为 +3.68 至 +11.81 pp（五模型）。**[V：frozen_test，S2 − S1；J.models.*.delta_pp]

作为模型间的描述性对照，Qwen3-VL-4B的伤害率为3.78%，Qwen3.5-4B为8.33%[J.models.{qwen3vl_4b,qwen35_4b}.categories.harmed.percent]。这提示不同模型对证据条件变化的边际响应可能不同、证据质量的边际价值可能随模型而异；不是质量的因果效应，也不是整个模型家族的规律。这两个读数不是五模型伤害率的最小值与最大值，不能代替全表比较。

**证据数量声明：** S1为3张检索图，S2为标注答案图（通常5张，Incomplete为1张）[M.evidence_ids_order]。本节度量的是“正确证据条件 vs 检索证据条件”的总差异，同时包含证据正确性与证据数量，本文未分离二者。因此，上述“救回/伤害”仅是条件间正确性转换的操作性标签，不是逐题机制归因，不估计等预算的纯质量效应或可部署收益。解析失败仍计入完整分母，不将其排除或另选子集。[J.models.*.parse_failures]

同池同预算下，Qwen3-VL-4B的utility较cosine、random多答对5、8题。配对95%区间为[−1.45,2.42]、[−1.26,2.90] pp，均无法与无差异区分；仅作本模型、本题集的描述，不支持策略优势或等价判断。[R3]

---

**来源定位（供审阅，非新增论文主张）：**

- [M] `logs/B_predictions.jsonl.gz`，筛`stage=quality & split=frozen_test & condition∈{S1,S2}`；字段`model_key/qid/scenario/correct/parse_status/evidence_ids_order`。输入摘要与筛选行数见[J.sources.predictions]。
- [V] `reports/v1.10.1/paired_comparisons.csv`，按`model_key/split/comparison`定位，字段`improvements/regressions/unchanged/delta_pp/ci_low_pp/ci_high_pp`。此处不编造冻结数字id，冻结表没有同名S2_minus_S1条目。
- [J] `reports/paper_20261021/r1_transitions_20261023.json`，含计算前固定口径、输入SHA256、逐题配对标记、题单摘要及所有区间；完整计算前口径亦保存在`protocol_text`中。
- [R3] `reports/paper_20261021/r3_paired_bootstrap_20261023.json`，`results[0:2]`。该段使用题级配对bootstrap、10,000次、seed 42，区别于上表场景分层口径；两组比较都保留，不独立成节。
