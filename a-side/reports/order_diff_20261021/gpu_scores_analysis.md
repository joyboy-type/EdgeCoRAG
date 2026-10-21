# GPU 分数表先验 + 三题分差（2026-10-21）

输入：`a0eb7a0` 的 `reports/next_stage_20261019/gpu_scores_20261021/{scores_live.csv, scores_history.csv, scores_manifest.json}`。
经 GitHub API 拉取（git 443 被墙、SSH 无 github 密钥），两文件 sha256 与 B 声称值**逐一比对通过**。

## 0. 先验（全部通过）

| 项 | scores_live.csv | scores_history.csv |
|---|---:|---:|
| sha256 | `75a502aa…`（48333 B）✅ | `71c32ed3…`（39730 B）✅ |
| 数据行 | **50** | **50** |
| 列数 | **22** | **22** |
| `dtype` | `float32` | `bfloat16` |
| `pool_id` | `sha256:12f1e2fe…` | `sha256:94c69185…` |
| `n_pool_scored` | `4712`（一致） | `18955`（一致） |
| `self_match_removed` | 每题 10 行同一 `image:<查询图>`（= 剔除了这张自匹配图） | 全部 `not_in_pool_18955` |
| `score_fp32_hex` 回读 | 50/50 与 `score_fp32` 逐位相等（`float.fromhex`） | 50/50 相等 |
| qids | `10/1049/1051/1062/1117` | 同左 |

列序与 `similarity_bypass.py FIELDS` 一致（22 列：`identity,qid,source,rank,sha256,score_fp32,score_fp32_hex,dtype,tf32_enabled,batch_size,pool_id,k,sort_key_rule,self_match_removed,n_pool_scored,normalize_locus,encoder_weights_sha256,model_revision,query_image_sha256,stack_versions,command_sha256,run_id`）。

## 1. 前提（写进结论）

**live = fp32 / 4,712 池；history = bf16 / 18,955 池。两表不同池、不同 dtype。** 下面所有对比一律标"跨池"。

一个**决定性事实**：两侧在每个 qid 上的 `sha256` 集合**交集 = 0**（1049/1051/1062/10/1117 全部 0）。这意味着——

> **不存在"同时出现在两侧的同一张图"，所以不存在可以跨侧取分差的"被交换两行"。**

早前"三题各只差一次相邻交换"的观察，是**同池 fp32 内部**（如 batch 16→1、或归一化位置）的比较，与本轮的**跨池**（4,712 vs 18,955）是两回事。本轮历史池的 10 行里**没有一张**落在 live 的 4,712 池里。

## 2. 三题：两侧各自的相邻间隔（跨池，不可按 rank 对应）

| qid | 侧 | dtype/池 | 最紧相邻对 | rank | 相邻间隔 Δ |
|---|---|---|---|---:|---:|
| 1049 | live | f32/4712 | `7ee260a9…` vs `5e7ad2c3…` | 5–6 | **2.8914213181e-4** |
| 1049 | history | bf16/18955 | `bd6a83fd…` vs `ce69535a…` | 8–9 | 2.4348497391e-4 |
| 1051 | live | f32/4712 | `990220d3…` vs `76b59203…` | 4–5 | **8.815526962e-5** |
| 1051 | history | bf16/18955 | `71122bb3…` vs `2b406046…` | 7–8 | 4.363656044e-4 |
| 1062 | live | f32/4712 | `860c0210…` vs `cdf25a1f…` | 2–3 | **2.968907356e-3** |
| 1062 | history | bf16/18955 | `2d6140ab…` vs `b6c7c4b1…` | 3–4 | 1.925230026e-5 |

这些 Δ **全部不是同一对图**——live 的相邻对来自 4,712 池、history 的来自 18,955 池，两对图的 sha256 完全不同。

## 3. 判定（按写死规则）

规则：
1. 同池 fp32 复现同样换位 → 归因数值栈；
2. 不复现 → 归因归档 bf16 或池差，并指出哪一个；
3. 连 gap 都对不上 → 池仍不同，回退核对 pool_id。

实测：本轮**没有同池对照数据**（live 是 fp32/4712，history 是 bf16/18955；不存在两份"同池不同 dtype/参数"的表）。且两侧 sha256 交集为 0，gap 无法对同一对图比对 → 命中规则 2 与 3：**既不能归因数值栈，也不能单纯归因 dtype**，因为候选集合本身不同（池不同），dtype 只是次生差异。

## 结论句（固定）

> **三题中 0 题可归因于数值栈，其余归因于池与 dtype 差异（跨池比较，非同等条件）。**

要能给出"N 题归因数值栈"的非零 N，需要 B 补一份**同池 fp32 复现表**（在同一 4,712 池、fp32 下，用不同 batch/归一化/栈再打分一次，例如 `pool_id=12f1e2fe…` 且 `dtype=float32`），才能与 `scores_live.csv` 做真正的"同池对同图"换位比对。当前两份表**不能**支撑任何"换位归因"——它们连候选图都不重叠。

## 4. 产物

| 文件 | rc | sha256 |
|---|---|---|
| `a-side/reports/order_diff_20261021/gpu_scores_analysis.json` | 0 | 见仓库提交 |
| 本文件 | — | — |
