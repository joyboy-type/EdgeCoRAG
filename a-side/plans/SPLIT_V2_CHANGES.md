# 切分 v2 变更说明

> 对应基线 `9a223095e829d4baec98c761038f84127d9f7f62`。
> 本版修正 v1 的**三处已确认缺陷**，并把"同源隔离"从**不实的声明**
> 改为**可校验的字段 + 如实的不可行结论**。

---

## 1. 修正的缺陷

### 缺陷 1 ⛔ 已调试题漏进冻结集（实测复现）

**v1 的错误逻辑**：

```python
for name in ("smoke_20", "dev", "internal_holdout"):
    chunk = rows[pos:pos + take]
    forced = [it for it in chunk if it["raw_id"] in reviewed]   # 只在这里过滤
    ...
    pos += take
splits["frozen_test"].extend(rows[pos:])    # ← 已调试题从这里直接进冻结集！
```

**实测后果**（用 v1 + `reviewed_ids.txt` 复现）：

```
❌ I3b 已调试题不进入 frozen_test — 泄漏 3: ['mragb:3', 'mragb:4', 'mragb:43']
```

**严重性**：题数相加仍等于 1353，**纯对数查不出来**。
泄漏的题会被当作"未见过"的冻结题，最终评估因此虚高。

**v2 的处理**：在**任何**分配之前先把已调试题整体摘出，
后续流程（分层、配额、frozen 兜底）**根本看不到它们**。

### 缺陷 2 ⛔ 文档声称的规则与代码行为不符

**v1**：manifest 的 `rationale` 写"同源组整组分配"，
但代码实际是**按场景分层逐题分配**——名实不符。

**v2**：
- 不再用自由文本描述规则，manifest 写入**机器可校验字段** `assignment_rule`；
- 由 `verify_split.py` 的 **I9** 断言该字段存在；
- `stratification.role` 明确写"**仅用于均衡覆盖；不是同源分组依据**"。

### 缺陷 3 `--dry-run` 仍写文件

**v1**：`--dry-run` 照样写出 `*.txt` 与 `split_manifest.json`。

**v2**：dry-run 只计算、只打印、只自检，**不写任何文件**。
验证方式：执行前后比对 `splits/` 的文件列表——**完全一致**（已实测）。

---

## 2. 「同源隔离」的处理：从虚称改为如实结论

### 2.1 用户指出的问题

> `scenario`、`image_type`、`source` 本身不能证明是实际同源实体组。

**完全正确。** 它们是粗粒度属性：同 `scenario`（如 Angle）下有大量不同实体。

### 2.2 我方实测：实体级隔离在本数据集上**不可行**

为此专门构建了实体分组（`build_entity_groups.py`）并量化
（`quantify_entity_connectivity.py`）：

| 指标 | 实测值 |
|---|---|
| 唯一图片哈希 | 4,712 |
| **跨题共享的图片哈希** | **2,688** |
| 共享形态 | `gt↔ret` **1,423**、`gt↔gt` **1,091**、`query↔query` 162、`ret↔ret` 11、`query+gt+ret` 1 |
| **仅精确重复的连通组** | **7 组，最大组 1,338 题** |
| 每题平均共享图数 | **8.02**（中位 8，最大 11） |

**含义**：这个数据集在图片层面**几乎是一个整体**——
题与题之间通过 GT / 候选图大量复用而连通。
**每题平均与约 9 道其它题共享图片。**

**若强行做组原子分配**，实测结果荒谬：

```
计数: smoke_20=8  dev=7  internal_holdout=0  frozen_test=1338
```

### 2.3 v2 的处置

```python
# 分配前先探测巨型连通组
if gof and max_g > threshold:          # threshold = 25% × 总题数
    ent_meta["mode"] = "per_question_fallback_giant_component"
    ent_meta["fallback_reason"] = "..."
    gof = {}                            # 退化为逐题
```

manifest 中**如实记录**：

| 字段 | 值 |
|---|---|
| `entity_isolation.mode` | `per_question_fallback_giant_component` |
| `entity_isolation.giant_component_detected` | `true` |
| `entity_isolation.largest_group_size` | 1331 |
| `entity_isolation.why_infeasible` | 引用上述量化数据 |
| `entity_isolation.caveat` | **"跨子集的图片相关性**未能隔离**"** |

**这不是"已消除相关性"，而是"无法隔离"** —— 切分文档与 manifest 都按后者表述。

### 2.4 为什么"用图片反推实体"是合理的代理

没有官方实体/文档映射可用，因此用**图片内容**反推连通性：

