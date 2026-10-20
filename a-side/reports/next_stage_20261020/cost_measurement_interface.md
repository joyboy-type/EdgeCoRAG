# 正式系统成本测量接口（A 侧检索段）

日期：2026-10-20。本文件是该接口在仓库内的唯一口径。**本批没有测任何新数值**：只交付接口、边界定义与自检。
真实数值必须在独占 GPU 的正式实验中产出；未测项一律写 null 并注明原因，不写 0。

## 1. 为什么必须重做（不能沿用上一轮的三个数）

上一轮 smoke 回执里的 `10.493 GiB`、`1.563 s`、`0.505 s` 各有明确边界，**都不能直接当正式指标**：

| 上一轮的数 | 实际含义 | 不能写成 |
|---|---|---|
| `process_allocator_peak_allocated/reserved` | PyTorch 进程分配器峰值 | 整卡占用、系统 RAM、索引驻留内存 |
| 组件中位数（0.0913 / 0.0154 / 1.2394 / 0.389） | 分段计时 | 相加代替端到端 |
| `setup 11.227 s` / `22.948 s` | 构造函数内部 setup / 验证+初始化 | 含进程启动与全部导入的冷启动 |

此外 5 题 × 15 观测不足以报 P95，也不能当吞吐能力。

## 2. 段定义（唯一字段名）

实现：`a-side/scripts/a12_cost_recorder.py`（不依赖 torch，CUDA 同步由调用方注入）。

### 2.1 离线（一次，单独报告，不进在线请求）

| 段名 | 起止 | 必记伴随字段 |
|---|---|---|
| `corpus_encode_seconds` | 语料逐图解码 + 预处理 + 编码器前向（含同步） | 图像数、dtype、batch、设备 |
| `index_build_seconds` | 归一化/维度截断/矩阵落盘（可选索引训练） | 维度、行数、文件字节、是否压缩 |
| `index_load_seconds` | 索引从磁盘到常驻内存/显存 | 驻留位置、常驻字节（实测，不是理论向量大小） |

### 2.2 在线（每题）

| 段名 | 起止 | 与 B 的对应 |
|---|---|---|
| `query_decode_encode_seconds` | 查询图解码 → 预处理 → 编码 → 同步 | 同上一轮 `query_decode_encode_seconds` |
| `ranking_no_self_seconds` | 全库打分 → 无自匹配过滤 → 取 top-k | 同上一轮 `ranking_no_self_seconds` |
| `utility_scoring_seconds` | 10 个候选逐个效用前向（含同步） | 与 `selection_request_build_seconds` **分开**，上一轮是合在一起的 |
| `selection_request_build_seconds` | 选 3 张 + 请求组装（不含生成） | 上一轮 `selection_request_build_seconds` |
| `switch_seconds` | A0↔A1↔A2↔A3 或模型切换开销 | 单列，不摊进任何路径 |
| `generation_decode_seconds` | 生成与解码（B 主责，本模块只接收上报值） | 同上一轮 |

**端到端**：由外层单一计时器测一次（`rec.request(...)`）。分段时间只用于分解；`component_sum_seconds` 仅作一致性诊断，模块会在 `component_sum > e2e` 时置 `component_exceeds_e2e=true`，不得反过来把它当端到端。

## 3. 必须随每行写入的 provenance

```
hardware: {gpu, vram_gib, driver, cpu, cpu_thread_env}
encoder:  {model, revision, dtype, batch, tf32}
corpus:   {corpus_version, rows, content_digest_sha256}
protocol: 协议版本串
warm_state: cold | warm | warmup
```

缺任一项 `CostRecorder` 拒绝创建（已在自检里断言）。

`cpu_thread_env` 专门用来收口上一轮 `libgomp: Invalid value for environment variable OMP_NUM_THREADS` 的告警：**构造时就强制校验**——必须是**正整数**（记录实际生效线程数）或字符串 **`"unfixed"`**；`"auto"`、空串、`0`、负值、布尔、缺失一律抛 `ProvenanceError`，不是"事后提醒"。给 `"unfixed"` 时每条记录的 `unmeasured_provenance` 里会写明"只作技术联调，不得进入正式基准"，`summary()` 里也保留该值。B 侧负责固定该告警；A 侧负责让"没写生效值"根本无法构造记录。

## 4. 资源指标：由外部实测注入（A2）

本模块**从不自己产生**整卡显存 / 系统 RAM / 能耗；但提供**两个明确的注入 API**，让外部实测值能落进同一条 JSONL 记录：

### 4.1 API（二选一）

```python
# 行内注入：在 request 内调用
with rec.request("mragb:10", strategy="cosine"):
    with rec.segment("ranking_no_self_seconds"): ...
    rec.resources(
        device_memory={"value": 7.1, "unit": "GiB",
                       "method": "nvidia-smi --query-gpu=memory.used 10Hz"},
        system_ram={"value": 12.4, "unit": "GiB",
                    "method": "/usr/bin/time -v Maximum resident set size"},
        energy={"value": 1840.0, "unit": "J", "method": "wall meter, 1s sampling"},
    )

# 后处理合并：把外部采集的测量值按 req_id 合并进已有 JSONL
from a12_cost_recorder import attach_resources
summary = attach_resources("cost.jsonl", provider=lambda req_id, row: {...},
                           out_path="cost.merged.jsonl")
# summary = {rows, filled:{device_memory:n,...}, still_null:{...}, missing_req_ids:[...]}
```

