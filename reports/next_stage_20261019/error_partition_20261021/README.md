# 主表：top3 GT命中 × S1答对（2×2），伤害另列

v3优先级分区已降为对账附录，不作主表。第四类“其余（含命中且答对）”是“完整输入且答对”的残余桶，不等同于“证据无关”。优先级定义为事后设定。

主表见 `main_2x2/main_table.csv`；每模型固定1033题。复验（新目录）：
`$PY analysis/next_stage_20261019/error_crosstab.py --out "$NEW_CROSSTAB_DIR"`

共享检索自检要求五模型逐qid命中布尔一致，且命中/未命中计数一致，否则停止。此次均为516/517。四格互斥且合计1033，缺输入0。伤害=S0对且S1错，占比以1033为分母；是答错题子集，与2×2重叠，不得与四格相加，不作因果解释。失败沿用原标记、计错且保留分母，不重解析；不作任何frozen选择。

|模型|未命中但答对|未命中且答错|命中但答错|命中且答对|命中数|未命中数|伤害（占1033）|
|---|---:|---:|---:|---:|---:|---:|---:|

|qwen3vl_4b|259|258|180|336|516|517|105 (10.16%)|
|qwen3vl_8b|237|280|173|343|516|517|79 (7.65%)|
|gemma4_e2b|147|370|297|219|516|517|112 (10.84%)|
|gemma4_e4b|191|326|280|236|516|517|86 (8.33%)|
|qwen35_4b|239|278|192|324|516|517|100 (9.68%)|

## 历史联接与分区附录

v1/v2原条件和历史结论保留，不作为主表。v3本轮仅更名，计数/归属/区间未变；见v3/label_migration.json。v3/validation为90be65d时的历史回执，逐字节复验应在该提交运行；修订后的主表复验用上述命令。

# v2命名空间核验与原定义重算（基线20d1505）

能联：通过现成context映射，五模型各1033/1033题可与数据集gold精确联接，总5165/5165（100%）。
不能联：S1 evidence_ids_order实际是qid#official_retrievedN角色槽位，不能直接与image:* gold别名字符串相等比较，直接同命名空间比例0%。
只能联一部分：本次不存在部分缺输入，映射后真正不可判定为每模型0/1033；此前“缺映射”是漏查现有B_input_contexts，不是历史数据缺失。

## 联接证据与复验

现成链：prediction.context_key → logs/B_input_contexts.jsonl.gz 的input.evidence[evidence_id].sha256 → image:<sha256> → retrieval-formal.approved.json的gold[qid]。每条核对context的qid/condition/证据列表行序；S2所有GT集合映射后再与独立归档gold核对，5165/5165完全一致。无需图像、解码、模型或新的别名推断。该等价只针对本次原baseline context的SHA与dataset gold身份，不能外推为18955历史索引的image:*后缀等于重编码文件原始字节SHA。

20题已按group表既有顺序取样，原gold/evidence列表打印并另存仓库外私有probe；公开只保存probe哈希/比例，不推送raw gold映射。全量复算不只依赖这20题。namespace_v2.json含源文件SHA、计数和定义冲突。

```sh
$PY analysis/next_stage_20261019/join_error_partition.py --gold-controls "$GOLD_CONTROLS" --out "$NEW_JOIN_OUT" --private-probe "$NEW_PRIVATE_PROBE" --print-probe
```

GOLD_CONTROLS必须为合法已有归档，NEW_PRIVATE_PROBE须在仓库外且不存在。join_v2.csv.gz只含源行号、模型/qid、正确标记、GT命中布尔及原定义标记，不复制原题/答案或gold列表。

## 分区定义冲突：保留原条件，不假称互斥

原定义逐字实现：a=gold∩top3为空；b=相交且S1错；c=S0对且S1错；d=S1错且不相交且非c。d是a的子集，c可与a或b重叠；S1对且命中的题不落入任何类。四个原条件无法同时满足“互斥且相加=1033”。不能把完整输入但未覆盖的正确题改写为不可判定。