1. **精确重复**：任一图片（查询图/GT/候选）的字节哈希跨题相同 → union；
2. **近重复**：查询图 dHash 汉明距离 ≤6 → union。

**局限（已在 manifest 声明）**：
- 是**代理分组**，非官方标注；
- dHash 对旋转、大幅裁剪、翻转**不敏感** → 会**漏并**；
- 同场景不同实体可能因查询图相似而**误并**。

→ 因此只可声明"**已按可检测到的重复做隔离**"，
**不可**声明"已消除全部相关性"。而实测连"可检测到的"都无法隔离。

---

## 3. `raw_id` 保持字符串

v2 **不对 `raw_id` 做任何整数化**。排序时用 `int()` 仅用于**排序键**，
写入文件的仍是原始字符串：

```python
rows_sorted = sorted(rows, key=lambda r: int(r["raw_id"]) if r["raw_id"].isdigit() else 0)
qids = [f"mragb:{r['raw_id']}" for r in rows_sorted]   # 原样写入
```

`verify_split.py` 的 **I5** 断言 `raw_id` 为字符串。

---

## 4. 已调试题清单（v2 使用）

来源 `splits/reviewed_ids.txt`（**支持 `#` 注释**——v1 的解析把注释行当成了 ID，
导致"丢失的已调试题"里出现整条注释文本）。

| 来源 | raw_id |
|---|---|
| B 侧提供 | `0, 1, 2, 3, 4, 24, 43` |
| A 侧接触 | `0, 1, 2, 3, 4, 24`（接口样例；`0` 另用于哈希稳定性试验） |
| **并集（v2 实际使用）** | **`0, 1, 2, 3, 4, 24, 43`** |

**另有全量聚合标签接触**，已如实写入 manifest 的 `label_exposure_note`：
A 侧曾在**全部 1353 题**上计算过与 GT 相关的**聚合统计**。
这些统计**未用于挑题**（切分只依赖 `raw_id` 与固定种子），但作为已发生的
标签接触如实声明。详见 `a-side/plans/REVIEWED_IDS.md`。

---

## 5. v2 产物

| 子集 | 题数 | sha256（前 16） |
|---|---|---|
| `smoke_20` | **20** | `363f69180d74a803` |
| `dev` | **150** | `8d5346df2690579e` |
| `internal_holdout` | **150** | `3181bc8ebad7a776` |
| `frozen_test` | **1033** | `c9f950652442bad9` |

**旧版本保留**：`*.txt` 与 `split_manifest.json`（v1）**未被删除**，
供对照与回退。v2 用 `*.v2.txt` 与 `split_manifest.v2.json`。

---

## 6. 验证结果

### 6.1 不变量测试（`verify_split.py --version v2`）

**18 项全部通过**，其中关键项：

```
✅ I1  子集互斥（无 qid 跨子集）
✅ I2  总覆盖完整 — 唯一 1353 / 期望 1353
✅ I3  已调试题不进入 internal_holdout
✅ I3b 已调试题不进入 frozen_test          ← v1 在此失败
✅ I4  已调试题全部有归属 — 7 题均已放置
✅ I5  raw_id 为字符串
✅ I8  声明计数 == 文件行数
✅ I9  manifest 声明了机器可校验的分配规则
✅ I10 声明了实体/近重复组的处理方式
```

**用户要求的针对性用例**（"已调试题原本落在四种子集时都被正确处理"）：
`verify_split.py` 的 I3/I3b/I4 逐子集检查已调试题归属，覆盖
`smoke_20`/`dev`/`internal_holdout`/`frozen_test` 四处。

### 6.2 可重现性

**三次独立运行**（含不同输出目录）哈希完全一致：

```
✅ smoke_20 一致   ✅ dev 一致   ✅ internal_holdout 一致   ✅ frozen_test 一致
```

### 6.3 dry-run 语义

执行前后 `splits/` 文件列表**完全一致** → `--dry-run` 确实不写文件。

---

## 7. 已知限制（未解决）

1. **实体/同源相关性未能隔离**（上述 §2.2，数据集属性所致，非切分缺陷）。
   建议 B 在分析时把 `(scenario, image_type)` 作为分层变量，
   并注意跨子集的图片复用可能带来相关性。
2. **已调试题清单可能不完整**：B 只提供了 7 个 `raw_id`；
   若 B 还调试过其它题，需补充后**重新生成 v3**（v2 保留）。
3. **场景分层不保证每个子集都覆盖全部 9 个场景的最优比例**——
   v2 用按层比例配额，已核对各子集均含全部场景，但小场景题数少。
