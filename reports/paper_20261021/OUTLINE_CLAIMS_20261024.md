# 提纲与主张表（执行结果版，2026-10-25）

本轮仅确定提纲与证据边界；摘要、结果章和主初稿尚未修改。正文结果按A→B→C排列；成本与基础设施压缩为支撑小节/附录，D只在Limitations。摘要后续限定五句：第1句问题、第2句协议、第3句A、第4句B、第5句C；D不进入摘要。

共同用语约束：不使用“证明”“因果”“数量无关”；不称“等价”；“显著”只有附相应检验才可使用，本轮不使用。跨零只写“cannot exclude no difference／无法与无差异区分”。测得比例不写成模型常数或外推工具。所有表在表注注明题分母、证据张数和区间单位；检索排序表明确无生成3/5张条件，k=5不冒称输入5张。

## §4.1 A：图片数匹配后的正确证据净增益

表注：分母956题；S1=3张检索证据，S2@3=原序前3张GT；原S2参照为同956题、5张GT，均另含query图。原始1,033题中的77道单图题不纳入本主分析。

|节名|主张|数字与区间|证据路径|允许措辞|禁止措辞|
|---|---|---|---|---|---|
|§4.1 A · Qwen3-VL-4B|同张数条件净增益|567/956→665/956；+10.25 pp [+7.53, +12.87]|`r1_equal_count_20261024.json:models.qwen3vl_4b.groups.primary956`|图片数匹配为3张的956题上，观察到正净增益|证明正确性的因果作用；数量无关；写成全量1,033题结论|
|§4.1 A · Gemma E2B|同张数条件净增益|351/956→408/956；+5.96 pp [+3.24, +8.58]|`r1_equal_count_20261024.json:models.gemma4_e2b.groups.primary956`|图片数匹配为3张的956题上，观察到正净增益|证明正确性的因果作用；数量无关；写成全量1,033题结论|
|§4.1 A · Gemma E4B|同张数条件净增益|403/956→462/956；+6.17 pp [+3.45, +8.68]|`r1_equal_count_20261024.json:models.gemma4_e4b.groups.primary956`|图片数匹配为3张的956题上，观察到正净增益|证明正确性的因果作用；数量无关；写成全量1,033题结论|
|§4.1 A · Qwen3-VL-8B|同张数条件净增益|560/956→659/956；+10.36 pp [+7.95, +12.66]|`r1_equal_count_20261024.json:models.qwen3vl_8b.groups.primary956`|图片数匹配为3张的956题上，观察到正净增益|证明正确性的因果作用；数量无关；写成全量1,033题结论|
|§4.1 A · Qwen3.5-4B|同张数条件净增益|540/956→605/956；+6.80 pp [+4.18, +9.52]|`r1_equal_count_20261024.json:models.qwen35_4b.groups.primary956`|图片数匹配为3张的956题上，观察到正净增益|证明正确性的因果作用；数量无关；写成全量1,033题结论|
|§4.1 A · 总述|五模型净增益+5.96–10.36 pp，区间全>0；严格标准2/5|70%规则：L3>0且L3≥0.70×同956题Delta5；各模型点估计比及下界比见报告|`r1_equal_count_20261024.json:models.*.groups.primary956.{ci95,retained_ratio,lower_bound_reference_ratio,criterion}`|五模型均有正区间，只有2/5达到严格保留标准|全部保留≥70%；把点估计比当下界比；等价；显著（无对应检验）|

区间：题级、场景分层配对bootstrap，2,000次、seed 42，95% percentile线性插值、描述性，无多重比较校正；不是冻结564分量聚类区间。救回/伤害/不变及同对/同错均在同956题统计，见同一JSON `counts/proportions/ci95`。新旧运行硬件/栈差异保留为解释边界。

## §4.2 B：接口可得率与命中后表现

表注：原主实验分母1,033题；S1=检索top3、3张证据，原S2通常5张GT、77道Incomplete仅1张，此表只计算S1。命中后条件正确率分母516；五模型命中题集合一致，不只是数量相同。

