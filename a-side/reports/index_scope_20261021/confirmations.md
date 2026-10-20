# A 侧回应：4,712 清单 + 四处读法确认 + 数值溯源 + 接数字段（2026-10-21）

基线：`a-side` @ `4a60d75`｜本轮**不改任何 a-side 历史产物**、不重跑 1,203×4、不读 gold、未申请 GPU。
本轮新增仅在 `a-side/reports/index_scope_20261021/`。

---

## 1. 交 4,712 唯一图 sha256 清单

| 文件 | 规模 | sha256 |
|---|---|---|
| `a-side/reports/index_scope_20261021/unique_4712_sha256.csv` | 4,712 行 + 表头；400,731 B；**只有 sha256，无图像** | `83275ee7b0a0fbeb…`（全值见 summary.json `output.sha256`） |
| `a-side/reports/index_scope_20261021/unique_4712_summary.json` | 规模/角色分布/输入输出哈希 | — |

**列**：`sha256, n_instances, n_query, n_gt, n_official_retrieved, roles, in_instances`
`roles` 取值只有四种组合（与 14,475 完全自洽）：

| roles | 内容数 | 说明 |
|---|---:|---|
| `gt` | 2,073 | 只作 GT |
| `gt;official_retrieved` | 1,544 | 既是 GT 又是官方候选 |
| `official_retrieved` | 13 | 只作官方候选（**不在任何 query/gt 角色里**） |
| `query` | 1,081 | 只作查询图 |
| `query;gt;official_retrieved` | 1 | 三种角色都有 |
| **合计** | **4,712** | |

自洽校验（可用本表复核）：作 GT 的 3,618 = 2,073+1,544+1；作官方候选的 1,558 = 1,544+13+1；交集 1,545 = 1,544+1。

**B 侧算重合度的口径**（三步，不需要我这边再给东西）：

1. `18,955 ∩ 4,712`：把 B 的索引 sha 与本表 `sha256` 求交，计数 = 落在唯一内容里的条目。
2. `18,955 ∩ 14,475`：因 4,712 已含全部实例 sha（`occurrences.csv` 的 sha 集合 = 本表集合，脚本内 `assert` 过），此步结果**等于**第 1 步；要按"实例"口径算，应改口径为"条目数是否等于实例数"，不能用交集。
3. `两边都不在`：`18,955 − |18,955 ∩ 4,712|`。

> 命令与 rc：`python a-side/scripts/a32_unique_sha_list.py --corpus E:/EdgeCoRAG-A-store/corpus_v1 --out a-side/reports/index_scope_20261021` → **rc=0**；输出 `unique=4712 instances=14475 duplicates=9763`。

---

## 2. 对 B 四处读法的确认

### a) 双口径政策 —— **确认**

论文定量只用 **14,475（实例）/ 4,712（唯一内容）**；**18,955 只作"历史发布索引行数"**，出现在脚注/环境描述，不参与任何定量陈述（不写进语料规模、不写进召回分母）。
理由：14,475 与 4,712 都能由公开数据逐行复算（见 §3），18,955 不能；混用会让读者无法判断分母。补充一条**可用性**限制：即使 B 后续给出 `sources[]`，18,955 也只能升格为"可解释的发布索引行数"，**不能**改回"实例数"。

### b) `dedup.notes` 读法 —— **确认**

`dedup.by_identity=true / kept_duplicates=0` 只能读作"**该快照内身份互不重复**"，**不构成"建库时做过内容去重决策"的证据**。
理由：这两项是**结果属性**（快照里没有重复身份），不是**过程证据**（是否主动去重、去重键是什么、上游是否已去重）。反例：即便建库时完全没做去重，只要上游语料本身无重复，`by_identity` 也会是 `true`。

### c) `artifact_files` 的 shape 证据 —— **确认（附条件）**

`语料 [18955,768] float32` + `查询 [1353,768] float32` 与我的冻结接口**维度和 dtype 一致**（768 维、float32 落盘），可以确认为同一维度的向量空间。
**条件**：shape/dtype 只能证明"语料侧 18,955 行、查询侧 1,353 行、768 维 fp32"，**不能**证明这 18,955 行的**身份口径**。若 B 给出两个文件的 sha256 与文件头（npy/npz magic + shape），我可以复核 shape 而不必加载权重。

### d) 池不同 —— **确认**

B 的 history 与 live 都在 **18,955 池**（`approved.json` / `plan.json` 的 corpus 计数为证）；我的重建在 **4,712 池**（`corpus_v1`）。
同时确认 B 的限定：**池差能否完全解释 1049/1051/1062 的 gap 幅度，尚未证明**。我这边的三题分差（2.89e-4 / 8.81e-5 / 3.84e-3，保 top3 窗口）来自 4,712 池，**不能**直接与 B 的 1.27e-4~7.82e-4 并列比较；两边的数值必须各带 `pool_id`。

---

## 3. 三项数值溯源（回填）

### 3.1 28 个 parquet → 14,475：复算命令与 rc

