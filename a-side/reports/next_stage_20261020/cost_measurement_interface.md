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

`cpu_thread_env` 专门用来收口上一轮 `libgomp: Invalid value for environment variable OMP_NUM_THREADS` 的告警：正式基准必须**先固定合法值并记录实际生效值**，否则报错而不是静默继续。B 侧负责该告警的主查；A 侧只负责把生效值写进上面这个字段。

## 4. 明确不由本模块产出的指标

| 指标 | 状态 |
|---|---|
| 整卡显存占用峰值 | 必须由实测接口（如 `nvidia-smi` 采样或平台监控）写入 `device_memory`；本模块该字段恒为 `null` |
| 系统 RAM 峰值 | 同上，`system_ram` 恒为 `null` |
| 能耗 | 同上，`energy` 恒为 `null`；没有功耗计的机器只能说"未测" |
| 索引驻留字节 | 允许写**实测** RSS/常驻字节；不允许用 `18955 × dim × 4` 的理论向量大小顶替 |

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

## 7. 自检（已通过）

`python a-side/scripts/a13_cost_selftest.py` → `a-side/reports/next_stage_20261020/cost_recorder_selftest.json`，
**11/11 通过**，覆盖：

1. 嵌套 `request` 被拒绝（端到端只能一个外层计时器）
2. 分段之和 > 端到端时被标记
3. 同请求内同名段重复被拒绝
4. 未测段写 null 并进入 `unmeasured_segments`，不写 0
5. 离线/在线分开，离线不进入在线汇总
6. provenance 缺项拒绝创建
7. 观测数 < 20 不报 P95
8. `device_memory` / `system_ram` / `energy` 恒为 null

## 8. 仍未确定 / 需要实测

- 正式实验所需的样本量（每路径题数 × 重复次数）与是否包含 1033 全量：取决于预算批准。
- 目标边缘设备型号与是否支持 bf16/fp32 编码：未定。
- 索引类型（扁平 vs IVF/HNSW）：本批只交付扁平暴力检索接口；更大语料需要另立协议。
- 切换成本：需要真实多路径会话才能测，本轮只定义字段。
