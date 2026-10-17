# A 侧本批回执（A_return.md）

日期：2026-10-17。分支见末尾提交号。逐项说明完成/部分完成/阻塞、文件路径、核验范围、未做的事、给 B 的依赖。

## 逐项状态

| 任务 | 状态 | 交付 | 说明 |
|---|---|---|---|
| A-01 案例图片可获得性 | ✅ 完成 | `case_image_availability.csv` | 20 去重 qid × (查询图 + S1×3 + S2×n) = 172 条，全部 `available` |
| A-02 语料访问与许可 | ✅ 完成（结论为「仍受阻」） | `corpus_access_and_license.csv` + `corpus_readiness.md` | 网络不可达 + 许可未声明 |
| A-03 检索/效用选择方案 | ✅ 完成（设计稿） | `retrieval_selection_protocol.md` + `routing_and_cost_protocol.md` | 只设计，不跑前向 |
| A-04 来源分组可行性 | ✅ 完成（结论为「不可得」） | `source_group_feasibility.md` | 无可靠分组键，不交编造 CSV |

## 各任务核验范围

### A-01

- 输入：`reports/v1.10.1/diagnostics/selected_cases.csv`（20 条，去重后 20 qid，均在 frozen_test）。
- 方法：读取本地固定证据包 `frozen_test_s1`（查询图 + S1 已发布候选 top-3）与
  `frozen_test_s2`（S2 真实 GT），按 `evidence_list.jsonl` 的 `path`/`sha256`/`w`/`h`
  逐图核验：文件存在、字节 sha256 一致、PIL 可解码、尺寸匹配。
- 结果：172/172 全部 `available`；无缺失、无哈希不符、无解码失败。
- **边界**：这只是「图片可获得性」核验，**不是**视觉机制审定；`visual_review_completed`
  与 `mechanism_adjudicated` 仍为 False，未在看图前填「语义已确认」，也未把哈希未命中写成检索失败。
- **最小交接**：20 qid 的查询图+S1+S2 图片可单独打包（约 20×(1+3+~4.6)≈172 张，约 45 MiB），
  后续若 B 需要按 qid 取回可据此安排；本批不传输。

### A-02

- 只读核验：MRAG-Bench README（GitHub）、HF 数据集卡、GitHub 仓库 license 字段、历史语料探测记录。
- 关键结论：数据集本体 CC-BY-4.0（可研究使用）；**独立语料包（Google Drive zip）许可未声明、本机网络不可达**；
  评测代码仓库 `license=null`；上游图片（Imagenet 等）与官方候选检索器未核验/未说明。
- 未下载语料、未下载图片包，未把「未核实规模」写成实测。

### A-03

- 纯设计：官方候选与自主重检索分 pool/分表；EmbeddingGemma 2 768 主 + 128/256/512 对照 + 截断归一化；
  R@1/R@5/MRR 与「精确哈希命中 vs 语义支持」区分；cosine/utility/random 三策略与种子；
  四路径 + Oracle 路由矩阵（仅上界）+ 成本分列（索引/在线/切换）+ 跨硬件不可相加。
- 未跑任何模型前向或检索；未知成本标「未测」。

### A-04

- 逐一评估 `scenario`/`aspect`/`image_type`/`source`/图片字段，均非可靠来源/文档/实体键。
- 复用「1338/1353 题精确图像连通大组」结论，不把连通组当作文档来源。
- 结论：**不交付 source_group_candidates.csv**（无可靠键，不编组）。

## 未做的事（明确）

- 未下载独立语料、未下载模型、未启动生成或嵌入推理、未连接旧服务器、未重试旧任务。
- 未改 prompt、解析器、64token、评分、BF16、切分、证据顺序、原始结果。
- 未做真实检索指标（R@k/MRR）、未做效用模型前向、未做四路径运行、未做来源聚类统计。
- 未把 A-01 的可获得性写成视觉机制审定，未把 A-02 的「未声明许可」写成「已授权」。

## 给 B 的依赖

- **B-02**：可用 `case_image_availability.csv` 判断「保留或解除看图依赖」；A 侧图片可获得（172/172），
  但看图前的语义/机制审定仍待。
- **B-05**：独立检索路线**暂不能进入下一轮**（语料网络不可达 + 许可未声明），见 `corpus_readiness.md`；
  若需推进，先解除语料阻塞。
- **B-04**：来源聚类不可靠（无分组键），统计仍按官方 9 场景分层，不声称来源独立性。

## 提交与文件

- 本批新增材料均在 `a-side/reports/next_stage_20261017/`：
  `case_image_availability.csv`、`corpus_access_and_license.csv`、`corpus_readiness.md`、
  `retrieval_selection_protocol.md`、`routing_and_cost_protocol.md`、`source_group_feasibility.md`、`A_return.md`。
- 复现脚本：`a-side/scripts/a01_case_image_availability.py`（A-01）。
- 提交号与分支见回复正文。
