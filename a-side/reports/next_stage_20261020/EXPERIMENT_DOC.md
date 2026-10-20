# EdgeCoRAG 实验文档（A 侧整合版 v1）

维护：A 侧｜更新：2026-10-20｜适用提交：`a-side/next-stage-20261017` @ **`4a60d75`**（tag `a-iface-20261021-fix7`）
本文是**唯一整合入口**：B 不需要在六份 A 侧文档之间来回跳，按本文执行即可；细节文件在每节末尾给出。

---

## 0. 一页速览

| 问题 | 现状 |
|---|---|
| 检索接口 | **已冻结** `a-side/retrieval-interface-v1`（fp32 / float32 重归一化 / `(-score, sha256)` 次序）；36 个哈希绑定产物，干净检出 `a17` → `rc=0 / 36 / 0` |
| 排序可复现性 | fp32 下查询批大小 16→1 的排序差异 **0/1203**；bf16 下 187/1203 改序、36 条改集合 → 所以冻结 fp32 |
| 排序脆弱度 | `min_adjacent_margin<1e-3` 的题：768 维 **83.35%**、128 维 **94.97%** → **必须用固定 rank 列表，不能重排** |
| 语料口径 | 公开可复现 **4,712** 唯一内容 / **14,475** 图像实例；smoke 报告写 **18,955** → 差 4,480 / 14,243，**未裁定** |
| 四路径 Oracle 上界 | `official_retrieved_top3` 条件下 frozen +20.6 pp（**上界，不可部署**） |
| 本轮能否跑生成 | **否**——需预算批准；本文只定义矩阵、口径与验收 |
| 待 B 交 | ① `index_receipt` ② 5 题两份 10 行 ③ 向量指纹 ④ 编码参数 ⑤ a18 跨栈回执 |
| 协议串 | `a-side/retrieval-interface-v1`（改 top-k/select-k/排序键/归一化/种子 → 升 v2） |

---

## 1. 已冻结的检索接口 v1

### 1.1 版本与哈希

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench` rev `43620fde4044bb150e158c67ad7af6b6b11e1da2`，split `test`（1,353 题） |
| 编码器 | `google/embeddinggemma-2` rev `914f7f89142e33e77833254d9c9b90c3cef7303b`；`model.safetensors` sha256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79` |
| 运行栈（测 0/1203 的栈） | torch `2.11.0+cu128`、torchvision `0.26.0+cu128`、transformers `5.19.0`、sentence-transformers `6.1.0`、Pillow `12.3.0`、numpy `2.5.2` |
| 语料 | `corpus_v1`，4,712 唯一内容，`content_digest=31ade7b7e2454d0b9fcd58568247dd2a6862e15273fdd65e1d12ed50e373264e` |
| 产物清单 | `a-side/retrieval_if_v1/artifacts.json`（36 个文件，逐文件 sha256/字节，`summary.hash_normalization="LF"`） |

### 1.2 执行口径（逐字实现）

```
解码：PIL.open(落盘 JPEG q95 字节).convert("RGB")     # 不缩放、不裁剪
模型：SentenceTransformer(MODEL_ID, revision=REV,
        config_kwargs={"audio_config": None},
        model_kwargs={"torch_dtype": torch.float32})
编码：.encode([{"image": im}], batch_size=1, normalize_embeddings=False)   # 图像侧无文本前缀
归一化：v32 = v.astype(float32); v32 /= max(||v32||, 1e-12)               # float32 层，不用模型 dtype 内归一化
算术：torch.backends.cuda.matmul.allow_tf32 = False
      torch.backends.cudnn.allow_tf32 = False
打分：score = V32 @ q32（numpy float32，逐题）
排序：order = lexsort(keys=(-score, image_id))     # 主键分数降序，次键 sha256 升序
```

**候选身份** = `sha256(JPEG q95 字节)`；语料行序 = `sha256` 升序；同一内容只留一行。
**无自匹配**：先剔除 `image_id == 查询图 image_id`，再取前 10；不足则按原序补足并置 `refill_used=1`。
**维度**：768 及 128/256/512（取前 d 维后在 float32 下重新归一化，**不重新编码**）。

### 1.3 语料边界（必须随结果一起写）

本语料是**数据集内部图池**（GT 唯一 3,618、官方候选唯一 1,558、交集 1,545），天然偏相关：

