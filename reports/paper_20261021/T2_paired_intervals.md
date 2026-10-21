# T2 配对差异与描述性区间

来源：`reports/v1.10.1/paired_comparisons.csv`；筛选条件：`split=frozen_test`。来源行号为含表头的文件物理行号。

口径：同模型、同一批配对题；分母 **1,033**，**改善+退化+不变 = 1,033**。Δ与区间均为百分点（pp），仅显示四舍五入到两位小数，CSV保留原精度；不重新计算区间。

方法：`method=paired_scenario_stratified_bootstrap`（原值）；**2,000 次重采样、seed 42、描述性、未预注册**。本表未做多重比较校正，不能套用no-self策略比较的来源聚类/Holm口径。

| 模型 | 对比 | Δ(pp) | 95% 区间 | 改善题数 | 退化题数 | 来源行号 | method |
|---|---|---:|---|---:|---:|---:|---|
| Qwen3-VL 4B | S1 − S0 | -2.52 | [-5.13, +0.19] | 79 | 105 | 17 | paired_scenario_stratified_bootstrap |
| Qwen3-VL 4B | S2 − S1 | +11.81 | [+9.20, +14.42] | 161 | 39 | 18 | paired_scenario_stratified_bootstrap |
| Qwen3-VL 4B | S2 − S0 | +9.29 | [+6.68, +12.29] | 159 | 63 | 19 | paired_scenario_stratified_bootstrap |
| Qwen3-VL 8B | S1 − S0 | -0.29 | [-2.61, +2.13] | 76 | 79 | 20 | paired_scenario_stratified_bootstrap |
| Qwen3-VL 8B | S2 − S1 | +10.65 | [+8.23, +13.07] | 143 | 33 | 21 | paired_scenario_stratified_bootstrap |
| Qwen3-VL 8B | S2 − S0 | +10.36 | [+7.74, +12.97] | 160 | 53 | 22 | paired_scenario_stratified_bootstrap |
| Gemma 4 E2B | S1 − S0 | -0.87 | [-3.49, +1.84] | 103 | 112 | 23 | paired_scenario_stratified_bootstrap |
| Gemma 4 E2B | S2 − S1 | +7.26 | [+4.65, +9.97] | 141 | 66 | 24 | paired_scenario_stratified_bootstrap |
| Gemma 4 E2B | S2 − S0 | +6.39 | [+3.58, +9.20] | 154 | 88 | 25 | paired_scenario_stratified_bootstrap |
| Gemma 4 E4B | S1 − S0 | +2.90 | [+0.19, +5.71] | 116 | 86 | 26 | paired_scenario_stratified_bootstrap |
| Gemma 4 E4B | S2 − S1 | +6.39 | [+3.87, +9.00] | 128 | 62 | 27 | paired_scenario_stratified_bootstrap |
| Gemma 4 E4B | S2 − S0 | +9.29 | [+6.39, +12.20] | 167 | 71 | 28 | paired_scenario_stratified_bootstrap |
| Qwen3.5 4B | S1 − S0 | +0.97 | [-1.74, +3.78] | 110 | 100 | 29 | paired_scenario_stratified_bootstrap |
| Qwen3.5 4B | S2 − S1 | +3.68 | [+1.16, +6.49] | 124 | 86 | 30 | paired_scenario_stratified_bootstrap |
| Qwen3.5 4B | S2 − S0 | +4.65 | [+1.65, +7.74] | 160 | 112 | 31 | paired_scenario_stratified_bootstrap |

## 四条读法（按用户原文保留）

1. 跨零不写成"无差异"。以下四条跨零，只能写"不能排除无差异"：
   Qwen3-VL 4B S1−S0 [−5.13, +0.19]、Qwen3-VL 8B S1−S0 [−2.61, +2.13]、
   Gemma 4 E2B S1−S0 [−3.49, +1.84]、Qwen3.5 4B S1−S0 [−1.74, +3.78]。
2. 唯一不跨零的 S1−S0 是 Gemma 4 E4B：+2.90 [+0.19, +5.71]，
   但仍是描述性、未做多重比较校正，不得写成"显著有益"。
3. S2−S1 全部不跨零（+3.68 至 +11.81），是全文最强信号。
4. 三个对比共用同一批题，区间不能相互叠加或相减。

“全文最强信号”是上述原文的描述性读法，不表示经统一检验或多重校正后已建立跨指标强弱排序。

源CSV SHA256：`04dc6783dbc865c2f26185d8ef6fc65083a91fb238e4f57efb12b824c53a046e`。本次15行及指定三行交叉核对一致，rc=0。
