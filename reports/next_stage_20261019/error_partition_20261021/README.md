# 五类互斥操作分区与error_type

复验：`$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out "$DERIVED_ROOT"`

全部21927源行各落一个标签，见partition_rows.csv.gz；主分析为stage=quality/split=frozen_test/condition=S1，每模型1033，按564关联分量配对bootstrap10000次seed42，见partition_summary.csv。主分析5类和=1033。全21927行包含性能重复、holdout与S0/S2，不伪称21927个独立问题，不对它们移植564组CI。

优先级：先S0对S1错→检索伤害代理；其后top10不含GT且S1错→未检索到；含GT且S1错→检索到但答错；不含GT且S1对→无关但未伤害的操作代理；缺身份联接/配对、非主S1或正确且有证据→不可判定（包括非错误项，不能硬塞错误类）。公开S1 official_retrieved*与S2 gt*是角色槽位名，不能比较字符串推断图像命中；本批所有非伤害主S1都未知，前三个无法识别类别的0只是已识别计数，不是其真实率为0。

区间是同一配对问题集中的标签占比区间，以全False参考计算；不是模型间准确率差。未校正与25格家族Holm兼容保守矩形=Bonferroni均报告，描述性、未预注册。跨零只能说不能排除无差异。能力替代单列模型级属性，缺同负载成本/非劣效证据，不能由跨零推出。

error_types.csv.gz逐条保留源行号、原input_error/generation_error的JSON值、parse_status、correct，额外派生error_type；优先级见summary.json，重叠失败另有原始字段可查，不改变任何原状态、分数或日志。未重新parse；wrong-answer与parse_failure分开计数。