| | 本接口（4,712 图池） | B 侧历史缓存 |
|---|---:|---:|
| 768 维 top10 any-hit | **799/1033（77.35%）** | **560/1033（54.21%）** |

两者**不是同一语料**，数值不可互换；论文的独立检索语料（Google Drive + CLIP）仍不可得，本接口**不宣称**复现该条件。

细节：`interface_freeze.md`（§1–§9 含升版规则、§3.2 行尾与 `verify.json` 语义、§5.1 utility 分工、§8 gold 边界）

---

## 2. 选择策略与证据组装

| 策略 | 规则 | 顺序 | 额外成本 |
|---|---|---|---|
| **cosine** | 候选池前 3 | 分数降序 | 0 |
| **utility** | 按 `ℓ("True")` 原始 logit 降序取 3 | 分数降序，并列按 sha256 升序 | 每候选 1 次前向（10 次/题） |
| **random** | 题内派生种子抽样 3 个（不放回） | 按分数降序 | 0 |

- **utility 打分口径冻结**：`ℓ("True")` **原始 logit**；`p_pair(True)=σ(true−false)` 与全词表 `p_vocab` 是**另两种排序**，不可互换（详见 §10.4）。
- **分工**：B 只交 `qid,sha256,score`（每题 10 行、覆盖候选池全部 sha）；**选 top3 / 并列打破 / slot 顺序 / 物化**由 A 的 `a15 --strategy utility --scores` 完成。
- **证据顺序**：查询图在前，其后 slot 1..3；写入 `evidence_list.jsonl` 与 `evidence_ids_order`。
- **gold 边界**：gold 只进评分与 S2（GT 证据 Oracle）/ 离线分析；**不进候选、排序、选择、prompt**。

细节：`interface_freeze.md` §5、§5.1、§8

---

## 3. 维度选择准则（只用 dev_150）

**L1 检索层筛选**（不需要生成）：主指标 **`any-hit@10`**；等价带 **≤1 题**（≤0.0067）；并列次序键 `set_recall@10` → `MRR@10` → 更小维度 → 再取较小维度。
**L2 下游层定档**：dev_150 上 `strict_choice_v1` 准确率；同模型同题配对 bootstrap 95% 区间跨 0 = 并列 → 回到 L1 次序键。
**`order_fragile` 题**（`min_adjacent_margin<1e-3`）：**主分析不剔除**（固定分母），但**必须分层报告**；两层符号相反 → 判"未解决"，默认沿用 768。
**禁止**：用 `frozen_test` 的任何指标参与选择；`internal_holdout` 不得当选择集。

dev_150 现状（L1 参考，不是定档结论）：

| 维度 | any-hit@1 | any-hit@5 | any-hit@10 | set_recall@5 | set_recall@10 | MRR@10 | order_fragile |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 768 | 0.3800 | 0.6667 | 0.7400 | 0.3020 | 0.4420 | 0.5000 | 0.847 |
| 512 | 0.3800 | 0.6600 | 0.7333 | 0.3020 | 0.4420 | 0.4989 | 0.793 |
| 256 | 0.3600 | 0.6600 | 0.7333 | 0.2953 | 0.4340 | 0.4897 | 0.853 |
| 128 | 0.3333 | 0.6200 | 0.7267 | 0.2860 | 0.4113 | 0.4600 | 0.920 |

细节：`selection_policy.md` §1–§6

---

## 4. 最佳固定 RAG（P1–P4）与四路径矩阵

| 代号 | 含义 | 可部署 |
|---|---|---|
| **P1** cosine 固定 | 前 3 张 | 是 |
| **P2** utility 固定 | `ℓ("True")` 前 3 | 是 |
| **P3** dev 最优固定（= 任务书 R03 的"最佳固定 RAG"） | dev_150 上从 {P1,P2,random} 选一条，frozen 只评一次 | 是 |
| **P4** Oracle 逐题最优 | 需标签 | **否**，标 `post hoc`，只作上界 |

四路径：`A0` E2B 无证据 / `A1` E2B + 检索 select3 / `A2` E4B 无证据 / `A3` E4B + 检索 select3。
**已知离线矩阵**（证据条件 `pool_id=official_retrieved_top3`，**不是**自主检索；保真校验 30/30 格与 `quality.csv` 一致）：

