# R3：同池同预算策略的配对不确定性

**结论：** Qwen3-VL-4B的utility答对数点估计高于cosine与random，但两项配对区间均含零，均**无法与无差异区分**。不能据此写“utility更优”，也不能写策略等价。R3保留首位作为同池策略比较小节，主张收紧为可复核的策略取舍及逐题转换画像。

## 计算前登记与来源

- 登记已随方向稿提交：`9563209`，见 [ADVISOR_BRIEF.md](ADVISOR_BRIEF.md) 末节；登记文件SHA256：`395ada36687581d829dc99153c7e00f95dd7f62468d62417e96e99ce1d0d0720`。本次结果不回填登记正文，不改划分、抽样算法或比较项。
- **J** = [r3_paired_bootstrap_20261023.json](r3_paired_bootstrap_20261023.json)。下表每行的完整数值、分母与来源由J.results及J.provenance绑定。JSON SHA256：`db4009218fdad6c7204fb10233e5579c0987ccd392e121601ee9fe008f48183b`。
- 核验私有归档全部15个预测文件、18,045条记录；smoke/dev/frozen分别每模型60/450/3,099条，均为三策略的合计。按`qid/selection_strategy`无重复、无缺行，split题单互斥，文件摘要逐个匹配`closeout-manifest.json`（J.archive_coverage）。这些检查不把三个split合并成统计样本。
- 本次估计仅用frozen_test的Qwen3-VL-4B，三策略各1,033题（J.results[*].n），同一top10候选取3。输入为`continuous-complete-backup/frozen_test/results/generate-qwen3vl_4b/predictions.jsonl`的`qid/selection_strategy/selected_ids/final_output`；绝对路径与SHA256见J.provenance.raw_*。逐题正确标记来自`corrected-protocol-scoring/frozen_test__qwen3vl_4b__{utility,cosine,random}.private.json`的`per_question.correct`，三者均核对到同一原始预测摘要与金标答案摘要，并逐题匹配评分raw_output和预测final_output。没有重新解析、重跑推理或排除失败题。
- 金标答案原始文件、bundle路径及摘要见J.provenance.gold_answers_* / bundle_*；题号按字典序排列，以UTF-8 `qid+换行`串联（含末尾换行）计算SHA256：`2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc`。J.paired_correctness保存题号与三策略正确标记，不复制私有答案或题干。

## 两项配对结果

单位为pp；准确率差方向均为utility减对照。改善指utility对、对照错；退化相反。同对/同错为两者正确标记一致的题。

|比较|答对数：utility/对照|点估计pp|95%题级配对区间pp|改善/退化题|同对/同错题|判断及数字入口|
|---|---|---|---|---|---|---|
|utility−cosine|623/618|+0.48|[-1.45, +2.42]|56/51|567/359|无法与无差异区分（J.results[0]）|
|utility−random|623/615|+0.77|[-1.26, +2.90]|65/57|558/353|无法与无差异区分（J.results[1]）|

## 固定计算口径与复算入口

题级配对bootstrap，有放回抽取与原题单等长的题索引；每次抽样保留同题三个策略的标记，两项差共用抽样。10,000次、seed 42、NumPy Generator(PCG64)、双侧95% percentile区间，分位数线性插值（J.method）。下列代码直接从J复算，不需要私有答案；数值运算版本见J.method.numpy/python：

```python
import json
import numpy as np
with open('reports/paper_20261021/r3_paired_bootstrap_20261023.json') as f:
    j = json.load(f)
rows = j['paired_correctness']  # 已按qid字典序排列
assert [r['qid'] for r in rows] == sorted(r['qid'] for r in rows)
a = np.array([[int(r['utility_correct']) - int(r[s + '_correct'])
               for s in ['cosine', 'random']] for r in rows], dtype=np.int8)
n = len(rows)
rng = np.random.Generator(np.random.PCG64(42))
b = np.empty((10000, 2))
for i in range(10000):
    b[i] = a[rng.integers(0, n, size=n)].mean(axis=0) * 100
print(a.mean(axis=0) * 100)
print(np.quantile(b, [.025, .975], axis=0, method='linear'))
```

## 写作边界

- 本次为两项预先指定比较的未校正边际区间，不提供多重比较整体错误率保证；仅覆盖这个模型、题单及已记录生成结果，不含跨随机生成、跨模型或跨数据集变异。
- 题级区间没有保留共享图像组件相关性，不能取代既有`quality_closure_20261021/source_cluster_ci.csv`的564组件聚类及多重比较校正区间；两种口径分开命名、分开引用。所有点估计只是该固定运行的读数。
- P1为cosine、P2为utility；P3为dev选定策略，在本模型恰为utility，**不是random**；random分数来自逐题评分。P4为事后Oracle，不能作为可部署收益。本比较不混入官方共享检索S1及其命中数；后补utility打分与策略生成属不同批次。
- 只用归档原文比较：Utility-MRAG已归档零样本与utility条件，缺同池cosine/random的成对数值，不能写“复现原论文排序”。文献核验等级与协议差异沿用DATA_AUDIT，不新增外部查证。

完成本结果后才写独立 [R3小节草稿](draft/R3_strategy_tradeoffs_EN.md)；完整初稿与冻结表保持原状。
