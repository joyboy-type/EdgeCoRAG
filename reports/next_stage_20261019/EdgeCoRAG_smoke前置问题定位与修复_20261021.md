# EdgeCoRAG：smoke 前置问题定位与本地修复（2026-10-21）

本轮只做本地定位、定向修复与离线验证，没有开机、没有新增收费实验，也没有改动上一轮的原始预测、计划、lease、归档和回执。上一轮 smoke 的日志、`gpu-result-verified.json`、`plan.private.json`、`lease.authorized.json` 全部保持原样。

## 结论摘要

1. **CPU 线程告警**：`libgomp: Invalid value for environment variable OMP_NUM_THREADS` 不是本项目代码设置的。仓库内没有任何位置写入 `OMP_NUM_THREADS`（只在此前报告正文里出现过），父进程也不设该变量，worker 通过 `subprocess.Popen` 直接继承运行环境，因此非法值来自远端 shell/镜像环境。日志里两行出现在模型加载之前的进程初始化阶段，与"同一个 worker 进程内 NumPy 的 OpenBLAS libgomp 与 PyTorch 自带 libgomp 各初始化一次"一致；这是与日志位置相符的解释，不是已证实的结论（实例已关机，无法再查环境）。
2. **上一轮实际生效线程数无法恢复**，也没有回填：运行日志没有记录环境变量，计划与 setup 回执里也没有线程字段。本轮不猜测、不补写，只把它作为"已记录为未知"的事实写进新版本口径。
3. **检索排序差异不是排序代码问题**：用历史缓存查询向量 + 同一份索引 + 现场排序代码，可以逐位复现历史 top10 顺序；差异只可能来自现场重新编码出的查询向量本身。
4. **差异量级被夹逼在一个很窄的区间**：3 道题的差异各自只是 top10 内部**一次相邻换位**，且换位对的间隔恰好是该题 top10 内最小的相邻间隔；同时 5 题 top10 集合与 cosine top3 完全不变，因此现场与历史之间的相似度变化被夹在 **1.27e-4 以上、7.82e-4 以下**。换算成元素级相对误差约 0.6%–3.8%（bf16 一个 ULP 为 2⁻⁸≈0.39%），落在"同一图像在不同 batch/内核下重新编码"的量级内，与预处理/归一化等结构性差异（会到 1e-2 量级并改变集合）不符。这是间接夹逼，不是已定位到具体内核。
5. 两处都做了**可审计的代码修复**：继承值原样记录、非法值显式标记后覆盖、实际生效线程数事后实测；检索侧新增每条请求的相似度、相邻间隔、top10 边界裕度与查询向量指纹，使"现场与历史是否一致"以后可以直接测量，而不用从候选顺序反推。
6. **离线重放已把"复现效果"变成实测事实**：1203/1203 题的无自匹配 top10 顺序逐位复现；60 次请求的候选池、cosine top3、utility 选择全部与历史一致；5 题对照中 cosine 与 utility 所选证据在重放/历史/现场三方向完全一致，10/10 条生成输入（含 prompt 文本与证据顺序）完全相同。因此上一轮那次内部换位**没有影响模型实际输入**，唯一仍未被解释的是"现场编码向量与缓存向量的距离"，只能由新预算的受控对照回答。

## 1. CPU 线程告警

### 证据链

