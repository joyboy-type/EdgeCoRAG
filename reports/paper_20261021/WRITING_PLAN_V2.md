# 论文写作方案 v2（合并版）

合并两份材料：
- Codex《论文写作总纲与证据图表整合模板》（2026-10-18，含 23 篇文献矩阵、九图候选、章节填空模板、主张检查清单）
- 本仓库《写作风格参考》（2026-10-21，含六篇目标论文的共同结构、ACL 格式约束、审计类论文的修辞边界）

v2 相对旧模板的**唯一实质改变**：把论文定位从"方法/系统论文（含边缘部署与节能）"收敛为**审计/边界论文**。理由是结果已经关闭了方法分支（见 §一）。

---

## 一、定位（已由数据决定，不再二选一）

旧模板保留了"若完成后续方法与系统实验，再围绕已验证的核心机制组织方法论文"的分支。该分支已不可能：

| 方法/系统论文所需 | 现状 |
|---|---|
| 可部署路由策略 | 未训练、未评估；Gate A1 判 `insufficient_evidence` |
| 完整同机成本 / 边缘设备 | 仅三模型、20 题、2 token 的 GPU pilot；无边缘设备、无能耗整机 |
| 效果优于基线的方法 | 无；共享检索在五个模型上四条区间跨零 |

**结论**：定位为审计论文。一句话主张：

> 在冻结协议下，多模态 RAG 的收益边界由**检索命中率**与**模型利用率**决定，而不是由"是否接检索器"决定。

## 二、章节—证据—图表对应（8 页正文）

| 章节 | 页 | 写什么 | 数字入口 | 图表 |
|---|---|---|---|---|
| Abstract | 0.3 | 五句，含一个反直觉数字 | `retrieval.top3_miss`、`T2.*.S1_minus_S0_pp` | — |
| 1 Introduction | 1.2 | 四层结构（检索无效→证据有效→天花板→利用率） | 同上 + `gate.qwen3vl_4b.delta_pp` | — |
| 2 Related Work | 0.75 | 四组，每组末句点差异 | — | — |
| 3 Method | 1.75 | 条件定义、检索接口、**2×2 定义**、统计、成本仪表 | `a18.*`、`index.*` | — |
| 4 Results | 2.5 | 主表 + 逐条解读 + 利用率 + 伤害 + oracle + 成本 + judge + S3 | `T1.*` / `T3.*` / `harm.*` / `cost.*` | **T1、T3、F1、F4** |
| 5 Discussion | 0.75 | 支持什么 / 不支持什么 | — | — |
| 6 Ethics | 0.5 | 只讲"负结果被过度解读"一个风险 | — | — |
| 7 Limitations | 1 | 八条（不计页） | — | — |
| 8 Conclusion | 0.25 | 收束 | — | — |
| Appendix | — | 协议细节、T2/T4/T5、prompt 原文、复现命令 | 全部冻结 id | 附录图 |

## 三、参考文献：分三级使用（旧模板 L01–L23 的正确用法）

旧模板的 23 篇矩阵是资产，但**只有 6 篇完成过会议版核验**。分级：

| 级别 | 文献 | 用法 |
|---|---|---|
| **A. 已核（可直接引）** | MRAG-Bench (ICLR'25)、MMDocRAG (NeurIPS'25 D&B)、VisDoM (NAACL'25)、Utility-MRAG (ACL'26)、VQQP (ICML'26)、RAGRouter (NeurIPS'25) | 相关工作主体；数字与结论引用 |
| **B. 方法背景（需核页码）** | CLIP、MRL、Lost in the Middle、RouteLLM、FrugalGPT、Adaptive-RAG | 只在"背景方法"处一句带过，投稿前逐条核 |
| **C. 仅提及（不引数字）** | AWQ、PowerInfer-2、RAGAS、ARES、VisRAG、ColPali 等 | 只在"未来工作/相关方向"提及 |

**硬规则**：C 级不得用来支撑任何比较；B 级不引具体数值；A 级数字必须能被页面核到。

## 四、图表最终清单（旧模板九图 → 四图 + 附录）

