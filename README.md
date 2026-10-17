# EdgeCoRAG

研究小型多模态模型在共享视觉证据下的能力边界，以及质量、生成时延和显存的关系。

截至2026年10月17日，runtime-v1.10.1批准的161任务、21927次问答已全部完成并本地备份核验。五模型技术通过，132次正常格式失败全部计错。任务书整体仍有第二数据集、完整检索成本、机制审定及来源聚类统计等缺口，不能由技术通过宣称论文结论成立。

完整成果位于[交付分支](https://github.com/joyboy-type/EdgeCoRAG/tree/results/runtime-v1.10.1-delivery)，由[草稿PR #2](https://github.com/joyboy-type/EdgeCoRAG/pull/2)集中审阅。默认`main`首页同步当前导航；下列成果链接指向交付分支，尚未将整份PR合并为`main`的源码。

## 当前进度与下一项工作

| 范围 | 已核对的状态 | 接下来做什么 |
| --- | --- | --- |
| 第一轮模型实验 | 161任务、21927次运行完成并备份 | 保留固定分母与全部失败记录 |
| B-01阶段论文 | 初稿已交付 | 审阅、修订方法和结论表达 |
| B-02记录诊断 | 37条论断证据、20条案例状态已交付 | 图像可获得性待A-01；视觉机制未审定 |
| B-03第二数据集 | 官方来源与评分代码已静态核验 | 解决MMDocRAG许可冲突、schema与评分适配缺口 |
| B-04/B-05统计与新协议 | 方法边界与预案已交付 | 等可信来源分组、正式矩阵和资源预算 |
| A本批任务 | [独立任务 #3](https://github.com/joyboy-type/EdgeCoRAG/issues/3)已发布，本仓库尚无本批交付回执 | 先回传现有图片可获得性、独立语料访问与许可 |

B侧进度集中在[任务 #4](https://github.com/joyboy-type/EdgeCoRAG/issues/4)与[B交付回执](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_return.md)。没有回传的A侧工作不推断为已完成或未开展。本批未新增推理、judge调用、图库下载或租卡。

## 当前交付入口

- 下一阶段分别执行：[A：语料、检索与证据交接任务](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/A_TASKS.md)／[你与B：阶段论文、诊断与补充协议任务](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_TASKS.md)
- B侧本批交付：[阶段论文初稿](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_phase_report.md)／[离线报告（下载后打开）](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_phase_report.html)／[论断证据表](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_claim_evidence.csv)／[任务进度与仍缺的证据](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_return.md)
- [第二数据集可行性](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_external_dataset_feasibility.md)／[统计补强决策](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/B_statistics_decision.md)／[下一轮实验预案](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/next_stage_20261017/next_experiment_decision.md)
- [整合说明 Word 文档（首次交付快照）](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/EdgeCoRAG阶段成果与任务要求整合.docx)
- [下一步应该做什么](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/Next_steps.md)
- [任务书与全部现有文档要求整合](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/Requirements.md)
- [五模型比较报告](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/B_comparison.md)
- [已保存结果诊断报告（离线 HTML）](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/v1.10.1/diagnostics/report.html)：GT 哈希分组、格式影响分解与 20 个待审案例
- [文献与复现状态](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/B_papers.md)
- [交付包与清理说明](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/Delivery.md)
- [逐题结果与输入上下文](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/logs/README.md)
- [离线复算方法](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/analysis/v1.10.1/README.md)
- [原始绑定与补丁运行的两阶段重建](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/reports/Reconstruction.md)

## 主结果

冻结集每条件1033题、严格评分；S0仅查询图，S1为发布的官方检索候选top3，S2为actual GT oracle。

| 模型 | S0 | S1 | S2 |
| --- | --- | --- | --- |
| Qwen3-VL 4B | 60.12% | 57.60% | 69.41% |
| Qwen3-VL 8B | 56.44% | 56.15% | 66.80% |
| Gemma 4 E2B | 36.30% | 35.43% | 42.69% |
| Gemma 4 E4B | 38.43% | 41.34% | 47.73% |
| Qwen3.5 4B | 53.53% | 54.50% | 58.18% |

Gemma在同S1下仍低于Qwen，不能写为普遍替代。S2只用于oracle诊断。结果来自同一RTX4090，性能为预处理与生成，不是端到端检索或真实边缘设备评测。

## 目录

`b-side/` 保留准确的已执行v1.10.1代码、冻结配置和接收审计；`a-side/`及`handover/`保留A侧来源、契约、历史探针与可复现样例；`reports/`为当前报告和表格；`figures/v1.10.1/`为PNG/SVG/PDF科研图；`logs/`为压缩逐题记录和结构化输入；`provenance/v1.10.1/`为代码身份、矩阵、25份阶段回执与交付哈希；`configs/model_registry.yaml`为原JSON注册表的兼容镜像。

## 版本与历史文档

原始批准源提交为`6c529479b94362c19094088524f8702ca2a9a0de`，实际执行为该源码加用户批准的v1.10.1补丁，由`b-side/package_hashes.json`锁定。补丁只把正常格式失败与技术失败的阶段门禁分开，并补足Qwen依赖；提示词、严格解析、64token、BF16及科学参数未变。

旧A侧状态文档、冻结注册表和前租用回执描述当时状态，保留其原始内容以便追溯；当前完成状态以[执行回执](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/provenance/v1.10.1/execution_receipt.json)为准。历史“尚未GPU验证”字段没有被悄悄改写。完整原始attempts、旧失败记录、备份archive在本地保留。

本轮新增材料不含模型权重、数据集原始图片、环境、缓存、认证信息或服务器运维工具。仓库已有的6题接口图片是可复现实例，继续保留；不能因为文件较大就删掉仍被验证器引用的有效样例。数据与许可见[source_manifest.csv](https://github.com/joyboy-type/EdgeCoRAG/blob/results/runtime-v1.10.1-delivery/source_manifest.csv)。