|节名|主张|数字与区间|证据路径|允许措辞|禁止措辞|
|---|---|---|---|---|---|
|§4.2 B · 可得率|接口精确身份的top3可得率|516/1,033=49.95%；描述性区间[46.95%,52.95%]|`frozen_numbers.json:id=retrieval.top3_hit`；`decomposition_20261021.json:models.*.{r,ci.r}`；`../next_stage_20261019/error_partition_20261021/join_v2.csv.gz:{model,qid,joinable,top3_gt_hit}`|共享检索在五模型上提供同一命中题集|语义证据充分率；可部署准确率上界；模型独立检索获得|
|§4.2 B · Qwen3-VL-4B|命中后的条件正确率|336/516=65.12%；[60.97%,69.25%]|`decomposition_20261021.json:models.qwen3vl_4b.{hit_correct,hit_n,u,ci.u}`；`../next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`|在本文命中集合上的描述性读数|模型常数；可跨题/跨策略预测；因果；机制归因|
|§4.2 B · Gemma E2B|命中后的条件正确率|219/516=42.44%；[38.22%,46.64%]|`decomposition_20261021.json:models.gemma4_e2b.{hit_correct,hit_n,u,ci.u}`；`../next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`|在本文命中集合上的描述性读数|模型常数；可跨题/跨策略预测；因果；机制归因|
|§4.2 B · Gemma E4B|命中后的条件正确率|236/516=45.74%；[41.39%,50.09%]|`decomposition_20261021.json:models.gemma4_e4b.{hit_correct,hit_n,u,ci.u}`；`../next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`|在本文命中集合上的描述性读数|模型常数；可跨题/跨策略预测；因果；机制归因|
|§4.2 B · Qwen3-VL-8B|命中后的条件正确率|343/516=66.47%；[62.35%,70.46%]|`decomposition_20261021.json:models.qwen3vl_8b.{hit_correct,hit_n,u,ci.u}`；`../next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`|在本文命中集合上的描述性读数|模型常数；可跨题/跨策略预测；因果；机制归因|
|§4.2 B · Qwen3.5-4B|命中后的条件正确率|324/516=62.79%；[58.53%,66.88%]|`decomposition_20261021.json:models.qwen35_4b.{hit_correct,hit_n,u,ci.u}`；`../next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`|在本文命中集合上的描述性读数|模型常数；可跨题/跨策略预测；因果；机制归因|

范围42.44–66.47%来自上述逐模型比例，不是一个合并估计或置信区间。B区间沿用题级bootstrap 10,000次、seed 42，描述性；不得与A的2,000次场景分层区间或冻结聚类区间混用。场景层结果只作补充，Incomplete仅5个命中题（`DECOMPOSITION.md:§七`、`scenario_extrapolation_20261021.json`），不据此提机制。

## §4.3 C：当前池维度压缩取舍

表注：当前4,712身份池，分母1,203题，GT通常5张、Incomplete为1张；纯检索排序不使用生成3/5张条件。统一FP32截断重归一化，k=1/5/10分别评价；V复用，Q为同协议新补编码。

