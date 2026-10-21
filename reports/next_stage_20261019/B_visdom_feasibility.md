# VisDoM 可行性
复验：`$PY analysis/next_stage_20261019/b_offline_protocols.py --verify`

本批只读固定revision README（5023字节）与仓库元数据，返回200；同revision requirements.txt返回404。逐来源URL、UTC时间和sha见B_visdom_source_checks.json，未下载数据/模型。README可访问不等于代码环境可复现。

README声明2271 queries/1277 docs，未本地计数。API license=null，不能推定使用或再分发许可；五个上游数据集需分别核权。依赖涉及PyTorch、PDF/OCR工具、向量库、视觉/文本检索器和可选API客户端，未锁定环境、未执行。多文档自由问答与word-overlap F1不等同MRAG单图ABCD严格准确率；必须另冻输入、来源分组、生成预算和评分协议。

GPU量级不可识别：未核验页数、未选后端、无上下文长度与吞吐，不能编造小时范围。只给页编码+查询检索+生成的公式，实际预算待独立协议、许可与授权。未开展复现；保持R06相关状态，不将可行性当第二数据集新结果。