| cohort | A0 | A1 | A2 | A3 | 固定最优 | 路径 Oracle | 增益 |
|---|---:|---:|---:|---:|---|---:|---:|
| frozen_test_1033 | 375 | 366 | 397 | 427 | A3 41.34% | **640（61.96%）** | **+20.6 pp** |
| internal_holdout_150 | 58 | 54 | 48 | 57 | A0 38.67% | 88（58.67%） | +20.0 pp |

互补性（frozen）：仅该路径答对 `A0 41 / A1 40 / A2 41 / A3 54`；四条全错 393；四条全对 166。
**Oracle 是上界，不是路由器可达收益**；与 S2（GT 证据 Oracle）不是同一概念，分表报告。

细节：`routing_protocol_v2.md`（§1 定义 / §2 question-runs / §4 可部署路由器特征白名单 / §6 验收 / §7 离线矩阵）

---

## 5. 成本测量协议

### 5.1 段名（唯一口径，不允许改名）

| 类别 | 段名 |
|---|---|
| 离线（一次，不进在线请求） | `corpus_encode_seconds`、`index_build_seconds`、`index_load_seconds` |
| 在线（每题） | `query_decode_encode_seconds`、`ranking_no_self_seconds`、`utility_scoring_seconds`、`selection_request_build_seconds`、`switch_seconds`、`generation_decode_seconds` |

端到端由**外层单一计时器**测一次（`rec.request(...)`）；`component_sum_seconds` 只作诊断，`component_sum > e2e` 会置 `component_exceeds_e2e=true`，**不得反过来当端到端**。

### 5.2 强制 provenance（缺项构造即报错）

`hardware.cpu_thread_env` 必须是**正整数**（生效值）或字符串 `"unfixed"`；`"auto"`/空串/`0`/负值/缺失 → `ProvenanceError`。给 `"unfixed"` 会写 `unmeasured_provenance`，标注"仅技术联调、不得进正式基准"。

### 5.3 资源指标（只能外部实测注入）

`rec.resources(device_memory=…, system_ram=…, energy=…)` 或 `attach_resources(jsonl, provider)`；
注入值必须含 `value/unit/method`，`method` 命中 `allocat|memory_allocated|memory_reserved|reserved_peak|torch.cuda.memory` 直接抛错；`null` 恒表未测，空调用也拒绝。

### 5.4 统计与边界

每题 ≥3 次测量 + 1 次预热（预热不进统计）；**观测数 <20 不报 P95**；冷/热分开；跨设备不得相加。
整卡显存 / 系统 RAM / 能耗只有实测才报；**allocator 峰值不得改名**。

细节：`cost_measurement_interface.md`（自检 32/32）

---

## 6. 数据合同（B 要交的东西）

| # | 文件 | 关键要求 |
|---|---|---|
| ① | `index_receipt.json` | 按 `contracts/index_receipt_field_mapping.md` 填；过 `a20` 且 `errors=[]`；`verdict=pending` 时 **`reconciliation.notes` 必须非空** |
| ② | `threshold_rows.csv` | 表头精确 `qid,source,rank,sha256,score`；每题 `history`/`live` 各 10 行；sha 64 位小写十六进制；覆盖 `10/1049/1051/1062/1117`；只有 live 的题要标注"缺 history" |
| ③ | `vector_fingerprints.json` | `{qid:{"live_sha256":"<64hex>","history_sha256":"<64hex>\|null"}}`，对 **float32 序列化字节**取 sha256 |
| ④ | `encode_params.json` | `{qid:{dtype_live,dtype_history,normalize_live,normalize_history,batch_live,batch_history}}`；`normalize∈{model_internal,post_cast_float32}`；`batch∈{1,16,group_of_N}` |
| ⑤ | `receipt_a18_<栈>.json` | `a18_batch_sensitivity_receipt/v1`；判定见 §7.3 |

**A 侧交付给 B 的产物（已在仓库）**：

```
a-side/retrieval_if_v1/
  pools/<cohort>__dim<D>__top10.csv          qid,pool_id,retriever_id,embed_dim,rank,sha256,score,is_self_removed,refill_used
  select3/<cohort>__dim<D>__cosine+random.csv  qid,strategy,embed_dim,slot,sha256,score,selection_seed,order_rule
  pool_quality/<cohort>__dim<D>__margins.csv  逐题分数结构 + min_adjacent_margin（脆弱度）
  metrics/retrieval_metrics_by_dim.csv        any-hit / set-recall / all-GT / MRR
  metrics/best_fixed_rag_placeholder.csv      空占位表（只有表头）
  corpus/{corpus_meta.json,corpus_manifest.csv,occurrences.csv}
  artifacts.json / verify.json
```