- 仓库代码/配置检索：`OMP_NUM_THREADS`、`set_num_threads`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS` 在源码与配置中均无写入；命中项只有历史报告正文。
- 执行链：`b-side/e2e_lease.py` 只更新 `PYTHONPATH/HF_HOME/HF_HUB_CACHE/HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/TOKENIZERS_PARALLELISM`，随后 `subprocess.Popen(command, ...)` 不传 `env=`，因此子进程完整继承父进程环境；父进程本身也继承启动它的远端 shell 环境。
- 日志位置：`worker.log` 中两行告警位于两条 `Loading weights` 之前，即进程启动、导入阶段；libgomp 在每次 OpenMP 运行时初始化时打印一次该错误，且失败后退回默认线程数。
- 因此非法值来自运行环境而非本项目；**具体非法字符串在上一轮没有被记录，已不可恢复**。

### 修复（`b-side/e2e_smoke.py`）

- 计划新增必填字段 `cpu_threads`：正整数或 `'affinity'`。旧计划缺少该字段会被 `validate_plan` 拒绝，不会被当成"和以前一样"继续跑。
- 新增 `configure_cpu_threads()`：在任何 NumPy/BLAS/PyTorch 导入之前，先**原样记录**继承的 6 个线程相关变量，标出非法值，再把 `OMP_NUM_THREADS/MKL_NUM_THREADS/OPENBLAS_NUM_THREADS/NUMEXPR_NUM_THREADS/VECLIB_MAXIMUM_THREADS` 固定为计划值；非法的 `OMP_THREAD_LIMIT` 被移除并记录，合法但会把线程数压低的 `OMP_THREAD_LIMIT` 直接报错。
- 新增 `observed_parallel_evidence()`：模型加载后实测 `os.cpu_count()`、affinity、`torch.get_num_threads()`、`torch.get_num_interop_threads()`，并在可用时用 `threadpoolctl` 读 BLAS 线程池；不可用时明确写"未验证"，不填默认值。
- 生效性硬校验：`torch.set_num_threads(计划值)` 后若实测与计划不符，直接抛错终止，不进入计时。
- 回执：`runtime/thread-configuration.json` 写"继承值 / 非法值 / 被移除值 / 已应用值 / 实测值"；`setup.json` 同时带 `cpu_threads` 与索引内存事实（resident vector 字节数、索引加载前后 `/proc` 进程计数）。

### 测试（先写失败测试再改代码）

新增 `ThreadConfiguration` 与相关用例，覆盖失败边界：非法继承值（`auto`、空串、带空格、`+4`、`4.0`、`0`、`-2`）被记录并覆盖；`OMP_THREAD_LIMIT` 压低线程数被拒；非法 limit 被移除并记录；`threads` 传 `bool/float/str/None/0/-1` 全部拒绝；`'affinity'` 解析；实测回执只含实测值。

## 2. 现场检索与历史缓存的内部排序差异

### 方法

只用已归档数据，不加载模型、不用 GPU：`work/next-experiment-20261019/retrieval_order_diagnostic.py` 读取历史语料向量、历史缓存查询向量、历史 no-self 排名和上一轮 32 条请求的现场候选顺序。

1. 用历史缓存查询向量 + 现场同一排序代码（`normalize` → `float32` GEMV → `np.lexsort((ids, -sim))` → 剔除自身身份补足 top10）重算 top10：**5 题全部逐位复现历史顺序**（脚本内断言，失败即退出）。
2. 把现场记录的候选顺序与历史顺序对齐，统计反转对、反转对的相似度间隔、top10 边界裕度。
3. 用同一份数据做扰动探针（同一图像以不同 batch/内核算子重编码的替代模型）：在 200 次/档的独立元素相对扰动下，检查 top10 集合与顺序能保持到多大扰动。

### 结果

| 题 | 与历史同序 | 反转对数 | 反转对间隔（相似度） | 所需最小相似度变化 | top10 边界裕度 | 隐含元素相对误差（bf16 ULP） |
|---|---|---:|---:|---:|---:|---:|
| mragb:10 | 是 | 0 | — | — | 2.28e-3 | — |
| mragb:1049 | 否 | 1 | 2.54e-4 | 1.27e-4 | 2.73e-3 | 0.61%（1.56） |
| mragb:1051 | 否 | 1 | 1.46e-4 | 7.28e-5 | 3.59e-3 | 0.35%（0.89） |
| mragb:1062 | 否 | 1 | 9.89e-6 | 4.95e-6 | 7.82e-4 | 0.024%（0.06） |
| mragb:1117 | 是 | 0 | — | — | 2.20e-3 | — |

- 3 道题的差异**都只是 top10 内最紧的那一对相邻候选互换**，没有跨越 top10 边界的进出；5 题 top10 集合、cosine top3、所选证据都与历史一致。
- 边界不变给上界：任何跨越第 10/11 名的相似度变化都小于最小边界裕度 7.82e-4；反转给下界：至少 1.27e-4。
- 换算：1.27e-4 的余弦变化对应约 0.61% 的元素级相对误差（约 1.6 个 bf16 ULP）；上界 7.82e-4 对应约 3.8%（约 9.6 ULP）。扰动探针中，3.1% 的独立元素扰动仍保持全部记录的 top10 集合。
- 结论（限定表述）：观察到的一致性落在"同一图像、同一 BF16 编码器、仅 batch=1 与批量批组合不同"应有的数值量级内；与"预处理/归一化/路径映射出错"这种结构性差异（会到 1e-2 量级并改变集合）不符。**没有定位到具体内核或具体原因**，因为上一轮没有保存现场查询向量，也没有做同进程受控对照。

### 修复（记录口径）

- `NativeRuntime.rank()` 现在返回 `(排序后的 id, 对应相似度)`；`search()` 保留为兼容包装。
- 新增 `ranking_evidence()`：每条请求记录 top10 分数、9 个相邻间隔、第 10/11 名边界裕度、边界候选、查询图自身在排名中的位置；新增 `vector_fingerprint()` 记录归一化后 float32 查询向量的 SHA-256（含 dtype/维度）。以前只能从候选顺序反推，现在可以直接测。
- 真实数据交叉核验：`verify_ranking_evidence_real.py` 在真实 18,955×768 索引上跑新记录函数，5 题的边界裕度与最小相邻间隔与独立诊断脚本逐值一致（1e-12 内），结果见 `ranking-evidence-realcheck-20261021.json`。
- 记录这些量对计时的影响：它们在被计时的检索组件内部完成，属于该组件成本的一部分，不再出现"计时区间外在记账"的隐藏开销。

## 3. 本轮改动与本地验证

| 文件 | 变化 |
|---|---|
| `b-side/e2e_smoke.py` | 线程记录/固定/校验、排序证据与向量指纹、`/proc` 内存计数、索引驻留事实、计划新增 `cpu_threads` 与 `entry` |
| `b-side/e2e_cost.py` | 新文件：正式三策略成本实验入口（`cosine/random/utility`、固定重复、P95 声明、设备级采样、RSS、样本结构披露） |
| `b-side/e2e_lease.py` | 父进程按 `plan['entry']` 在允许清单内分派校验器与执行入口，不再硬编码 smoke 路径 |
| `b-side/boot_watchdog.py` | 新文件：独立开机看门狗，deadline 到点即 `os.sync()` + SIGTERM 平台 supervisor，先写回执再动手，识别不到唯一 supervisor 就拒绝动手 |
| `tests/test_e2e_smoke.py` | 11 → 24 项 |
| `tests/test_e2e_cost.py` | 新文件 9 项 |
| `tests/test_boot_watchdog.py` | 新文件 7 项 |

本地验证命令（项目根目录；默认 python3 没有 NumPy/PIL，全目录用下文的 NumPy 运行时）：

```sh
python3 -m unittest discover -s outputs/EdgeCoRAG-delivery-20261017/tests -p test_e2e_smoke.py     # 24 OK
python3 -m unittest discover -s outputs/EdgeCoRAG-delivery-20261017/tests -p test_e2e_cost.py      # 9 OK
python3 -m unittest discover -s outputs/EdgeCoRAG-delivery-20261017/tests -p test_boot_watchdog.py # 7 OK

