# bf16-cast 消融

## 预先固定本轮门禁与方法

本轮容差为事后设定，依据是两次独立实现的浮点求和顺序差异：身份/排名/sha逐条完全一致；分数绝对差≤1e-6 **或** 相对差≤1e-5（相对分母=abs(live score)，0时仅绝对门禁）视为同一计算。超出即停止，不调阈值。

对保存的float32归一化V/Q逐题计算V@Q[i]，按lexsort(-score,identity)，仅剔除self。V/Q以round-to-nearest-even各转bf16再回float32；不重归一化。此为最终向量量化消融，不等同于重跑bf16编码器。

changed_order=有序top10不同；changed_set=top10集合不同；changed_top3=有序top3不同，另报top3集合变化。换位对=fp32/bf16两者top10并集内相对顺序反转的候选对，报告两个状态下的有符号分差。

对history使用键表sha256_raw→sha256_q95映射，缺失/歧义均显式记录，不猜身份。1e-2抬升判据固定为映射后两池共有top10候选的bf16-cast−fp32分数增量≥0.01，同时history有序top10相同；否则回退池差，不声称唯一因果归因。

运行状态：本轮CPU计算rc=0，容差门禁通过。

## 本轮结果

身份/排名/sha **50/50完全一致**；分数 **50/50在预定容差内**。实际实现噪声最大2.384185791015625e-07，约2.4e-7；A报告的最小相邻间隔8.8e-5，是实际噪声的369.10倍（按2.4e-7为366.67倍）。故这次实现噪声不足以解释该量级换位；这不是对所有池/内核误差的普遍界。

| qid | changed_order | changed_set | changed_top3（有序） | 换位对数 | history在4712池内/10 | history与cast完整顺序一致 |
|---|---|---|---|---:|---:|---|
| mragb:10 | False | False | False | 0 | 4/10 | False |
| mragb:1049 | False | False | False | 0 | 8/10 | False |
| mragb:1051 | False | False | False | 0 | 7/10 | False |
| mragb:1062 | False | False | False | 0 | 1/10 | False |
| mragb:1117 | False | False | False | 0 | 3/10 | False |

## 换位对分数差

正负号按fp32领先候选a减候选b；以下均为本次CPU计算。

### mragb:10

无换位对。

### mragb:1049

无换位对。

### mragb:1051

无换位对。

### mragb:1062

无换位对。

### mragb:1117

无换位对。


## history对照与结论

**回退池差。** 50/50 history raw sha均由键表唯一映射到q95；共享成员的cast最大分数抬升为0.0011141300201416016，全池最大绝对变化为0.0016489624977111816，未同时复现1e-2抬升与history完整换位模式。

键表18,955行与live4,712唯一q95的交集为4282；live中430张不在history键表。逐题history候选缺失数和完整两套top10、共有候选的history−fp32与cast−fp32差值见JSON。池不同首先是候选资格不同，不仅是同候选重排。最终向量量化未能解释观测，因此回退池差排查；没有证明池差足以解释所有分数幅度，也没有排除编码路径差异。

数据来源：本机会话包session/encoded/{V,Q}.npy及pool/qids/encoding、scores_live/history；映射键表见JSON路径。输入sha256、NumPy版本、每对完整精度分差均在JSON。旧精确门禁rc1保留于父提交11bbded；本轮按新写死容差更新原文件。

可定位的池差：history top10的50个候选出现中，仅23个在live4,712池，27个不在该池；逐题分别缺6/2/3/9/7个。缺失候选不可能仅靠对当前池向量cast重新进入top10。共有候选的history−fp32最大为0.0157507061958313，而cast−fp32最大仅0.0011141300201416016。
