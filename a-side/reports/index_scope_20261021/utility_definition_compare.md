# utility 定义差异对照（一页）

**本文 utility**：`ℓ("True")` —— 对候选图 + 题面打分时，输出词表里 token `"True"` 的**原始 logit**；按该值降序取前 3。不做 softmax、不做归一化。

**作者（utility-mrag, ACL 2026）**：使用其自有 surrogate 模型，`score_key: true_logit`；其 `p_true` 定义为在 `[True, False]` 两 token 上的 softmax，即 **σ(true − false)**；另报告 `p_vocab`（全词表 softmax），对 `true − log Z` 单调。

## 1. 三者是三种不同排序

| 口径 | 排序由什么决定 | 对"True/False 同升降"是否敏感 |
|---|---|---|
| `ℓ("True")`（**本文**） | `true` 本身 | 敏感（同升降会改变排序） |
| `p_pair = σ(true − false)` | `true − false` 差值 | 不敏感（同升降抵消） |
| `p_vocab = softmax(true)` | `true − log Z` | 依赖全词表配分函数 |

三者**数学上不等价**，不能互换；同一批候选在三种口径下可以给出不同的 top-3。

## 2. 与作者的一致性

| 项 | 作者 | 本文 | 是否一致 |
|---|---|---|---|
| 打分键 | `true_logit` | `ℓ("True")` 原始 logit | **形式上一致**（都取 logit，不取概率） |
| surrogate 模型 | 作者自有（Qwen3-VL-2B 一类） | 我们的 B 侧 surrogate（同一类模型，具体 checkpoint 见回执） | **未验证**（不同 checkpoint、不同 prompt/模板、不同 tokenizer） |
| 是否同构 | — | — | **未验证** |

**明确写"未验证"的理由**：同构需要证明"两个 surrogate 对同一候选的 logit 排序单调等价"，这要求同一批输入在两个模型上各跑一遍并比较排序（Kendall τ 或 top-3 重合率）。本批**没有**做这个对照实验（需要 GPU 前向）。因此本文只能说"口径形式相同"，**不能说"与作者等价"或"复现了作者的 utility"**。

## 3. 引用时的措辞（可直接用）

> 我们采用与 utility-mrag 形式相同的打分键（`True` token 的原始 logit），但未验证其 surrogate 与我们使用的模型之间是否排序等价（需在同一批候选上做双模型对照，本批未执行）。因此本文的 utility 结果**不构成**对作者方法的复现，只用于在同一协议内比较"按效用信号选 3 张"与"按余弦选 3 张"。

## 4. 不能说的话

- 不写"复现了 utility-mrag 的 utility"。
- 不把 `σ(true−false)` 或 `p_vocab` 的结果与本文 `ℓ("True")` 的结果并列成同一张表。
- 不写"两种定义等价 / 差别很小"——除非做过双模型排序对照（本批未做）。
