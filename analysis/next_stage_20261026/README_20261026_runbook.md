# 补跑运行手册（S3-8B + Qwen3.5-9B，2026-10-26）

> 2026-10-28 收货更新：S3-8B 与 9B 已完成，见 [补跑结果与离线复算](../../reports/paper_20261026/COMPLETION_RESULTS_20261028.md)。
> 以下原命令保留为历史运行说明，不应直接重跑已完成任务。9B 冷启动判据未通过；§9 前瞻登记固定预热后的独立验证，`nine_b_warmed.py` 在同进程完成固定预热→三题计时→全量，不自动关机。
> 本轮实际依赖已固定为 flash-linear-attention/fla-core 0.4.2 与 causal-conv1d 1.7.0；不能重新安装不带版本的最新版 FLA。
> `completion_controller.py` 是早期历史编排器，含关机逻辑；本轮 warmed 入口没有启动它或关机守护。用户最终在完整性核查后另行授权手动关机。


配对文档：`PREREGISTRATION_20261026_completion.md`（判据与停止规则以它为准）。

## 一、租卡与镜像

| 项 | 要求 | 不满足的后果 |
|---|---|---|
| 显存 | **≥ 32 GB，首选 40–48 GB** | 8B+4 图已实测 23.4 GB 峰值；24 GB 必 OOM |
| 算力 | compute capability ≥ 8.0（原生 bf16） | V100（7.0）不可用 |
| 镜像 | **CUDA 12.8 devel（含 `nvcc`）** | runtime 镜像无 nvcc → `causal_conv1d` 编不了 → 9B 单题 >10 分钟 |
| torch | 2.8.0+cu128 | 与既有正式记录一致 |
| transformers | ≥ 5.19（含 `Qwen3_5ForConditionalGeneration`） | 4.57.3 无该类，9B 加载失败 |

候选卡：L40S 48GB / RTX A6000 48GB / A100 40GB / RTX 5090 32GB（偏紧）。价格以平台实时报价为准。

## 二、环境准备（一次性）

```bash
# 1) 核验（不装任何东西，只报告）
python env_check.py --json /root/autodl-tmp/env_check_20261026.json
#    rc=3 表示两项都不具备条件；按输出里“缺什么”逐项补

# 2) 线性注意力：先只装 fla（Triton JIT，不需要 nvcc）
pip install flash-linear-attention==0.4.2 fla-core==0.4.2

# 3) causal_conv1d：优先预编译 wheel，失败再源码编译
pip install causal-conv1d==1.7.0 || \
  TORCH_CUDA_ARCH_LIST=8.9 pip install causal-conv1d==1.7.0 --no-build-isolation
#   TORCH_CUDA_ARCH_LIST 按卡算力：4090/L40S=8.9, A6000=8.6, A100=8.0

# 4) 再核验一次，确认 nvcc_matches_torch_cuda / fla_present / nine_b_ready 均为 OK
python env_check.py
```

**不要做**：量化、降 dtype、限制 `max_pixels`、缩图、改 prompt。任一都会破坏"同精度/同预处理可比"前提。

## 三、权重

`env_check.py` 会打印 `权重 qwen3vl_8b / qwen35_9b` 的片数与路径。

- **续租原实例**：`/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/` 下应已存在，直接可用。
- **新实例**：需重新下载（服务器直连 huggingface.co 不通，必须用镜像）：

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/EdgeCoRAG/cache/huggingface
python - <<'PY'
from huggingface_hub import snapshot_download
for repo, rev in [("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
                  ("Qwen/Qwen3.5-9B", "c202236235762e1c871ad0ccb60c8ee5ba337b9a")]:
    p = snapshot_download(repo, revision=rev, local_dir=f"{__import__('os').environ['HF_HOME']}/hub/models--" + repo.replace("/", "--"),
                          allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors", "merges.txt", "vocab.json"])
    print("DONE", repo, p)
PY
```

体积：8B ≈ 17.5 GB、9B ≈ 19.3 GB；经 hf-mirror 约 30–50 分钟。

## 四、执行顺序（一次开机）

```bash
OUT=/root/autodl-tmp/run_20261026

# 0) 环境 + 权重
python env_check.py

# 1) 9B 可行性验证（只跑 3 题）—— 超过 30 秒/题就跳过 9B
python nine_b.py --mode feasibility --out $OUT/9b
#   rc=0 → 通过；rc=5 → 未通过，跳过第 3 步，只做第 2 步

# 2) S3 + Qwen3-VL-8B（约 10 分钟，29+2+5 题）
python s3_qwen8b.py --out $OUT/s3

# 3) 9B 全量（S0/S1/S2 × 1,033，约 1.7–2.5 小时）
python nine_b.py --mode full --out $OUT/9b

# 4) 收尾：落盘 + sha256 + 关机
```

## 五、产物与判读

| 文件 | 位置 |
|---|---|
| `s3_qwen3vl_8b_{dev,holdout,frozen}.csv` | `$OUT/s3/` |
| `receipt_s3_qwen3vl_8b.json` | `$OUT/s3/` |
| `s0s1s2_qwen35_9b_{S0,S1,S2}.csv` | `$OUT/9b/` |
| `receipt_qwen35_9b.json`、`receipt_feasibility.json` | `$OUT/9b/` |

判读：
- `csv` 列名与既有四模型 S3 / 五模型主表完全一致，可直接并入同一张表。
- 每份回执里 `complete` 字段为 `true` 才算"可并入"；否则标"不可判定"，不用成功子集替代。
- `stopped_reason` 非空时**必须原样写进报告**，不得删。

## 六、补齐后能改与不能改的论文表述

| 补齐项 | 可改 | 仍不可写 |
|---|---|---|
| S3-8B | "S3 四模型" → "S3 五模型" | 跨尺度鲁棒性结论（29 题、AI 辅助、非盲审） |
| 9B | 主表扩到六模型；B 节多一模型读数 | 纯规模趋势（Qwen3.5 ≠ Qwen3-VL 家族） |

细节见 `PREREGISTRATION_20261026_completion.md` §5–§6。
