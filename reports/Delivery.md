# EdgeCoRAG 阶段成果交付说明

本次交付整合用户提供的任务书与仓库25份Markdown文档，共37项要求。已完成实验的范围为MRAG-Bench五模型冻结协议；未达成项列在Requirements，不以文件存在代替科学完成。当前研究结论是能力边界与负结果，尚无普遍替代、外部验证或端到端边缘部署结论。

## 文件对应

| 任务书交付项 | 本次位置 | 状态 |
| --- | --- | --- |
| B_papers.md | reports/B_papers.md | 来源与复现状态已整合；原论文逐表指标及未明许可列缺口 |
| B_comparison.md | reports/B_comparison.md 与 reports/v1.10.1/ | 质量表、配对区间、同证据模型差距、转移与实例 |
| B_predictions.jsonl | logs/B_predictions.jsonl.gz | 全21927条；按logs/README解压即得到JSONL，压缩减少重复上传 |
| model_registry.yaml | configs/model_registry.yaml | 原始JSON是合法YAML子集，按字节镜像；运行仍读取b-side原JSON |
| figures/ | figures/v1.10.1/ | 质量、同模型差值、时延、对转错、质量P95和显存图，共6组 |
| source_manifest.csv | 仓库根目录source_manifest.csv | 含已核验和未独立核验字段，未明许可透明保留 |
| 需求核对与下一步 | reports/Requirements.md 与 Next_steps.md | 37项逐项状态、证据与限制 |
| 科学与代码溯源 | provenance/v1.10.1/ 与 b-side/package_hashes.json | 精确执行代码、绑定矩阵、阶段回执、交付文件SHA |

## 清理范围

本轮从已核验备份选择有用交付物，省去环境、缓存、SSH/监控/终端脚本、连接配置、数据库、重复解压JSONL、旧发布ZIP和临时报告构建物。首页旧进度被当前入口替代；原始备份和旧失败attempts未删除。保留A侧审计、哈希、冻结依据及接口样例，它们有复现与证明用途。没有重写历史，也没有删除远端实验资产。

逐题记录gzip约2.6MiB，不以丢失失败行压缩。输入上下文单独去重。原始结果archive SHA256为`98bf99c45ecdd1a44029747885e9c3e49f860b95ae95079ea0c5c123b33ffc85`，2118文件逐一校验，本地完整保存。本轮新增结果不包含完整数据集图像或模型权重；仓库已有6题接口图片继续保留。需要重推理时复用已有固定缓存/Release及官方revision，不能把轻量结果包当完整离线模型镜像。

## 验证与发表边界

公开JSONL重新严格解析、核对21927唯一键、161任务和132格式错误，并重算34个quality组合及跨模型配对、转移与性能表。完整备份复核另重算76份非performance评分和原始哈希。最终具体检查结果见provenance下publication_checks.json；提交前检查只覆盖所列范围，不代表整课题研究目标已完成。

所有科研图都以真实计量边界命名。质量成本图使用不同固定工作负载，前沿是描述性的；S3小型AI辅助审阅子集不能外推。源依赖、审计暴露与无多重校正等限制已随报告交付。未自动启动任何后续实验或服务器操作。

从头重建依照[Reconstruction.md](Reconstruction.md)分两阶段：先用父版本建立绑定，再用精确v1.10.1补丁运行。补丁目录直接跑旧closeout会因原依赖pin拒绝；父版本九项离线检查与v1.10.1五项格式回归检查通过，不等于重部署图像全链路已验证。

## 记录诊断补充

新增[已保存结果诊断](v1.10.1/diagnostics/report.html)、逐题配对台账、20个事后选例、六组SQL及8单元已执行笔记本。诊断只读公开结果，未新增推理或修改科学参数；R21仍有看图语义与机制审定缺口。数据复算与HTML结构核验通过，浏览器图表和交互自动核验未完成。具体范围见`v1.10.1/diagnostics/delivery_validation.json`。

桌面原始完整交付ZIP与8页Word保留原版；新增诊断以补充ZIP单独交付。补充包基于原交付提交`49031cf65538521f76fc9c275c7fdd3be6923c77`，覆盖包内同路径文件后得到本轮更新；它不单独包含原始压缩逐题日志、模型或数据集图像。更新后的完整仓库由`provenance/v1.10.1/delivery_manifest.json`逐文件锁定，旧版manifest仍可从Git历史取得。