```bash
python a-side/scripts/a31_index_scope_census.py \
  --data  <mrag_bench>/43620fde4044bb150e158c67ad7af6b6b11e1da2/data \
  --corpus <corpus_v1> --out a-side/reports/order_diff_20261021
# rc=0
# 输出：shards=28 questions=1353 gt=6357 retrieved=6765
#       instances=14475 unique=4712 duplicates=9763
```
逐分片行数写在 `census.json` 的 `per_shard`（每个 `test-000NN-of-000028.parquet` 的 `rows/gt/retrieved/instances`）；`per_question_count_check.total_matches=true`。
判定式：`1,353（每题 1 张查询图） + 6,357（gt_images 长度和） + 6,765（retrieved_images 长度和） = 14,475`。

### 3.2 4,712：`corpus_manifest.csv` 行数 + 去重口径

- 行数：`corpus_manifest.csv` 数据行 = **4,712**（一行一内容，按 sha256 升序）；`occurrences.csv` 数据行 = **14,475**；两文件 sha 集合完全一致（`a32` 里 `assert`）。
- 去重口径：**身份 = sha256(图像 JPEG 字节)**；同一身份**只保留一行**；`occurrences.csv` 记录它出现的每一次实例（角色 + rank），因此 14,475 − 4,712 = **9,763** 次重复出现被保留在实例表里、不进清单。
- 角色计数：`query` 1,353 / `gt` 6,357 / `official_retrieved` 6,765（三者相加 = 14,475）。

### 3.3 "4,712 图 ≈26 分钟"：**观察值，不是归档实测**

| 项 | 值 |
|---|---|
| 性质 | **墙钟观察**（编码阶段一次跑完的记录），**没有留下回执文件**；因此不是可复现实测，未归档 |
| 换算 | 4,712 图 / ≈26 min ≈ **0.33 s/图** |
| 硬件 | RTX 4060 Laptop（8 GB），单机 |
| dtype | **float32**（`SentenceTransformer(..., torch_dtype=torch.float32)`） |
| TF32 | **关闭**（`allow_tf32=False`，cuda + cudnn） |
| 其它 | `batch_size=1`（图像侧逐图）、`normalize_embeddings=False`（归一化在 float32 层外做）、逐图从磁盘解码 |
| 与归档锚点 0.0592 s/图 的差 | **5.6×**；原因**未确证** |

**未确证的具体含义**：我没有做过"同一硬件、同一代码、同一 dtype 下 batch=1 vs batch=8/16"的对照编码计时，也没有锚点那次的硬件/批次记录，因此**不能断言** 5.6× 来自"单图 batch + 逐图解码 + fp32/TF32 关闭"中的哪一项。要确证需一次带回执的编码计时（GPU 轮，`hardware.cpu_thread_env`、dtype、TF32、batch 全记录）。
在此之前，本数字在论文里只能写成"观察值（未归档实测）"，**不得**当作正式实测。

---

## 4. 接数准备：B 的旁路导出列够不够

B 拟输出：`qid / source / rank / sha256 / score_fp32 / dtype / tf32_enabled / batch_size / pool_id / stack_versions / command_sha256`

**结论：算"被换对的分差"够用；做归因不够，需补 6 个字段。**

### 4.1 够用的部分

`qid + source + sha256 + score_fp32 + rank + pool_id` 足以：两侧按 `sha256` 联接 → 取被换的那一对 → 分差 = `|score_live − score_history|`，并按 `pool_id` 分开报告。

### 4.2 必须补的 6 个字段（现在补，别等 GPU 跑完）

| 字段 | 为什么必须 |
|---|---|
| `normalize_locus` | 取值 `model_internal` / `post_cast_float32`。归一化位置会改序（A 侧实测 917/1,203 改序），没有它无法区分"归一化"与"dtype"。 |
| `encoder_weights_sha256` | 模型权重身份。`model_revision` 是分支指针，不是权重字节。缺它就无法排除"权重不同"。 |
| `model_revision` | 与权重 sha 一起构成可复核的模型身份（HF id + revision）。 |
| `query_image_sha256`（或 `query_vector_sha256`） | 确认两侧用的是**同一张查询图**；否则分差可能来自换图。 |
| `n_pool_scored` | 打分时的候选池规模（18,955 全量 vs 截断）。池大小不同则分数不可直接比。 |
| `self_match_removed` | 布尔。有无自匹配剔除会改变第 1 名与相邻分差。 |

**建议同时带**：`k`（top-k）、`sort_key_rule`（如 `(-score, sha256)`）、`run_id`（同一次运行分组）、`score_precision`（是否按 9 位小数落盘——**要求至少 9 位有效数字或 hex**，不要四舍五入到 6 位）。

### 4.3 一个硬要求

`score_fp32` 请用 **float32 原值的十进制全精度（≥9 位有效数字）或 `float.hex()`**。若导出器用 `%.6f`，相邻分差 1e-4 量级会被舍入吃掉，届时无法判定"是否只差一次相邻交换"。

---

## 5. 本轮产物与校验

| 文件 | rc | sha256（前 16） |
|---|---:|---|
| `a-side/scripts/a32_unique_sha_list.py` | — | 见仓库提交 |
| `a-side/reports/index_scope_20261021/unique_4712_sha256.csv`（4,712 行） | 0 | `83275ee7b0a0fbeb` |
| `a-side/reports/index_scope_20261021/unique_4712_summary.json` | 0 | — |
| 本文件 `confirmations.md` | — | — |

未读 gold、未开 GPU、未改任何 a-side 历史产物（36 个 artifacts 与 `artifacts.json` 均未触碰）。
