# 补充实验预注册：S3-8B 与 Qwen3.5-9B（2026-10-26）

本文件在**执行前**登记两项被登记为"非必需对照"的补齐实验的题单、条件、指标、判据、停止规则与硬件要求。
执行前提交并记录 SHA256；执行后**只追加回填**，不改本节任何阈值、题单或判据。

## 0. 范围与定位

| 项 | 是否必需对照 | 本文件处理 |
|---|---|---|
| S3 + Qwen3-VL-8B | 否（原登记：bf16+多图峰值 23.4 GB 撞 24 GB 卡，OOM） | **补跑**，不改精度、不改图像预处理 |
| Qwen3.5-9B（S0/S1/S2 × 1,033） | 否（原登记：线性注意力需两个 CUDA 扩展，环境无 nvcc；PyTorch 回退单题 >10 分钟） | **补跑**，先做可行性验证 |
| 整机能耗 / 开放问答人审 / 第二数据集 / bf16-vs-4bit 一致性 | 否 | **不在本文件范围**，保持原登记 |

两项补齐后**仍不产生**以下结论：S3 的跨尺度鲁棒性结论（29 题、AI 辅助、非盲审）、9B 的纯规模趋势（Qwen3.5 与 Qwen3-VL 属不同家族，规模与家族混淆）。

## 1. 共同来源与不可改动项

- 主预测来源：`logs/B_predictions.jsonl.gz`，SHA256 `df22ac5f70ce127629dbc807fd389af32282613c3d95815a68fe20760bf63c38`。
- 协议入口：`b-side/configs/protocol_main_v1.json`，SHA256 `50d57f136b7797619830be3d1e4f755da6a7029a067a76e7bd0c6914dd559b5e`。
- **冻结数字 `frozen_numbers.json` 不得修改**；新数字一律另立产物。
- 不改 `a-side/**`；不覆盖既有 S3 的四个模型结果。
- 生成参数与既有正式记录对齐：bf16、`quantization=none`、greedy、`seed=42`、`max_new_tokens=64`、同一 prompt 模板与图像顺序规则、原生 EOS、不设 `min_new_tokens`。
- 解析器：单一固定多项选择解析（`\b([ABCD])\b`），解析失败计错并保留在分母，不重试不修补。

## 2. 实验 1：S3 + Qwen3-VL-8B

### 2.1 模型与输入

- 模型：`Qwen/Qwen3-VL-8B-Instruct` @ `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`（4 shard，17.53 GB bf16）。
- 输入条件：`S3-pure`（query 图 + 3 张干扰图 = 4 图），逐 split 读
  `bound-v1.10.0/integrated/<split>/s3/inputs/S3-pure.json`，媒体根
  `bound-v1.10.0/integrated/<split>/s3/media/`（`image_order[].path` 相对此根）。
- 金标：`bound-v1.10.0/integrated/<split>/s3/scoring/answers.json`（`raw_id`/`qid`/`answer_choice`）。
- 题单与既有四模型完全一致：`dev=5`、`internal_holdout=2`、`frozen_test=29`；**不增删题、不重排、不换图**。

### 2.2 指标

- 每 split 报：`n`、答对数、准确率、逐题选择与金标、状态列；列名与既有 `S3_qwen_<model>_<split>.csv` 完全一致（`raw_id,qid,choice,gold,correct,status`），保证可直接并入同一张表。
- 与 S1 的同 qid 配对读数：答对/答错计数（用于把现有"四模型 S1→S3"表扩到五模型）；**只作子集描述**。
- 不新增 bootstrap 区间；如需区间，须另立修订。

### 2.3 判据

- 唯一判据：**是否完整跑完 29/2/5 三组**。完整即"可并入四模型表"，不完整即"不可判定"，不用成功子集替代。
- 不设"优于/劣于"方向判据；不做跨尺度、跨模型显著性结论。

### 2.4 停止条件

- 模型加载或任一题 OOM → **立即停该模型**，保留 partial，记录原始错误。
- **禁止**为塞进显存而降精度、量化、限制 `max_pixels`、缩图、改 prompt 或改题单（这些都会破坏"同精度、同预处理可比"前提）。
- 生成失败率（累计失败请求 / 累计已尝试请求）严格 >5% → 停并报。
- 会话剩 600 秒 → 停止新请求、收尾、落盘、关机。

### 2.5 硬件与精度要求

- **显存 ≥ 32 GB**，且支持原生 bf16（Ampere 及以后，compute capability ≥ 8.0）。V100（7.0）不可用。
- 不允许任何量化或 dtype 回退：`quantization=none`、`dtype=bfloat16` 必须写进回执。

