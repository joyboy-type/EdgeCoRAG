# 文献与复现状态

本表区分论文作者报告、A侧技术探针、B侧本轮实跑。没有把安装命令、接口通过或论文数字当作本项目性能复现。来源与已有PDF哈希见 [source_manifest.csv](../source_manifest.csv)。

| 来源 | 方法与数据 | 代码与实际可用部分 | 本项目状态与差异 | 原始指标数值与许可缺口 |
| --- | --- | --- | --- | --- |
| MRAG-Bench ICLR2025 | 1353视觉中心MCQ，直接回答、检索与GT证据 | mragbench/MRAG-Bench eval/score.py；接口4项差异已有审计 | 五模型在项目top3/actual-GT协议完成；主解析器strict_choice_v1，不是官方宽松抽取 | Table3所选基线／GT数值与5.82／33.16pp已核对，见本批原表证据；未复现作者增益。dataset卡CC-BY-4.0，图像与代码许可分别核对 |
| MMDocRAG NeurIPS2025 D&B | 文档问答，任务书称4055专家QA；第二验证集 | MMDocRAG/MMDocRAG仓库存在，具体schema、依赖、评分尚待试验 | 未运行，不能称已完成外部验证 | 原文4055、dev2055/eval2000和Table3/7所选数值已核对为作者声明；未逐题计数，HF与README许可冲突未解 |
| VisDoM NAACL2025 | 多文档视觉QA，含图表表格幻灯片 | MananSuri27/VisDoM；任务书列visdomrag.py/eval.py，当前可运行性未在B环境测试 | 跨域外测备选，未运行 | 已摘录Table3三模型四条件Average F1，摘要12–20%无统一分母解释；上游多数据许可仍待核验，仓库API license=null |
| Utility MRAG ACL2026 | 用视觉证据效用选择辅助多模态RAG | Hcnaeg/utility-mrag；A历史作者测试23/23、True/False探针 | 完整选择器及生成质量未复现；Gemma4/EmbeddingGemma2替换不能直接搬用论文提升 | Table1所选Top3数值与GT混入候选池设置已核对；全部表格／完整方法未复现；继承审计代码MIT，数据权利另审 |
| Fix Before Search VQQP ICML2026 | 视觉查询预处理与鲁棒性 | phycholosogy/VQQP_Bench；来源commit/PDF哈希有继承记录 | 可选机制扩展，未运行 | 没有新鲁棒性结果，原始数值与数据许可尚未补齐 |
| RAGRouter NeurIPS2025 | 文本多RAG路由 | OwwO99/RAGRouter；A侧参考文献 | 非原生视觉基线，未做视觉方法复现 | 不与本轮视觉主排行榜混排；原始数值与适配许可待补 |

任务书要求的“每篇原始数值/指标、成功复现与许可”仍是部分完成：已有定位、部分来源哈希和状态，四篇选定主表已补，仍缺其他所需表格、未运行方法的实测验证及未明许可。没有用空白或作者结果冒充完成项。A侧历史4060 8GB的4bit探针与本次4090统一BF16是不同硬件/精度条件，不能汇成同一性能表。

2026年10月17日本批继续核验了官方摘要、项目页、仓库README／元数据和少量评分源码，新增[文献证据表](next_stage_20261017/B_paper_evidence.csv)与[逐来源记录](next_stage_20261017/B_public_source_checks.json)。MMDocRAG的4055 QA现已在官方项目／摘要中核对为发布者声明，仍未本地逐行计数；HF卡片声明Apache-2.0，而仓库README另标数据CC-BY-NC、仅研究使用，冲突未解决。API license=null不能概括为README没有任何说明。其评分代码还有judge文件必需、README参数差异和等长校验缺口，详见[第二数据集可行性](next_stage_20261017/B_external_dataset_feasibility.md)。这些核验不等于外部评测或原论文全部表格复现，旧来源表的历史核验范围保留。

本批进一步核对四篇全文的选定主表，新增[36行作者数值证据](next_stage_20261017/B_paper_table_evidence.csv)、[解释与边界](next_stage_20261017/B_paper_table_audit.md)和[全文来源哈希](next_stage_20261017/B_primary_paper_checks.json)。MMDocRAG主表是gold-inclusive固定池；Utility主候选池也混入GT；VisDoM是word-overlap F1，不能把摘要泛化成统一准确率增益。评分合同另记录MMDocRAG论文／源码总体F1聚合差异。以上是文献审阅，不是本项目新增实验成绩。