cohort × 维度：`smoke_20 / dev_150 / frozen_test` × `768/512/256/128`（**不产出 holdout**）。

---

## 7. 验收指标、停止条件与判定阈值

### 7.1 指标定义

| 类别 | 指标 |
|---|---|
| 质量 | `strict_choice_v1` 准确率（固定分母，格式失败计错，不自动重试） |
| 检索 | `any_hit@k` / `set_recall@k` / `all_gt_covered@10` / `MRR@10`（口径与分母写进 `metrics/retrieval_metrics.json`） |
| 路由 | 相对固定最优的增量；Oracle 差距闭合率 =（路由器 − 固定最优）/（Oracle − 固定最优）；切换与检索附加成本 |
| 稳健 | 同 qid 重复请求的候选池 / select3 / 输入顺序是否逐字节一致 |

### 7.2 停止条件

版本或哈希不符；qid 覆盖不全；显存或预算超预设；技术错误；`sources[]` 或索引口径仍不明 → **记录原因并停该阶段**。

### 7.3 跨栈判定阈值（写死）

| 条件 | verdict | 报告必须写 |
|---|---|---|
| `changed_order == 0` **且** `changed_set == 0` | `stack_invariant` | 可写"该栈上批大小不影响排序"，附回执 sha256 与栈信息 |
| 其它 | `stack_sensitive` | **"A 栈的 0/1203 不能外推"** + 改序题号 + 该题 top10 最大分差 + "统一到哪一栈"建议 |

### 7.4 逐题归因标签（8 类，`a21`）

`index_composition / model_or_weight / exact_tie_sort / normalization_locus / decode_path / dtype / batch_composition / insufficient_data`
每类都写"看到什么数值才成立"；**数据不足就写 `insufficient_data` 并列出缺哪个字段**，不得近似。

---

## 8. 运行矩阵与预算（估算，非实测）

| 路径 | 条件数 | dev_150 | frozen_test_1033 |
|---|---:|---:|---:|
| A0 / A2（无证据） | 各 1 | 150 / 150 | 1,033 / 1,033 |
| A1 / A3（3 策略） | 各 3 | 450 / 450 | 3,099 / 3,099 |
| 合计 | 8 | **1,200** | **8,264** |

另需 utility 前向：E2B × 10 候选 × 1,183 题 = **11,830** 次（新 pool 身份不同，**不能复用**上一轮的 12,030 次）。
估算：`11,830×1.24 s + 9,464×0.35 s ≈ 5 h GPU`，按 1.48 元/时 ≈ **7.4 元**（另计数据盘与取回）。
**执行顺序**：`smoke_20` 四路径各 1 次 → `dev_150` 四维度选择 → `frozen_test` 只跑选定维度一次。正式计时独占 GPU。

---

## 9. 复现命令

### 9.1 A 侧（已跑过，产物在仓库）

```bash
export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1
python a-side/scripts/a06_build_corpus.py --store "$EDGECORAG_CORPUS" --verify   # ≈190 s
python a-side/scripts/a17_verify_interface.py            # 期望 rc=0、36/0、files_with_crlf=0
python a-side/scripts/a17_verify_interface.py --strict-lf # 干净 LF 检出 rc=0
```

### 9.2 B 侧（校验 + 消费）

```bash
git checkout 4a60d75          # tag a-iface-20261021-fix7
git status --porcelain        # 期望空；跑完 a17 后仍须为空
python a-side/scripts/a17_verify_interface.py --out /tmp/verify.json   # 不弄脏树
python a-side/scripts/a20_validate_index_receipt.py <你的回执>.json      # errors=[]
python a-side/scripts/a18_batch_sensitivity.py --self-check             # 2/2
python a-side/scripts/a15_materialize_packets.py \
    --cohort dev_150 --dim 768 --strategy cosine \
    --corpus "$EDGECORAG_CORPUS" --out "$HOME/edgecorag/packets/dev_150_dim768_cosine"
# utility：拿到分数表后（选 top3 由 a15 完成）
python a-side/scripts/a15_materialize_packets.py \
    --cohort dev_150 --dim 768 --strategy utility --scores b_scores.csv \
    --corpus "$EDGECORAG_CORPUS" --out "$HOME/edgecorag/packets/dev_150_dim768_utility"
```