|节名|主张|数字与区间|证据路径|允许措辞|禁止措辞|
|---|---|---|---|---|---|
|§4.3 C · 载荷|256维载荷为768维的1/3|4,825,088 vs 14,475,264字节；仅V理论载荷，无区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.{V_payload_bytes,payload_ratio}`|理论向量载荷降至1/3|完整索引、显存、整机能耗或端到端成本降至1/3|
|§4.3 C · top1 any-hit|256对768维的逐项取舍|433/1,203 vs 451/1,203；差-1.496259 pp；本次未新增区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.groups.all.hit_at_1`|五项损失均小于预设3 pp/百分制单位容差|统计等价；无损；证明；显著；只挑top5不报top1损失|
|§4.3 C · top5 any-hit|256对768维的逐项取舍|819/1,203 vs 815/1,203；差+0.332502 pp；本次未新增区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.groups.all.hit_at_5`|五项损失均小于预设3 pp/百分制单位容差|统计等价；无损；证明；显著；只挑top5不报top1损失|
|§4.3 C · top10 any-hit|256对768维的逐项取舍|931/1,203 vs 925/1,203；差+0.498753 pp；本次未新增区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.groups.all.hit_at_10`|五项损失均小于预设3 pp/百分制单位容差|统计等价；无损；证明；显著；只挑top5不报top1损失|
|§4.3 C · 宏Recall@5|256对768维的逐项取舍|0.307190 vs 0.307190；差+0.000000 pp；本次未新增区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.groups.all.recall_at_5`|五项损失均小于预设3 pp/百分制单位容差|统计等价；无损；证明；显著；只挑top5不报top1损失|
|§4.3 C · 完整MRR|256对768维的逐项取舍|0.501250 vs 0.507917；差-0.666745 百分制单位；本次未新增区间|`r2_dimension_compress_20261024.json:dimensions.{256,768}.groups.all.mrr`|五项损失均小于预设3 pp/百分制单位容差|统计等价；无损；证明；显著；只挑top5不报top1损失|

容差原规则为任一检索指标下降严格>0.03则该维不满足；恰为0.03不触发，本轮五项实际损失均<0.03。MRR×100是百分制单位，不是正确率百分点。四维128/256/512/768完整列在结果报告，不把256写成事后挑出的最优维度；不混用历史18,955池的384/383命中数。

## Limitations D：本任务未产生长输出，无法估计长度成本

表注：三模型，各cap各20题，3张cosine证据（另加query）、不是5张GT条件；两档同题、同卡、同提示。原始回答为选择题选项。

|节名|主张|数字与区间|证据路径|允许措辞|禁止措辞|
|---|---|---|---|---|---|
|Limitations D · Qwen3-VL-4B|两档长度一致，长回答边际成本不可估计|cap 2/256，平均均2.00 token，每档20题；长度比1.00≤3；DeltaN=0，边际量null；无区间|`r3_normal_output_cost_20261024.json:models.qwen3vl_4b.{caps,length_status,generation_ms_per_extra100_tokens}`|在本任务和提示下，长度档位未生效；记录保留，不重跑|正常长回答成本已测得；将null填0；增大上限导致更长回答；显著（无检验）|
|Limitations D · Gemma E2B|两档长度一致，长回答边际成本不可估计|cap 2/256，平均均2.00 token，每档20题；长度比1.00≤3；DeltaN=0，边际量null；无区间|`r3_normal_output_cost_20261024.json:models.gemma4_e2b.{caps,length_status,generation_ms_per_extra100_tokens}`|在本任务和提示下，长度档位未生效；记录保留，不重跑|正常长回答成本已测得；将null填0；增大上限导致更长回答；显著（无检验）|
|Limitations D · Gemma E4B|两档长度一致，长回答边际成本不可估计|cap 2/256，平均均2.00 token，每档20题；长度比1.00≤3；DeltaN=0，边际量null；无区间|`r3_normal_output_cost_20261024.json:models.gemma4_e4b.{caps,length_status,generation_ms_per_extra100_tokens}`|在本任务和提示下，长度档位未生效；记录保留，不重跑|正常长回答成本已测得；将null填0；增大上限导致更长回答；显著（无检验）|

## 支撑小节／附录：成本与可审计基础设施

表注：成本新测量仍为每模型每档20题、3张cosine证据，原GT5张条件未参与；索引身份/批不变性属于检索基础设施，不设置生成3/5张对照。

|节名|主张|数字与区间|证据路径|允许措辞|禁止措辞|
|---|---|---|---|---|---|
|§4.4／附录 · 成本|保留此次短答条件耗时、显存与GPU功耗画像|每档20题；P50/P95、encoder/generation分项、采样峰值及两种能耗算法全列，非推断区间|`r3_normal_output_cost_20261024.json:models.*.caps`；同名报告|短答任务的同卡描述性成本画像|与旧卡pilot合并比较；采样最大值当连续峰值；GPU功耗当整机；长答边际成本|
|方法／附录 · 复核|冻结协议、身份对账与批不变性提供可追溯支撑|沿用既有回执，不与A/B/C混分母或改写冻结数字|`../next_stage_20261019/pixel_identity_18955_keys_20261021/pixel_identity_18955_keys.csv`；`../next_stage_20261019/gpu_scores_20261021/scores_manifest.json`；`frozen_numbers.json`的相应source_catalog|可按归档路径复核输入身份与排序条件|新方法；新模型；可部署路由；跨数据集自主检索验证|

路径约定：表内同名JSON/MD相对本目录；`frozen_numbers.json`全路径为`reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`。新实验数字只来自三份新JSON，冻结数字不变。此提纲仅规定后续修改顺序和允许表述，未执行摘要或主结果章改写。
