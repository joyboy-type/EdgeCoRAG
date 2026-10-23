# E3 pilot GPU 功率与能耗复算（2026-10-23）

本文件从当前交付分支的原始功率样本重新计算，未开机或新增实验。机器可读结果见 [energy_summary.json](energy_summary.json)。**只覆盖 E3 pilot 的采样窗口；GPU 功耗，非整机能耗。**

## 来源与筛选

原始文件：`reports/next_stage_20261019/gpu_cost_20261021/device_samples.jsonl`。

SHA256：`88927af9710678f757b66fb8953fbfe7461df40ce119d3b06689d601a3492db6`。

仅保留 `power_W` 非 null、非空字符串的记录，将该字段转为有限数值；非空但无效的值必须报错，不悄悄丢弃。时间取 `epoch`，原顺序严格递增，无重复时间戳。本文没有用文件日期或修改时间定义观测窗口。

|项目|值|JSON 字段|
|---|---:|---|
|输入样本数|570|`samples.input_count`|
|有效功率样本数|570|`samples.valid_power_count`|
|空功率排除数|0|`samples.excluded_null_or_empty_power_count`|
|样本算术均值|187.359491228 W|`power_W.arithmetic_mean`|
|最小值|31.25 W|`power_W.minimum`|
|**采样到的最大值**|312.17 W|`power_W.sampled_maximum`|
|窗口时长|83.541253090 s（显示为 83.5 s）|`window.duration_seconds`|
|实际时间间隔梯形积分|4.357463724433 Wh；两位小数 **4.36 Wh**|`integration.energy_wh`|
|样本均值×窗口近似|4.347846298744 Wh；两位小数 **4.35 Wh**|`legacy_4_35_reconciliation.sample_mean_times_window_wh`|

“采样到的最大值”不是连续监测峰值，不能据此声明真实峰值。以上均值为采样值的算术平均，不是按时间加权的平均。

窗口起止：2026-10-21T00:09:12.643921+00:00 至 2026-10-21T00:10:36.185174+00:00（UTC；JSON 的 `window.start_utc/end_utc`）。相邻采样间隔并不完全相等，范围为 0.123382–0.373129 s（`window.interval_seconds_minimum/maximum`）。

## 两种计算口径

实际间隔梯形积分：

```text
E_Wh = Σ[(epoch[i+1] − epoch[i]) × (power[i] + power[i+1]) / 2] / 3600
```

只在相邻有效样本间假定线性插值，不向窗口外外推。本次以节点时间权重求和作代数复核，结果同为 4.357463724433 Wh（JSON 的 `integration.independent_algebraic_check_wh`）。该校验只核算术，不是与 A 分支的独立复算对账。

历史数值对应的样本均值近似：

```text
E_Wh_approx = mean(power_W) × (max(epoch) − min(epoch)) / 3600
```

所得 4.347846298744 Wh 四舍五入为 4.35 Wh。与实际间隔积分的差为 0.009617425688 Wh（`legacy_4_35_reconciliation.trapezoid_minus_sample_mean_approximation_wh`）。两种方法必须分名，不能把梯形积分写成 4.35 Wh。

## 与 A 侧既有回执对账

已通过用户指定分支 `a-side/next-stage-20261017` 读取固定提交 `4312359cdfdb8e39352415b182893f613a07ebda`，未切换交付分支或改动 A 侧历史文件。

- [A 原始 JSON](https://github.com/joyboy-type/EdgeCoRAG/blob/4312359cdfdb8e39352415b182893f613a07ebda/a-side/reports/gpu_cost_20261021/energy_summary.json)，路径 `a-side/reports/gpu_cost_20261021/energy_summary.json`，SHA256 `3ffcd8f2272b8846077d64ba74fff0bd003ae14df82ceb43e06a5d16e3a64c15`。
- [A 原始说明](https://github.com/joyboy-type/EdgeCoRAG/blob/4312359cdfdb8e39352415b182893f613a07ebda/a-side/reports/gpu_cost_20261021/energy_summary.md)，SHA256 `f58fc7a21c61f93c9d09da72a6cb2ab3dabf5dab677c7eb925f3fcd5b5b44112`。
- 本分支 [JSON](energy_summary.json) 的 `legacy_4_35_reconciliation` 指向以上固定来源及本说明；本文反向指向 JSON。A.input 与 B.source 以相同的原始样本 SHA256 建立来源对应，未以同一文件的复制冒充另一轮测量。

|A 回执字段|B 本分支字段|逐字段结果|
|---|---|---|
|`input.device_samples_sha256`|`source.sha256`|完全一致：`88927af9710678f757b66fb8953fbfe7461df40ce119d3b06689d601a3492db6`|
|`input.records_total`|`samples.input_count`|完全一致：`570`|
|`input.power_W_non_null_parsed`|`samples.valid_power_count`|完全一致：`570`|
|`input.power_W_null_or_unparsable`|`samples.excluded_null_or_empty_power_count`|完全一致：`0`|
|`stats.mean_power_W`|`power_W.arithmetic_mean`|完全一致：`187.35949122807017`|
|`stats.min_power_W`|`power_W.minimum`|完全一致：`31.25`|
|`stats.max_power_W`|`power_W.sampled_maximum`|完全一致：`312.17`|
|`stats.window_first_epoch`|`window.start_epoch`|完全一致：`1792541352.6439207`|
|`stats.window_last_epoch`|`window.end_epoch`|完全一致：`1792541436.1851737`|
|`stats.window_seconds`|`window.duration_seconds`|完全一致：`83.54125308990479`|
|`stats.energy_Wh`|`legacy_4_35_reconciliation.sample_mean_times_window_wh`|完全一致：`4.347846298744446`|

另外，A.input 的 `index_residency_sha256/switches_sha256` 也与本分支对应文件逐字节摘要匹配。A Markdown 明确使用“均值功率×窗口时长/3600”；A JSON 的未舍入数值为 **4.347846298744446 Wh**，与本分支同一近似公式结果完全相等，差值为 **0 Wh**。

**两处独立复算一致（同源样本、样本均值×窗口时长/3600的近似口径）。** 这表示两处算术复算一致，不是两次独立功耗测量，也不是实际时间间隔梯形积分与近似算法数值相同。JSON 中 `reference_receipt_verified` 和 `two_independent_recomputations_agree_claim_allowed` 已置为 true，并保存逐字段检查。

过滤规则的边界也保留：A 将空/不可解析功率计为排除；B 对空值排除、对非空非法值报错。当前原始文件的570条功率均有效，因此有效样本集合完全相同；不宣称对任意坏输入的处理策略相同。窗口首末 epoch 完全一致，均以末值减首值定义时长。A 未报告梯形积分，B 的4.357463724432720 Wh（显示4.36 Wh）另列，不覆盖、平均或替换 A 的近似值。
## 论文引用方式与边界

引用 4.35 Wh 时，必须引用本分支 JSON 的 `legacy_4_35_reconciliation.sample_mean_times_window_wh`，并说明它是“GPU 样本均值乘采样时长的近似”。若采用实际时间间隔积分，则引用 `integration.energy_wh`，显示为 4.36 Wh。两者均限于约 83.5 秒的 E3 pilot 窗口，不能用于整机能耗或完整实验成本。

该窗口覆盖预热、热请求及其间活动，未建立逐请求/逐模型能量分配；不能除以请求数后解释为每题完整成本，也不能外推到长答案、索引全量构建或边缘设备。原始功率样本和冻结数字未改动。