自检（全部 rc=0 才算过）：`a13 32/32`、`a19 14/14`、`a22 8/8`、`a21 9/9`、`a20 12/12`、`a18 2/2`、`a17 36/0`。

---

## 10. 已知事实与限制（写结果时必须带上）

1. **排序脆弱**：83.35%（768）/ 94.97%（128）的题 top10 最小相邻分差 <1e-3 → 消费方必须用固定 rank 列表。
2. **语料不同源**：本接口 4,712 图池 vs B 历史缓存 18,955 条目；同题 top10 any-hit 77.35% vs 54.21% → 数字不可互换。
3. **索引条目未裁定**：18,955 与 14,475/4,712 都不等（差 4,480 / 14,243）；三种假设与字段判据见 `index_receipt_adjudication.md`，**未下结论**。
4. **utility 三种口径不可互换**（数学上不同排序）：
   | 口径 | 排序由什么决定 |
   |---|---|
   | `ℓ("True")`（冻结） | `true` 本身 |
   | `p_pair(True)=σ(true−false)` | `true − false` |
   | `p_vocab(True)` | `true − log Z` |
5. **`0/1203` 绑栈**：只在 A 的栈成立；跨栈以 ⑤ 回执为准。
6. **跨题图像相关性未隔离**：精确重复把 1,338/1,353 题连成一个大组，不是实体隔离盲测。
7. **论文独立检索语料不可得**（Google Drive 不可达 + 许可未声明）；本接口不宣称复现该条件。
8. **utility 选图的顺序敏感度未测**（需 E2B 前向）；不能宣称"顺序不影响选图"。
9. **四路径 +20.6 pp 是上界**，且证据条件是 `official_retrieved_top3`，不是自主检索。

---

## 11. 未决事项与责任分工

| 事项 | 负责 | 阻塞点 |
|---|---|---|
| 18,955 三选一裁定 | A（B 供 ①） | 需 `sources[]` 的额外语料 sha256/规模 |
| 三题（1049/1051/1062）归因 | A（B 供 ②③④） | 缺数据只能 `insufficient_data` |
| 跨栈能否外推 | A（B 供 ⑤） | 需 B 栈上的 a18 回执 |
| 维度/策略定档（P3） | B（在 dev_150 跑生成） | 需 GPU 预算 |
| 四路径自主检索版 | A+B | 需预算；现有矩阵是官方候选条件 |
| MMDocRAG（B-03）/ 统计边界（B-04）/ T15 | B | 许可与 schema 未定 |
| utility 顺序敏感度 | A | 需 E2B 前向 |

---

## 12. 禁止表述（红线）

- 不把 Oracle（+20.6 pp）写成"路由器可达收益"；不与 S2 的 GT 证据 Oracle 混称。
- 不把 S1（官方候选 top3）改称"自主检索"；不把两批不同 `pool_id` 的数字并列成一张表。
- 不用 `frozen_test` 选维度/阈值/策略；已观察数据复核不写成"新盲测"。
- 不把"批大小/浮点误差"写成三题差异的已证原因（已排除：算术路径 0 改序、同配置逐位一致）。
- 不把 allocator 峰值写成整卡显存 / 系统 RAM / 能耗；未测不写 0。
- 不扩大 holdout；不上传原题、图片、完整原始响应、权重、私有归档。
- 不改 v1.10.1 的 prompt / 64 token / 严格评分 / BF16 / split / 原结果。

---

## 13. 变更规则

改 `top-k` / `select-k` / 排序键 / 抽样种子 / dtype / 归一化位置 / 解码路径 / 语料身份 → **升 `retrieval-interface-v2`**，新目录 + 重新生成 `artifacts.json` 与 `verify.json`，并说明哪些数值变了；不得覆盖 v1 产物。
标签只追加：`fix` → `fix2` → `fix3` → `fix4` → `fix5` → `fix6` → **`fix7`（当前）**；中间迭代内容见 `reports/TAG_NOTES.md`。

---

## 14. 本文件整合来源

`interface_freeze.md`、`selection_policy.md`、`cost_measurement_interface.md`、`routing_protocol_v2.md`、`index_receipt_adjudication.md`、`A_retrieval_consistency.md`、`A4_attribution_dryrun.md`、`A9_utility_mrag_feasibility.md`、`contracts/index_receipt*.{json,md}`、`A_return_20261020.md`、`reports/TAG_NOTES.md`。
冲突时以被引用文件为准；本文件只做整合与索引，不新增口径。