## 3. 实验 2：Qwen3.5-9B（S0/S1/S2）

### 3.1 模型与输入

- 模型：`Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a`（4 shard，19.31 GB bf16）。
- 输入：`bound-v1.10.0/integrated/frozen_test/main/inputs/{S0,S1,S2}.json`，各 **1,033 题**；媒体根 `.../main/media/`。
- 金标：`.../main/scoring/answers.json`。
- 条件定义沿用主实验：S0 仅 query 图；S1 共享 top-3 检索图；S2 金标图（通常 5 张，77 道 `Incomplete` 为 1 张）。
- **可选追加**：`S2@3`（金标前 3 张）。若不跑，9B **不进入 A 节（同张数对照）**，只进入主表 T1 与 B 节（可得率/利用率）。是否追加须在执行前另立一句话登记。

### 3.2 环境要求（本次补齐的真正门槛）

必须同时满足：

| 项 | 要求 | 验证方式 |
|---|---|---|
| CUDA toolkit | **`nvcc` 可用，版本与 torch 的 CUDA 匹配（12.8）** | `nvcc --version` 输出入回执 |
| torch | 2.8.0+cu128（与既有正式记录一致） | `torch.__version__`、`torch.version.cuda` |
| Qwen3.5 模型类 | transformers 含 `Qwen3_5ForConditionalGeneration`（5.19.x） | 导入成功并记录版本 |
| 线性注意力扩展 | `flash-linear-attention`（Triton JIT，**不需要 nvcc**）；`causal_conv1d`（需编译，优先预编译 wheel） | 两个包版本入回执 |
| chat template | Qwen3.5 processor 不自动透传 tokenizer 的 `chat_template`，须显式从 `tokenizer_config.json` 回填 | 回执记录 `chat_template_sha256` |

`causal_conv1d` 若须源码编译，固定 `TORCH_CUDA_ARCH_LIST` 为目标卡算力（4090/L40S = `8.9`，A6000 = `8.6`，A100 = `8.0`），编译参数入回执。

### 3.3 可行性验证（先于全量，失败即停）

1. 装 `flash-linear-attention` 后，跑 **3 题**，量单题端到端耗时。
2. 判据：**单题 > 30 秒 → 放弃 9B 全量**，保留 3 题记录并报"可行性未通过"；**≤ 30 秒 → 进入全量**。
3. 该门槛在执行前固定，不因结果调整。

### 3.4 指标与判据

- 每条件报：`n=1033`、答对数、准确率、逐题选择/金标/状态；列名 `raw_id,qid,choice,gold,correct,status`。
- 派生读数（与既有五模型同口径）：S0/S1/S2 准确率进 T1 表；`r`（命中题数）与命中后条件正确率 `u` 进 B 节。
- **不新增区间**；沿用既有口径（B 节为 10,000 次题级 bootstrap），若需新增须另立修订。
- 判据只有完整性：三条件各 1,033 题全部尝试并落盘即"完整"。

### 3.5 停止条件

- 可行性验证未通过（单题 >30 s）→ 停，不跑全量。
- 任一条件 OOM → 停该条件并报，**不降精度、不量化、不缩图**。
- 生成失败率 >5% → 停。
- 会话剩 600 秒 → 停止新请求、收尾、关机。
- 若 bf16 无法容纳：**默认放弃**，不转 4bit（转 4bit 需 `bitsandbytes`+`accelerate`，且引入"与五模型不同精度"的新口径，须另行登记 bits/group size/工具版本，不在本文件授权范围）。

### 3.6 硬件要求

- **显存 ≥ 32 GB，建议 40–48 GB**：9B bf16 权重 18.3 GB，加 4–5 图的开销后 24 GB 不足。
- 原生 bf16（compute capability ≥ 8.0）。

## 4. 单会话编排（一次开机完成两项）

| 序 | 步骤 | 预估 | 失败处置 |
|---|---|---|---|
| 0 | 环境核验（`env_check.py`）、权重 sha256 校验、`pip install flash-linear-attention` | 10–15 min | 失败即停并报缺什么 |
| 1 | 9B 可行性验证（3 题） | 5 min | >30 s/题 → 跳过 9B，继续 S3 |
| 2 | S3 + Qwen3-VL-8B 全量（5+2+29 题） | ~10 min | OOM → 停该模型 |
| 3 | 9B S0/S1/S2 全量（3 × 1,033） | 1.7–2.5 h | 失败率 >5% → 停 |
| 4 | 收尾：落盘、sha256、`final_receipt.json`、关机 | 10 min | 剩 600 s 强制收尾 |

