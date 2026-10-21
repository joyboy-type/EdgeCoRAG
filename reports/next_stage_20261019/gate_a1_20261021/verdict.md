# Gate A1 裁决：insufficient_evidence

复验：`$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out "$DERIVED_ROOT"`

Post hoc complementarity is not an evaluated deployable router; matched end-to-end routing cost absent.

描述性、未预注册；配对单位qid，整组重采样564个query/GT图像关联分量，按题加权；basic区间，Holm兼容联合矩形=Bonferroni；非独立题bootstrap。

## (i) post hoc Oracle − dev150最佳固定（frozen1033只评估）

- qwen3vl_4b: 711-623 /1033 = 8.5189pp；95% [6.8051,10.1843]；30对家族校正矩形 [5.8256,11.0783]。
- qwen3vl_8b: 698-627 /1033 = 6.8732pp；95% [5.2818,8.3774]；30对家族校正矩形 [4.2602,9.3363]。
- gemma4_e2b: 505-396 /1033 = 10.5518pp；95% [8.6407,12.4741]；30对家族校正矩形 [7.5032,13.6158]。
- gemma4_e4b: 551-455 /1033 = 9.2933pp；95% [6.9055,11.5097]；30对家族校正矩形 [5.4534,12.5219]。
- qwen35_4b: 673-585 /1033 = 8.5189pp；95% [6.7664,10.2495]；30对家族校正矩形 [5.4505,11.1788]。

Oracle为三种no-self策略的post hoc上界，不是S2 GT路径，也不是可部署路由。dev150选择原样核对，未改动。

## (ii) S0/S1/S2互补

a=!S0&S1; b=!S1&S2; c=S0&!S1; a/b/c may overlap, cannot sum to1033; rescue_union=a|b
这与R03的三策略路径是不同条件，不混成一项实验。逐模型计数/1033与区间见numbers.json、complementarity.csv。失败计错，未重parse。

## (iii) 假设路由成本/节省

1033题×0.03s = 30.99s路由开销；假设跳过25%且每次生成3.0s，净节省743.76s（0.450388元，假设2.18元/时）。均非实测，0%跳过时反而损失30.99秒。IO代理不等于真实路由器耗时。

反例：counterexamples列出S0正确但S1错误的题，以及三种策略均错、Oracle仍失败的题；每例带源JSONL物理行号。互补并不证明有可学习且省成本的部署策略。

文件、SHA及精确筛选条件见numbers.json.source_sha256/filters。校正区间跨零一律“不能排除无差异”；不写显著、因果或普遍替代。

复议条件（区间下界>0 且互补率≥15%）系事后设定的写作形态规则，不作统计推断。
