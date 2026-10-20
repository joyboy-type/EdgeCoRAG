# utility 定义差异（定稿一页，2026-10-21）

**结论**：本文的 utility 与作者 utility-mrag 的 utility **形式相同、数学不等价、同构性未验证**。
因此措辞只能是"**形式相同**"，**不得**写"复现了作者的 utility"。

## 1. 三种定义（互不等价）

| 记号 | 定义 | 排序由什么决定 | 取值域 |
|---|---|---|---|
| `ℓ("True")`（**本文**） | 打分时词表里 token `"True"` 的**原始 logit** | `true` 本身 | ℝ |
| `σ(true − false)` | 只在 `[True, False]` 两 token 上做 softmax | `true − false`（差值） | (0,1)，单调于差值 |
| `softmax_vocab(true)` | 全词表 softmax 后取 `True` 的概率 | `true − log Z`（配分函数会变） | (0,1) |

## 2. 为什么不等价

1. **`ℓ("True")` vs `σ(true−false)`**：前者对"两个 logit 同时加同一个常数"敏感，后者不敏感（差值不变）。因此只要 `False` 的 logit 随候选一起漂移，两种口径就会给出**不同的排序**。
2. **`σ(true−false)` vs `softmax_vocab(true)`**：后者分母是**全词表**配分函数 `Z`，随候选变化；前者分母只含两个 token。`Z` 变化时 `true − log Z` 的排序可与 `true − false` 不同。
3. **三种口径都可能给出不同的 top-3**；同一批候选在三种口径下必须分别报告，**不得混表**。

## 3. 与作者的一致性：**未验证**

| 项 | 作者（utility-mrag, ACL 2026） | 本文 | 一致？ |
|---|---|---|---|
| 打分键 | `score_key: true_logit`（原始 logit，非概率） | `ℓ("True")` 原始 logit | **形式一致** |
| surrogate 模型 | 作者自有 surrogate（Qwen3-VL-2B 一类） | 本文 B 侧 surrogate（具体 checkpoint 见回执） | **未验证** |
| prompt / 模板 / tokenizer | 作者自有 | 本文自有 | **未验证** |
| 排序等价性 | — | — | **未验证** |

**验证所需条件（本批未做，需 GPU）**：
1. **同一批候选**（≥200 张，覆盖高分与低分区）；
2. **双模型各跑一次**，取 `ℓ("True")`；
3. 比较排序一致性：Kendall τ、top-3 重合率、并列数；
4. 判定标准（先写死）：`τ ≥ 0.9 且 top-3 重合 ≥ 90%` 才能称"可替换"；否则只能称"形式相同"。

在完成上述对照前，本文的 utility 结果**只用于同一协议内的相对比较**（utility 选 3 vs cosine 选 3），**不构成**对作者方法的复现。

## 4. 可直接用的措辞

> 本文采用与 utility-mrag 形式相同的打分键（`True` token 的原始 logit），但未验证两个 surrogate 之间是否排序等价（需同批候选的双模型对照，本批未执行）。因此本文的 utility 结果不构成对作者方法的复现，只用于同一协议内的相对比较。

## 5. 不能说的话

- ❌"复现了 utility-mrag 的 utility"
- ❌ 把 `σ(true−false)` 或全词表 softmax 的结果与 `ℓ("True")` 并列成同一张表
- ❌"两种定义差别很小 / 等价"（除非做过 §3 的对照）
- ❌"utility 优于 cosine"（在未验证同构前，只能说"在本协议内，按 `ℓ("True")` 选 3 与按余弦选 3 的差异是 X"）
