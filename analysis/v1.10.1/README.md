# 本地统计复算

所有入口只做离线读取和统计，不下载、不推理、不连接服务器。`reproduce_public.py`仅用公开JSONL即可检查全部主键、严格抽取、计分、质量分母、跨模型配对差距、转移与质量成本表。

在仓库根目录，用已有Python运行：

```bash
python -B analysis/v1.10.1/reproduce_public.py --output-dir /path/to/new-empty-output
# 已有matplotlib时追加 --figures；只复算CSV无需第三方依赖
```

保有完整已验证本地archive者，可复核原始代码/矩阵/输入哈希并重算76份评分、所有批准的同模型区间、SQL与原图：

```bash
python -B analysis/v1.10.1/analyze_results.py --backup-root /path/to/verified/edgecorag-v1101-backup --output-dir /path/to/new-empty-output
```

依赖版本见requirements.txt。新输出必须在备份外且为空，原始备份不改。SQL文件用于该步骤生成的analysis.sqlite；数据库不重复上传。`results_analysis.template.ipynb`是清空输出的可运行模板，在环境中设置`EDGECORAG_BACKUP_ROOT`后执行；原来已执行且无错误的本地笔记本保存在原分析包，本模板不冒称已执行。

统计扩展是结果后的描述性分析，不改原计划/生成参数。跨模型比较显式按同条件、同split、同qid与版本配对，不绕过原analyze_batch.py的同模型安全限制。场景分层题级bootstrap2000次seed42，无来源聚类、多重校正、预注册等价或非劣效界值。

## 已保存结果诊断

只使用公开压缩输出与输入上下文，复算八种互斥正确性模式、GT哈希分组贡献、格式状态贡献和严格错误类别，并从逐题事实表进行六组SQL对账：

```bash
python -B analysis/v1.10.1/diagnose_saved_runs.py --output-dir /path/to/new-empty-output
```

该入口只需Python标准库及仓库原解析器。范围是internal_holdout与frozen_test的S0/S1/S2，共17745条回答；5915个问题×模型配对单元不是5915个独立问题。S3、开发、smoke、性能与warmup均不混入。原始严格分数不变，格式失败全部计错。

[diagnostic_record_analysis.ipynb](diagnostic_record_analysis.ipynb)是本轮已执行笔记本（8个代码单元，无错误）；重执行另需pandas、nbformat、nbclient及Jupyter kernel。HTML和CSV见[诊断目录](../../reports/v1.10.1/diagnostics/)。`build_diagnostic_report.py`生成canonical artifact；HTML由Data Analytics插件portable packager生成，不含联网依赖。报告数据与结构验证通过；浏览器图表、来源弹窗和交互核验未完成，详见目录内`report_packaging_receipt.json`。

新增`selected_cases.csv`按固定SHA规则事后选择20例，区别于此前`failure_examples.csv`的首qid实例。它们均未看图、未审定机制，不是代表性抽样。新增暴露记录见`posthoc_exposure.json`；本诊断未新增推理、置信区间或显著性结论。