PY=<LOCAL_ROOT>
$PY -m unittest discover -s outputs/EdgeCoRAG-delivery-20261017/tests -p "test_*.py"             # 74 OK（全目录）
```

裸 `python3` 跑全目录会因缺 NumPy/PIL 采集失败（12 个环境性错误，属于既有测试模块的依赖问题，不是本轮改动引入）；换成上面的运行时后 74 项全部通过。

两份新计划都通过真实父进程入口（非执行模式）校验，且校验器由计划里的 `entry` 决定：

```sh
python3 b-side/e2e_lease.py --plan <复验计划> --root ../..   # 5 题 / 32 请求 / validated_no_model_loaded
python3 b-side/e2e_lease.py --plan <成本计划> --root ../..   # 20 题 / 3 策略 / 363 请求 / validated_no_model_loaded
```

把 `entry` 改成清单外路径会被父进程直接拒绝（已本地验证）。

离线分析（需 NumPy 运行时，不加载模型、不用 GPU）：

```sh
$PY retrieval_order_diagnostic.py            # retrieval-order-diagnostic-20261021/
$PY verify_ranking_evidence_real.py          # ranking-evidence-realcheck-20261021.json
$PY prepare_cost_experiment.py               # e2e-cost-proposed/、e2e-smoke-recheck-20261021/
```

新增产物：`retrieval-order-diagnostic-20261021/{diagnostic.json, per_query.csv}`、`ranking-evidence-realcheck-20261021.json`、`e2e-cost-proposed/{plan.private.json, lease.proposed.json, budget.proposed.json, validation.json}`、`e2e-smoke-recheck-20261021/{plan.private.json, lease.proposed.json, validation.json}`。

## 4. 仍需新预算才能做的事

- 直接测量现场查询向量与历史缓存向量的距离（本轮没有保存现场向量，无法离线补）。
- 同进程受控对照：同一张图分别以 batch=1 与 batch=4 编码，测出编码差与相似度差，把"batch 组合"从解释变成证据。
- 在真实 GPU 上确认线程固定后 `torch`/BLAS 的实测值与计划一致，并确认告警消失。

以上都属于新收费运行，需先获批预算。

## 5. 复现效果评估（离线重放，2026-10-21 追加）

目的：在任何付费运行之前，先用纯离线重放回答"修复后的链路到底能复现多少历史"。方法上把两件事分开——**流水线是否逐位复现历史**（可离线判定）与**GPU 现场编码是否复现缓存向量**（只能新预算判定）。

重放输入全部来自归档：缓存的查询向量代替现场编码、归档的 Gemma E2B True logit 代替现场 utility、生成用占位实现。不加载模型、不用 GPU。

### 结果

| 检查 | 覆盖 | 结果 |
|---|---|---|
| 无自匹配 top10 顺序复现（新代码，含新记录器） | 1203 题（20 + 150 + 1033） | **1203/1203 全部逐位一致**，耗时 5.3 秒 |
| 请求级重放（20 题 × cosine/random/utility） | 60 次请求 | 全部候选池与历史一致；cosine top3 全部一致；**utility 选择 20/20 与历史一致** |
| 与上一轮现场运行对照（5 题） | 5 题 | 候选池集合 5/5 一致；顺序 2/5 一致（另 3 题为已知的一次相邻换位）；**cosine 与 utility 的所选证据在"重放/历史/现场"三者间 5/5 完全一致** |
| 生成输入等价性（5 题 × 2 策略） | 10 条 | **10/10 完全一致**（证据顺序、证据集合、渲染后的 prompt 文本全部相同） |
| 复验入口（lease A）重放 | 5 题 × 2 策略 × 3 次 = 32 次 | 回执 `completed`，32 次请求、2 次预热、30 次计入统计；候选池与全部所选证据均与历史一致 |
| 正式成本入口重放 | 20 题 × 3 策略 × 2 次 = 120 次 | 回执 `completed`；每策略 n=40、逐题 n=20、P95 已按 nearest-rank 计算 |
| 新记录器对计时的影响 | 60 次采样 | 相对上一轮的组件定义（matmul + lexsort + 无自匹配）只多 **0.037 ms**（5.76 → 5.80 ms，本机 768 维索引）；向量指纹在计时区间之外 |
| 现场/参考向量对照的接线检查 | 60 次请求 | 60/60 均产出对照记录，重放向量与计划内参考向量逐位相等（l2=0）——证明该测量通路可用，真正的编码差要在 GPU 上读 |

结论：上一轮那 3 道题的内部排序差异**没有传导到证据集合，也没有传导到模型实际收到的输入**。上一轮报告只核对了 cosine top3，本轮把 utility 选择、证据顺序与完整 prompt 一起核对，结果全部一致。也就是说，上一轮质量实验所用的生成输入在这 5 题上是可复现的；剩下未被解释的只有"现场编码出的向量与缓存向量差多少"，而这正是新预算要测的。

### 顺带修掉的测量偏差

审计中发现记录器最初用整表 `positions` 字典定位名次，会在每条请求内多一次约 19k 元素的构造，抬高"检索"组件的计时。已改成只扫描到第 11 个非自身候选即退出（`ranking_evidence`），并保留完整校验供直接调用者使用。上面的 0.037 ms 就是改后测得的增量。

### 这一节关闭了什么、没关闭什么

- 关闭：排序、自身剔除与补位、cosine/random/utility 选择、证据顺序、请求组装、计时口径、成本入口的统计聚合——这些现在都是**被测过**的，不再依赖假设。
- 未关闭：现场编码向量与缓存向量的距离；同一图像 batch=1 与批量的受控对照；真实线程数与真实延迟。这三项都需要新预算。


## 6. 不能据此得出的结论

- 不能据此说上一轮 smoke 的计时"已在线程受控条件下测得"；那一轮的线程数是未知量。
- 不能据此说现场编码与历史缓存"逐位一致"或"完全等价"；只能说在 5 道已观察题上集合不变、差异被夹逼在相似度 1e-4 量级、且与单次相邻换位一致。
- 不能把本次离线夹逼当作因果实验或新盲测；也没有任何准确率、P95 或部署优势结论。
- 离线重放用的是缓存查询向量，**不能**据此说"现场编码与历史逐位一致"；它只证明流水线其余部分逐位复现，编码差异仍需 GPU 对照。
- 重放的计时只验证了记账与聚合路径，**不是**延迟测量，不能写进任何成本结论。