partition_v2.csv因此明确标记original_requested_overlapping_flag_NOT_partition：保存原条件计数/占比、未校正95%区间与20标记家族校正区间，不改定义，不声称已交付互斥分区。以qwen3vl_4b为例：296题多重归类、336题无类，四类合计993而非1033；五模型详细诊断见namespace_v2.json。当前唯一阻塞是定义矛盾，映射已闭环。

此前产物保留为历史派生，原日志和状态不动；下方旧说明中的“缺GT联接/未知”已由本次纠正，不得继续当作实际数据缺失。

---

## 历史v1说明（保留原文供对账，联接缺口结论已更正）

# 五类互斥操作分区与error_type

复验：`$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out "$DERIVED_ROOT"`

全部21927源行各落一个标签，见partition_rows.csv.gz；主分析为stage=quality/split=frozen_test/condition=S1，每模型1033，按564关联分量配对bootstrap10000次seed42，见partition_summary.csv。主分析5类和=1033。全21927行包含性能重复、holdout与S0/S2，不伪称21927个独立问题，不对它们移植564组CI。

优先级：先S0对S1错→检索伤害代理；其后top10不含GT且S1错→未检索到；含GT且S1错→检索到但答错；不含GT且S1对→其余（含命中且答对）的操作代理；缺身份联接/配对、非主S1或正确且有证据→不可判定（包括非错误项，不能硬塞错误类）。公开S1 official_retrieved*与S2 gt*是角色槽位名，不能比较字符串推断图像命中；本批所有非伤害主S1都未知，前三个无法识别类别的0只是已识别计数，不是其真实率为0。

区间是同一配对问题集中的标签占比区间，以全False参考计算；不是模型间准确率差。未校正与25格家族Holm兼容保守矩形=Bonferroni均报告，描述性、未预注册。跨零只能说不能排除无差异。能力替代单列模型级属性，缺同负载成本/非劣效证据，不能由跨零推出。

error_types.csv.gz逐条保留源行号、原input_error/generation_error的JSON值、parse_status、correct，额外派生error_type；优先级见summary.json，重叠失败另有原始字段可查，不改变任何原状态、分数或日志。未重新parse；wrong-answer与parse_failure分开计数。

## v3 优先级分区

用户现已明确优先级，v2“定义矛盾”的阻塞仅属于历史原条件，不再适用于v3。先登记的完整规则见 priority_definition_v3.md：优先级定义为事后设定；真正缺输入单列，输入完整按伤害→未检索到→检索到但答错→其余依次唯一归类。v3不覆盖旧表，不改原日志。

### v3 本次结果（每模型固定1033题）

|模型|检索伤害|未检索到|检索到但答错|其余（含命中且答对）|不可判定|四类合计|
|---|---:|---:|---:|---:|---:|---:|
|qwen3vl_4b|105 (10.16%)|191 (18.49%)|142 (13.75%)|595 (57.60%)|0 (0.00%)|1033|
|qwen3vl_8b|79 (7.65%)|223 (21.59%)|151 (14.62%)|580 (56.15%)|0 (0.00%)|1033|
|gemma4_e2b|112 (10.84%)|310 (30.01%)|245 (23.72%)|366 (35.43%)|0 (0.00%)|1033|
|gemma4_e4b|86 (8.33%)|277 (26.82%)|243 (23.52%)|427 (41.34%)|0 (0.00%)|1033|
|qwen35_4b|100 (9.68%)|215 (20.81%)|155 (15.00%)|563 (54.50%)|0 (0.00%)|1033|

各行唯一归类；5×1033=5165行，缺输入0。规则为事后设定，第四类为剩余完整输入题（本批全为S1正确），不能解释成已证明证据无关；伤害不作因果解释。分量bootstrap区间见 v3/partition_v3.csv，逐题标签见 v3/assignments_v3.csv.gz。需求状态不变。
复验：`$PY analysis/next_stage_20261019/priority_error_partition.py --out "$NEW_PARTITION_DIR"`；四个产物可逐字节重放，见v3/validation/replay.json。