| 我们的编号 | 内容 | 来源 | 位置 |
|---|---|---|---|
| **F1** 质量—成本 | P95 时延 vs 准确率，三点（三模型） | `pareto_quality_cost.svg` | 正文，带"非已验证 Pareto"标注 |
| **F2** S1 增益 | 五模型 Δ 与区间，跨零点标出 | T2 表数据 | 正文（小图） |
| **F3** 2×2 分格 | 五模型四格堆叠 | T3 数据 | 正文 |
| **F4** 排序一致性 | 五题重合数与换位对 + bf16-cast 零翻转 | `bf16_cast_ablation.json` | 正文 |
| 附录图 | 索引对账（4,282/430/15）、维度消融、judge 五维雷达 | 各自回执 | 附录 |

旧模板的九图候选里，**图7（预算路由）、图8（真实系统）、图9（语义分面）全部删除**——对应能力不存在，画了就是暗示未做的事。

## 五、可复用的句子模板（改造为审计版）

旧模板的填空句式很好，但主语需要从"我们提出"改成"我们测量"：

**摘要五句**

1. Multimodal RAG is often justified by the claim that external visual evidence compensates for limited visual knowledge.
2. That claim rests on two premises — that retrieval surfaces the right evidence, and that the model can use it — which are rarely tested separately.
3. We freeze five vision-language models, four evidence conditions, one retrieval interface and one benchmark split, and measure each premise separately on 1,033 questions.
4. Shared retrieval is indistinguishable from no retrieval for four of five models (S1−S0 from −2.52 to +2.90 pp), while gold evidence improves accuracy by +6.39 to +10.36 pp.
5. The gap is explained by a 50% retrieval ceiling and utilisation ranging from 42% to 66% on hit questions; we release the protocol, the 2×2 decomposition and the instrumented cost pilot.

**结果段**

> Under a fixed question set, candidate pool and budget, **[model/strategy]** reaches **[metric = value]**, differing from **[explicit baseline]** by **[absolute delta and available interval]**. This supports **[bounded claim]**. Because of **[denominator / exposure / evidence count / cost boundary]**, the stronger claim **[X]** would require **[evidence]**.

**贡献三条（每条带交付物）**

1. We release a frozen, failure-retaining protocol for multimodal RAG on vision-centric QA, with all selection confined to a development split.
2. We introduce a 2×2 hit-by-correctness decomposition that separates retrieval quality from utilisation, with harm reported as an independent overlay.
3. We publish an identity reconciliation and an instrumented cost pilot, each with its own measurement limits stated.

## 六、主张检查清单（合并两版，共 12 条）

来自旧模板的 7 条（原样保留，它们是这份文档最有价值的部分）：

1. 官方候选 ≠ 自主检索；检索独立 ≠ 未暴露验证
2. 身份命中 ≠ 语义支持 ≠ 答案正确
3. GT 证据参照 ≠ 事后路径 Oracle ≠ 预算 Oracle ≠ 可部署策略
4. 引用 F1 ≠ 词面相似 ≠ 事实性 ≠ 图文一致
5. 模型/生成边界成本 ≠ 完整 RAG 系统成本
6. 作者报告 ≠ 项目实测 ≠ 本次推导 ≠ 未来提案
7. 线索未核 ≠ 已核；访问缺口必须保留

我们新增 5 条：

8. 跨零区间只写"cannot exclude no difference"，不写"equivalent"
9. 采样到的功率峰值 ≠ 连续峰值；GPU 功耗 ≠ 整机能耗
10. 三模型 pilot ≠ 五模型成本曲线；2 token ≠ 完整回答成本
11. 18,955 是发布索引行数，不是实例数；4,712 才是唯一内容数（4,282 为交集）
12. judge 与被评模型重叠时，排名不是独立证据

## 七、写作顺序（结合两版）

旧模板建议"先写设置与结果、后写方法与引言、最后摘要"；我们的初稿已全节存在，所以顺序改为**校验优先**：

```
1. 表格实体化（脚本从 frozen 生成 LaTeX，杜绝手抄）
2. 图转 PDF（F1–F4）
3. references.md → .bib（A 级 6 条，B 级逐条核）
4. Markdown → main.tex（ACL 模板，8 页）
5. Reproducibility Checklist
6. 数字终检（正文每个 id ↔ frozen_numbers）
7. 全文主张过一遍 §六 的 12 条
```

## 八、仍需补齐的三项

| 项 | 状态 | 影响 |
|---|---|---|
| B 级文献页码 | 未核 | 相关工作引用 |
| F1/F4 的 PDF 矢量版 | 只有 SVG/PNG | 排版 |
| ACL Reproducibility Checklist | 未做 | 投稿必需 |
