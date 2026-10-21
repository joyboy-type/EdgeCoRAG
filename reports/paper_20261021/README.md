# 论文材料索引

供审核与写作使用。按用途排序：

| 文件 | 用途 | 状态 |
|---|---|---|
| `PAPER_EVIDENCE_REVIEW.md` | **审核入口**：创新点筛选、已否证想法、既有工作、给 Codex 的 8 个问题 | 待审 |
| `WRITING_PLAN_V2.md` | 定位、章节页数、图表清单、文献三级、12 条主张检查 | 定稿 |
| `WRITING_STYLE.md` | 六篇目标论文的结构与修辞特征 | 定稿 |
| `DECOMPOSITION.md` | 两项分解、场景分层、维度与天花板的数字与边界 | 定稿 |
| `T2_paired_intervals.md` | 15 行配对区间与四条读法 | 定稿 |
| `references.md` | 六篇已核文献（标题/作者/会议/页码/DOI） | 6 篇已核 |
| `paper_outline.md` | 章节骨架（Codex 生成，早于最新结果） | 部分过时 |
| `figures/plot_F4.py` + `F4_order_consistency.*` | 排序一致性图与其生成脚本 | 定稿 |
| `DATA_INVENTORY.md` | 什么在仓库、什么不在、如何重建 | 定稿 |
| `draft/paper_EN_v0.md` | 英文初稿（4,268 词，八节） | 待按最新结论改写 |
| `draft/paper_zh_v1.md` | 中文底稿（前三章） | 参考 |

## 数字从哪来

一切定量陈述只引用 `reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`
的 `numbers[].id`；分解与场景分析的原始估计见本目录的 `*.json`。

## 已知不一致（待改稿时处理）

- `paper_outline.md` 写在 judge/S3/分解之前，其表图清单已由 `WRITING_PLAN_V2.md` 取代；
- 英文初稿的贡献条目仍写"2×2 分解"，应按 `PAPER_EVIDENCE_REVIEW.md` §四 改为三条；
- 初稿尚未包含 C2（场景分层）与 C3（维度不动天花板）。
