# B-03原论文表格与口径核验补充

日期：2026-10-17。核验了四篇官方全文中的**选定主表行和相关设置**，形成[36行数值证据](B_paper_table_evidence.csv)、[来源哈希与核验范围](B_primary_paper_checks.json)。作者成绩均标为`author_report_only_not_reproduced`；没有下载外部QA、图库、模型或作者逐题预测，没有启动推理。论文全文仅保存在本地核验缓存，不打包上传仓库。

## 1 已核实的数字与含义

| 论文与位置 | 作者报告值 | 需要保留的解释 |
| --- | --- | --- |
| MRAG-Bench Table3 | GPT-4o无RAG68.68%、检索68.96%、GT74.50%；人类38.47%／61.38%／71.63% | GT增益分别5.82与33.16**个百分点**，由表格两格相减得到；虽caption使用relative一词，不是相对提高5.82%／33.16%。top5、Incomplete1，与本项目top3和严格解析条件不同 |
| Utility Table1，PDF第6页／印刷35096 | Qwen3-VL8B在MRAG的zero-shot59.35到Qwen3-VL2B surrogate Top3的67.55；Visual-RAG对应52.41到63.77 | MRAG为exact-match，Visual为Qwen3-8B judge的表内0～100尺度，不可都叫准确率；主表候选池混入标注GT，非纯自主检索部署 |
| Utility Table1 | Visual-RAG Ovis2.5-9B zero-shot52.67，Qwen3-VL2B surrogate Top3为63.24 | 这是作者模型／候选池／judge配置；不能迁移为本项目Gemma4+EmbeddingGemma2已经实现的提升 |
| MMDocRAG Table3／7 | GPT-4.1固定20quote池OverallF1=70.2、五维judge均分4.14；真实BGE原query为54.4／3.53，BGE clauses57.5／3.71，multiple clauses59.9／3.79 | 70.2来自包含gold的固定候选集，在Table7列为perfect；0～100引用F1与0～5judge分数分开，均非选择题准确率 |
| VisDoM Table3，PDF第7页／印刷6094 | GPT-4o Long32.78、Text37.33、Visual49.02、VisDoMRAG50.01；Gemini32.81／35.31／39.80／44.03；Qwen2-VL12.09／31.65／39.06／39.94 | 指标为作者显示的五子集Average word-overlap F1（PaperTab修改版）；检索视觉ColQwen2 k5、文本BGE1.5 k7。不能把摘要12～20%写成所有模型／全部基线的统一增益 |

VisDoM的GPT-4o示例按显示值相减：VisDoMRAG相对Text为+12.68个F1分、相对Visual为+0.99、相对Long为+17.23。它们是**绝对分差**，不替作者摘要补造唯一分母。主表本身也不支持“每个模型在每个子集均提高”的强表述；例如Qwen2-VL的SciGraphQA为28.13→27.98。此处只修正引用口径，不反推论文新结论。

## 2 版本与数据规模仍分清声明／本地核验

MRAG论文声明1353题；MMDocRAG全文2.2声明4055题、dev2055／eval2000、222文档，15quote为5图10文、20quote为8图12文；VisDoM Table2声明2271queries／1277docs。以上核对的是作者原文，尚未对外部数据逐条计数或核验来源隔离。

Utility的主表包含GT证据；附录D.1另描述retrieval-only等压力条件，本批没有审阅或复现所有附录实验，不能把某个压力条件套在主表成绩上。

## 3 MMDocRAG评分发现与下一步

[评分合同草案](B_mmdocrag_scoring_contract.md)与[10项静态发现](B_mmdocrag_static_audit.json)补齐了字段、固定qid分母、引用解析、空响应、token与judge完整性要求，以及15个将来适配器验收规格。**这些规格没有执行，适配器没有实现。**

新增重要差异：论文写“文本／图片F1平均”，源码Overall却是逐题引用并集F1宏平均；Table3图片80.7与文本52.0的平均66.35也不等于70.2。后续应分名保留口径并验证，不能自行修正作者结果。源码还存在短文件zip截断、token元数据缺失除零／缩分母、judge题单未对齐和import时NLTK下载等边界，原入口并非已证明的离线无judge路径。

本批完成所选主表与接口合同准备；B-03仍是部分完成。许可冲突、真实数据schema、依赖／评分适配可运行性未解决，无第二数据集实测。R05保持部分完成、R06待补。下一步可先在本地实现并验证无judge纯指标适配器（只用虚构输入），取得A的来源键与依赖材料后，再冻结第二数据集的小规模协议和预算。
