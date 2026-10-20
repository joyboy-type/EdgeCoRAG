# 给 B 的任务单（2026-10-20，rev2）

发布：2026-10-20。**本批没有新的 GPU 授权**：不租卡、不启动模型推理、不改历史结果。
A 侧交付在独立分支 `a-side/next-stage-20261017`，本轮标签 **`a-iface-20261021-fix2`**，**未并入 `results/runtime-v1.10.1-delivery`**（不要等它进结果分支）。

> rev2 更正（2026-10-20 晚）：上一版写"36 个产物自校验 0 失败"**只在 A 的 Windows CRLF 工作树成立**。
> B 在干净检出上实测 `a17` 为 `rc=1 / fail_count=72`，原因是清单按 CRLF 记录哈希。
> 现已修复：`.gitattributes` 对该目录强制 `eol=lf`，`artifacts.json` 改按 **LF 字节**记哈希
> （`summary.hash_normalization = "LF"`），`a17` 比对前做 `\r\n→\n` 归一化，`--strict-lf` 可强制 LF。
> **产物内容与数值未变**；正确表述是"**干净检出上应 0 失败；若失败先查 manifest 行尾口径**"。

## 0. A 已交付（直接用，不要重做）

| 项 | 产物 |
|---|---|
| 排序差异定位 | `reports/next_stage_20261020/A_retrieval_consistency.md`（含 §7.1 先验判定表；根因**未确认**） |
| 冻结接口 v1 | `reports/next_stage_20261020/interface_freeze.md`；`retrieval_if_v1/`（36 个哈希绑定产物，LF 口径） |
| 索引回执契约 | `contracts/index_receipt.schema.json` + `index_receipt.example.json` + `scripts/a20_validate_index_receipt.py` |
| 选择准则 | `reports/next_stage_20261020/selection_policy.md`（含 P1–P4 最佳固定 RAG 规则与空占位表） |
| 成本接口 | `scripts/a12_cost_recorder.py` + `a13_cost_selftest.py`（32/32） |
| 跨栈复测 | `scripts/a18_batch_sensitivity.py` + 回执 schema |
| 逐题归因工具 | `scripts/a21_attribute_exclusion.py`、`a23_fix_manifest_line_endings.py`、`a22_crlf_guard_test.py` |
| utility-mrag 可行性 | `reports/next_stage_20261020/A9_utility_mrag_feasibility.md` |

## 1. 先读

1. `reports/next_stage_20261020/A_return_20261020.md`（依赖清单总览）
2. `reports/next_stage_20261020/interface_freeze.md`（冻结口径，唯一权威）
3. `contracts/index_receipt.schema.json`（你要填的回执字段）

## 2. 你要做的 7 件事

### B1 校验接口产物（先做，30 分钟）

```bash
git fetch origin a-side/next-stage-20261017 && git checkout FETCH_HEAD   # 或独立 worktree
python a-side/scripts/a17_verify_interface.py
#   期望：artifacts_checked=36、fail_count=0、rc=0
#   若失败：先看 verify.json 的 files_with_crlf；非 0 说明你的检出是 CRLF，见下方说明

python a-side/scripts/a17_verify_interface.py --strict-lf
#   期望（Linux/macOS）：rc=0；若是 Windows 且用了 autocrlf，这里会故意失败并给修复提示

export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1
python a-side/scripts/a06_build_corpus.py --store "$EDGECORAG_CORPUS" --verify
#   期望：content_digest = 31ade7b7e2454d0b9fcd58568247dd2a6862e15273fdd65e1d12ed50e373264e、mismatches=0

python a-side/scripts/a15_materialize_packets.py --cohort smoke_20 --dim 768 --strategy cosine \
    --corpus "$EDGECORAG_CORPUS" --out "$HOME/edgecorag/packets/smoke20_768_cosine"
#   期望：verify.json 的 mismatch = 0（不要改脚本，--corpus 已支持）
```

**行尾口径说明**：`a-side/retrieval_if_v1/**` 的哈希按 LF 字节计算（与 git 提交内容一致）。
若你在 Windows 上看到 CRLF：
`git config core.autocrlf false` 后重新检出，或 `git rm --cached -r . && git reset --hard`
让 `.gitattributes` 的 `eol=lf` 生效——**产物内容不需要改**。

### B2 索引构建回执（A7，解释 18,955 的唯一入口）

按 `contracts/index_receipt.schema.json` 填 `contracts/index_receipt.example.json` 的副本，
**未回传字段保持 `null`，不要填 0 或猜值**，然后：

```bash
python a-side/scripts/a20_validate_index_receipt.py <你的回执>.json    # 必须 errors=[]
```

必填：条目数、身份口径（原始字节 / q95 重编码）、是否内容去重、行序规则、dtype、
归一化层、语料编码 batch、`sources[]` 每条 sha256。
参考：A 侧公开口径 `1,353` 题 / `14,475` 个图像实例 / `4,712` 个唯一内容；smoke 报告写 `18,955`。
三种假设下你应该给出的特征值见 `reports/next_stage_20261020/index_receipt_adjudication.md`（**A 不下结论**）。

### B3 那 5 题的对齐数据（`mragb:10/1049/1051/1062/1117`）