**顺序理由**：先做便宜的 S3（10 分钟）确保至少有一项增量落地，再投入 9B 的长跑。

## 5. 产物与收货口径

| 产物 | 路径 | 必含 |
|---|---|---|
| S3-8B 三份 csv | `reports/paper_20261026/s3_qwen3vl_8b_{dev,holdout,frozen}.csv` | `raw_id,qid,choice,gold,correct,status` |
| S3-8B 回执 | 同上目录 `receipt_s3_qwen3vl_8b.json` | 模型 revision、dtype、量化、`max_new_tokens`、题单 sha256、输入 sha256、csv sha256、GPU 名与显存、失败计数 |
| 9B 三份 csv | `reports/paper_20261026/s0s1s2_qwen35_9b_{S0,S1,S2}.csv` | 同上列名 |
| 9B 回执 | `reports/paper_20261026/receipt_qwen35_9b.json` | 上列 + `nvcc` 版本、torch/triton/fla/causal_conv1d 版本、`chat_template_sha256`、单题耗时分布、可行性验证结果 |
| 汇总收货单 | `reports/paper_20261026/final_receipt_20261026.json` | 两实验的 rc、逐文件 sha256 与字节数、每件"完整/不完整"判定 |

**不推**：模型权重、原始图像、私有归档。**不改**：`frozen_numbers.json`、既有 S3 四模型 csv、`a-side/**`。

## 6. 区间与措辞约束（沿用主实验）

- 不使用"证明""因果""数量无关""等价"；"显著"只有附对应检验才可用，本文件不设检验，故不使用。
- 跨零一律写"无法与无差异区分 / cannot exclude no difference"。
- 测得比例不写成模型常数，不外推。
- 所有表在表注写明：题分母、证据张数、区间单位（如报告区间）。
- S3 表必须写明"AI 图像辅助、label-aware、非人工盲审"。
- 9B 表必须写明"与五模型不同模型家族，不可作纯规模趋势"。

## 7. 硬件与镜像建议（供租用参考）

| 需求 | 规格 | 说明 |
|---|---|---|
| 显存 | **≥ 32 GB，首选 40–48 GB** | 48 GB 一张卡覆盖两项 |
| 算力 | compute capability ≥ 8.0 | 原生 bf16；**排除 V100** |
| 镜像 | **CUDA 12.8 devel**（含 `nvcc`），torch 2.8.0+cu128 | runtime 镜像无 nvcc，`causal_conv1d` 编不了 |
| 候选卡 | L40S 48GB / RTX A6000 48GB / A100 40GB / RTX 5090 32GB（偏紧） | 价格以平台实时报价为准 |

## 8. 2026-10-28 执行前实现核对（尚未推理）

题单、阈值、生成参数与判据均不变。本次在 `de6f979` 基线上修正执行器：可行性按三个单题的端到端耗时分别判断（不得用生成耗时均值替代）；异常请求计入尝试数并立即检查 >5% 与 OOM；解析失败计错；每题 CSV/原始输出立即落盘；三组覆盖完整才标完整。环境门禁要求实际导入成功（包括 causal_conv1d），并检查指定 torch/CUDA、transformers、原生 BF16 与 ≥32 GiB。

图像预处理以本文件 §1 引用的 `b-side/configs/protocol_main_v1.json` 为准：Qwen 的 `min_pixels=50176,max_pixels=262144,use_fast=false`，与已提交主协议一致。原补跑脚本遗漏传入这组参数，现恢复；不采用模型默认预算替代，亦不为适配显存进一步降低、缩图或重排。实际 processor 配置写入回执。

按用户本轮授权增加服务器内的独立后台控制与关机：从控制器启动起设 4 小时运行上限，剩 600 秒停止新请求；等待安装完成最多 30 分钟。单项受阻先保留原因，另一项具备条件则继续。所有执行结束或受阻后，持久盘保存原始记录、回执、日志与代码，打包并验证成员哈希，再关闭本实例；不依赖 Mac 在线。另设独立守护处理控制器意外退出。此处为运行保护，不新增效果判据，不重跑不利结果。

## 9. 2026-10-28 固定预热后的独立验证（执行前修订）

用户在获知“首题在 Triton 自动调优时触及 30 秒门槛；预热后重测须补充预注册”后，授权继续实验。本节在任何预热推理前提交，作为独立的 warmed 验证，**不追溯更改冷启动判定**。