### 4.2 语义与强制校验

| 项 | 规则 |
|---|---|
| `null` | 表示**未测**；不得写成 `0`，也不得用空对象代替 |
| 必填字段 | 注入值必须是对象，含 `value`（数值、非负）、`unit`（非空）、`method`（非空） |
| 分配器口径 | `method` 命中 `allocat / memory_allocated / memory_reserved / reserved_peak / torch.cuda.memory` 时**直接抛错**；分配器峰值不得改名成整卡/系统/能耗 |
| 全部未测 | `rec.resources()` 不带任何一项时抛错（防止空调用被误当成"测了 0"） |
| `attach_resources` | 只覆盖非 null 值；未提供的保持 `null` 并计入 `still_null`；提供非法值时抛错 |

| 指标 | 允许来源 | 不允许 |
|---|---|---|
| 整卡显存占用峰值 | `nvidia-smi` 采样、平台监控、NVML | `torch.cuda.max_memory_allocated()` 等分配器统计 |
| 系统 RAM 峰值 | `/usr/bin/time -v`、容器监控、`psutil` 采样 | 估算值 |
| 能耗 | 外接功率计 / 平台计量 | 用 TDP×时长推算写成实测 |
| 索引驻留字节 | 实测 RSS / 常驻字节 | `18955 × dim × 4` 的理论向量大小 |

## 5. 样本量与统计口径

- 每题至少 3 次测量，另 1 次预热不进入统计；预热单独写 `warm_state=warmup`。
- **观测数 < 20 时不报 P95**（`_stats` 会返回 `p95=null` 并给出理由）；正式 P95 需要每路径 ≥ 100 观测。
- 冷/热必须分开：`index_load_seconds` 与首个请求单列，不与热请求混算。
- 跨设备不得相加。A 旧 4060 与 B 旧 3090 的分段只能各自成表。

## 6. 与 B 的统一外层入口对接

B 的 `e2e_smoke.py` 已是外层计时器。对接方式（二选一，建议 A）：

- **方案 A（推荐）**：A 提供 `CostRecorder` 作为外层，B 的生成段以 `rec.segment("generation_decode_seconds")` 包住；A 的检索/选择段同名包裹。同一 run_id 输出一行 JSONL，端到端只有一条计时。
- **方案 B**：B 保留自己的外层计时，A 在每个请求返回 `{segments, marks}` 字典，由 B 合并。要求：B 的外层必须在**调用 A 之前**开始、在**写盘之后**结束，且 A 返回的段不得重复计入。

两种方案都必须满足：同一请求只有一条 `end_to_end_seconds`，其余是段。

## 7. 自检（已通过，32 项）

`python a-side/scripts/a13_cost_selftest.py` → `a-side/reports/next_stage_20261020/cost_recorder_selftest.json`，
**32/32 通过**，覆盖：

**A 组（计时与口径）**
1. 嵌套 `request` 被拒绝（端到端只能一个外层计时器）
2. 分段之和 > 端到端时被标记
3. 同请求内同名段重复被拒绝
4. 未测段进入 `unmeasured_segments`，不写 0
5. 离线/在线分开，离线不进入在线汇总
6. provenance 必填项缺失拒绝创建
7. 观测数 < 20 不报 P95
8. 未注入资源时 `device_memory` / `system_ram` / `energy` 为 `null`

**B 组（A1：强制线程字段）**
9. `hardware.cpu_thread_env` 缺失 → 拒绝
10. `"auto"` / 空串 / `0` / 负值 / 布尔 → 拒绝（5 个用例）
11. 正整数 `8` → 通过，落盘字段与 summary 都是 `8`
12. `"unfixed"` → 通过，且每条记录 `unmeasured_provenance` 留痕、summary 标 `unfixed`

**C 组（A2：资源注入）**
13. `resources()` 合法注入 → 落到当前请求记录
14. 缺 `value/unit/method` → 拒绝
15. `method` 为分配器口径（`torch.cuda.max_memory_allocated()`）→ 拒绝
16. 负值 → 拒绝；全部未测的空调用 → 拒绝
17. `attach_resources()` 按 `req_id` 合并，未提供的保持 `null`
18. `attach_resources()` 遇非法值（分配器口径）→ 拒绝

**段名未改动**：`query_decode_encode_seconds` / `ranking_no_self_seconds` / `selection_request_build_seconds` / `generation_decode_seconds` / `utility_scoring_seconds` 全部保持原样（自检里有段名集合断言）。

## 8. 仍未确定 / 需要实测

- 正式实验所需的样本量（每路径题数 × 重复次数）与是否包含 1033 全量：取决于预算批准。
- 目标边缘设备型号与是否支持 bf16/fp32 编码：未定。
- 索引类型（扁平 vs IVF/HNSW）：本批只交付扁平暴力检索接口；更大语料需要另立协议。
- 切换成本：需要真实多路径会话才能测，本轮只定义字段。