1. 历史与现场**各 10 行**：`qid,source(history|live),rank,sha256,score`
2. 现场查询向量指纹：`sha256(float32 序列化后的向量字节)`（有历史指纹一并给）
3. 编码参数：dtype、`Normalize` 是否启用、现场 batch 组成（是否每题单飞）

A 收到后用 `scripts/a21_attribute_exclusion.py` 逐题归因（dtype / 归一化位置 / 解码路径 / 批大小 / **数据不足**），
每类都带"看到什么数值才成立"的条件；**不做事后讲故事**。

### B4 固定 CPU 线程

`libgomp: Invalid value for environment variable OMP_NUM_THREADS` 出现 2 次，必须固定，
并把**实际生效值**写进计时回执 `hardware.cpu_thread_env`。
该字段现在**构造即强制**：只接受正整数或 `"unfixed"`；`"auto"`/空串/`0`/负值/缺失直接抛 `ProvenanceError`。
给 `"unfixed"` 也能跑，但每条记录会被标"只作技术联调、不得进正式基准"。保留原日志，不悄悄重跑。

### B5 修回执里的悬空引用

`provenance/results_20261020/e2e_smoke_public_receipt.json` 的 `source_pins` 指向
`a-side/scripts/evidence_selection.py` 与 `a-side/scripts/independent_retrieval.py`，
这两个文件**在任何分支都不存在**。补齐源码或改指向真实文件（含 sha256），否则该回执不可复算。

### B6 跨栈回执（a18）

A 的 `0/1203` 只在 A 的栈（torch 2.11.0 / tv 0.26.0 / Pillow 12.3.0 / numpy 2.5.2）测过；
你的服务器是 torch 2.8.0 / tv 0.23.0 / Pillow 11.3.0。用你的环境跑一次：

```bash
python a-side/scripts/a18_batch_sensitivity.py --schema        # 先看回执字段
python a-side/scripts/a18_batch_sensitivity.py --self-check    # 纯逻辑，不需要模型
python a-side/scripts/a18_batch_sensitivity.py \
    --qids-file a-side/splits/smoke_20.v2.txt --dtype fp32 --batches 16,1 \
    --weights-sha256 <model.safetensors 的 sha256> --out receipt_a18_<你的栈>.json
```

**判定阈值（写死）**：只有 `changed_order == 0 且 changed_set == 0` 才能宣称"跨栈一致"
（`verdict=stack_invariant`）；否则必须写 **"A 栈的 0/1203 不能外推"**，并列出改序题号与该题
top10 的最大分差，再给"统一到哪一栈"的建议；`changed_top3 != 0` 时还要说明选中的 3 张是否改变。
若本批不上 GPU，把这一项标"待批准"并说明需要多少分钟。

### B7 utility 分数回传格式

`qid,sha256,score` 三列，每题 10 行、覆盖候选池全部 sha、不许多列、不许改 sha。
**选 top3、并列按 sha 升序、slot 顺序、物化全部由 A 的 `a15 --strategy utility --scores` 完成**，
你不要自己挑 3 张。

## 3. 回传清单

| # | 内容 | 格式 |
|---|---|---|
| 1 | `a17` 校验结果（含 `fail_count`、`files_with_crlf`） | 终端输出或 `verify.json` |
| 2 | 语料重建校验 | `content_digest` + `mismatches` |
| 3 | 索引构建回执 | 见 B2 |
| 4 | 5 题 × 2 份 10 行 | CSV |
| 5 | 查询向量指纹 + 编码参数 | JSON |
| 6 | `OMP_NUM_THREADS` 生效值 | 字符串 |
| 7 | `source_pins` 修正 | commit |
| 8 | `a18` 跨栈回执 | JSON（`a18_batch_sensitivity_receipt/v1`） |
| 9 | 对接口的异议/缺字段 | 文字（冻结前最后一次改口径机会） |

## 4. 不要做

- 不重算候选池；不重新排序（83.35% 的题 top10 最小相邻分差 <1e-3，128 维 94.97%）。
- 不用 `frozen_test` 选维度、阈值或策略；已观察数据复核不写成"新盲测"。
- 不把 Oracle 上界（+20.6 pp）写成"路由器可达收益"；不与 S2 的 GT 证据 Oracle 混称。
- 不把 S1（官方候选 top3）改称"自主检索"。
- 不改 `a-side/**`（改 A 的脚本会改哈希）；不改 v1.10.1 的 prompt / 64 token / 严格评分 / BF16 / split。
- 不扩大 holdout 评测（A 产物里 `internal_holdout` 为空是有意的）。
- 不 `reset` / `clean` / `force push`；原题、图片、完整原始响应、权重、私有归档不上传。

## 5. GPU 门槛

B1/B2/B3/B4/B6 完成、接口异议关闭后，再一起提最小对照范围：
`smoke_20` 四路径各 1 次 → `dev_150` 四维度选择 → `frozen_test` 只跑选定维度一次。
量级估算（**非实测**）：约 9,464 次生成 + 11,830 次 utility 前向 ≈ 5 h GPU，按 1.48 元/时约 7.4 元；
须附费用上限、硬停机时间、保全方案与停止条件。

B-03（MMDocRAG 许可）、B-04（统计边界）、T15 仍归你，与本批并行推进。