- **原结果保留**：`/root/autodl-tmp/completion-9b-20261028b/9b/receipt_feasibility.json`，首题 `mragb:6` 为 `30.051801569759846 s`，验证未通过、rc=5；堆栈位于 Triton 自动调优阶段。不将该项写成通过，不用后续读数覆盖它。
- **问题**：固定预热后，Qwen3.5-9B 能否满足原先的三题逐题端到端 ≤30 秒门槛，并完整生成 S0/S1/S2 各 1,033 条？该检验仅说明此环境下的运行可行性，不产生冷启动延迟或部署成本结论。
- **题单/预热**：主输入保持原 frozen_test 1,033 题，排序题号哈希仍为 `2a102ea80297f371dbe793125ac98c084880168929cf8a0781aac315c485d9bc`。固定采用 S0 原序前三题 `mragb:6,mragb:11,mragb:12`；顺序题号逐个加换行后的 SHA256 为 `d559035171831d8e12efdc641dd4782c6ec40f060e0d53774775bf4c3192fc42`。三题各预热一次，**恰好三次，不追加、不换题、不按正确率或速度筛选**；每次预热上限 600 秒，单独保存原始输出、时间和状态，不计入正式准确率或三题计时门槛。
- **指标/判定**：同一模型加载与同一进程中，预热完成后，原三题各正式计时一次；三个请求均成功且分别 ≤30 秒才通过，不能用均值替代。任一超时即未通过，不再重试。只有该 warmed 门槛通过才执行正式 S0/S1/S2 各 1,033 题；正式准确率仅由该次全量记录计算。冷启动与 warmed 结果分别报告，不混为一个判定。
- **参数/环境**：模型 revision、图像顺序、原协议像素预算、bf16、greedy、seed=42、64-token 上限、原生 EOS、`enable_thinking=False` 与原注册一致。环境固定 torch 2.8.0+cu128、Triton 3.4.0、transformers 5.19.0、flash-linear-attention/fla-core 0.4.2、causal-conv1d 1.7.0；逐项记入回执，不回退参考实现、不量化。
- **停止/保存**：预热、正式计时、全量分别统计累计技术失败率，任一阶段严格 >5% 或 OOM 即停；解析失败仍计错并保留分母。全流程计算上限 4 小时，剩 600 秒不再发新请求并保存 partial；该保护只停止计算。**用户已撤回自动关机授权，任何结果、错误或超时均保持实例开机**。已完成 S3 不重跑。所有新记录写入独立 `completion-9b-warmed-20261028` 目录，结果无论正负全部保留，不覆盖冷启动或冻结数字。


## 10. 执行结果回填（2026-10-28；不修改以上题单、阈值或判据）

执行前的完整登记字节另存为 [`PREREGISTRATION_registered_46c8fd5.md`](../paper_20261026/PREREGISTRATION_registered_46c8fd5.md)，SHA256 `2b6262f1e3a658d3aeec5e22ad5eccdcb7f491ec4f4231fbbe5e1f5fe6629d96`，与 warmed 运行回执的登记哈希相同。当前文件只追加本节；原冷启动门槛未被追溯改写。

| 项目 | 完整性与返回码 | 结果与来源 |
|---|---|---|
| S3 + Qwen3-VL-8B | 5/2/29 均完整；36 次尝试，技术失败 0，rc=0 | dev 1/5、holdout 1/2、frozen 11/29；`../paper_20261026/receipt_s3_qwen3vl_8b.json` |
| 9B 原冷启动验证 | 未通过；首题超时，rc=5，未进入该轮全量 | 30.051801569759846 s；`../paper_20261026/receipt_feasibility_cold.json` |
| 9B 独立 warmed 验证 | 固定三次预热后，三个正式计时均 ≤30 s | 0.3445344418287277 / 0.31748734787106514 / 0.3069864548742771 s；`../paper_20261026/receipt_warmed_feasibility.json` |
| 9B warmed 全量 | S0/S1/S2 各 1,033；3,099 次尝试，技术失败 0，rc=0 | 正确数 606 / 618 / 720；`../paper_20261026/receipt_qwen35_9b.json` |

未追加 S2@3、区间或其他 GPU 实验；9B 不并入 956 题的 A 分析。S3 与 S1 的同题转换，以及 9B 的共享命中条件读数，仅离线复算点估计，见 `../paper_20261026/completion_numbers_20261028.json`。运行期间遵守撤回自动关机的授权；用户随后明确要求完整性核查通过后关机，已完成远端逐题与本地归档核对后执行手动关机。
