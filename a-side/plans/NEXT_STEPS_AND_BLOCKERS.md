# 未完成事项与阻塞清单（交接给下一个接手者）

> **目的**：让接手的 AI/人能在不重复已做工作的前提下继续。
> 本文件如实区分**已完成**、**部分完成**、**未开始**、**被阻塞**四类。
> 编写时间：2026-10-15。对应提交：见仓库 `a-side/` 与 `handover/` 最新版本。

---

## 0. 一句话现状

**检索侧的环境、工具链、数据版本、接口契约、样例验收已完成；
科学实验（检索质量指标、四路径对照、S3）一件都还没做。**
真正的阻塞是**独立语料未验证可下载且许可未确认**。

---

## 1. ✅ 已完成（有实测证据，可直接复用，不要重做）

| 项 | 证据位置 |
|---|---|
| 双 venv 环境（CUDA torch，transformers 4.x/5.x 隔离） | `a-side/reports/requirements-*.lock.txt` |
| 作者代码单元测试 **23/23 通过** | `pytest third_party/utility-mrag/tests` |
| EmbeddingGemma 2 检索**接口**可用（BF16、0.83 GiB、63.5 ms/query） | `a-side/scripts/smoke_embedding.py` |
| 维度截断 128/256/512/768 + 重新归一化 | 同上 |
| **Gemma 4 True/False logit 打分链路打通** | `a-side/scripts/probe_gemma4_logits.py` |
| 数据集版本锁定 + revision | `43620fde4044bb150e158c67ad7af6b6b11e1da2` |
| **GT 精确匹配命中率** 55.9% / rank-0 32.6% / 全覆盖 2.3% | `a-side/scripts/audit_gt_match_rate.py` |
| 哈希口径可靠性验证（原始字节不可得，JPEG95 重编码确定性） | `verify_hash_reliability.py`、`test_hash_stability.py` |
| 官方评测代码 4 处缺陷 | `handover/contracts/官方评测接口差异.md` |
| 体积口径核清（parquet 4.00 GiB） | `a-side/scripts/reconcile_dataset_size.py` |
| 6 题接口样例（含 GT，S2 可跑）**28/28 验收通过** | `handover/samples/`、`verify_handover_sample.py` |
| 题目分层切分 + 固定种子 `20261015` | `a-side/scripts/make_split.py`、`a-side/splits/` |
| 接口契约（两个 JSON Schema + 对齐说明） | `handover/contracts/` |

**不要重复做的事**：不要重跑环境检查、不要重下数据集、不要重算命中率
（除非数据集 revision 变了）、不要重建样例包。

---

## 2. ⏳ 部分完成（有基础但不够用）

| 项 | 现状 | 缺什么 |
|---|---|---|
| 检索质量评估 | 只验证了**接口可调用** | ❌ **R@1/R@5/MRR 一个都没算**；需在真实 MRAG-Bench 数据上跑 |
| 20 题联调清单 | 切分规则与 `smoke_20.txt` 已定 | ❌ 未生成**含真实图片与哈希**的冻结版清单 |
| S3 干扰证据 | 规范、三层校验、类型设计已定 | ❌ 未挖掘任何候选、未做语义抽查 |
| 检索器对照 | 未开始 | ❌ 与 CLIP/SigLIP 的对照未做 |

---

## 3. ❌ 未开始

1. **冻结证据列表（全量 1,353 题）** —— `evidence_list.jsonl` 不存在。
2. **独立重检索** —— 未开始（被 §4 阻塞）。
3. **Gemma 4 版效用选择器** —— 需要改写
   `third_party/utility-mrag/utility_mrag/models/gemma.py`
   （当前硬编码 `Gemma3ForConditionalGeneration`，Gemma 4 是 `Gemma4ForConditionalGeneration`）。
4. **S3-pure 干扰集 v1**。
5. **四路径对照（A0/A1/A2/A3）** —— 属 B 侧主责，但 A 侧需先给冻结证据。

---

## 4. ⛔ 阻塞（必须先解决才能继续）

### 阻塞 1：独立检索语料未验证（**最高优先级**）

| 项 | 状态 |
|---|---|
| 语料位置 | 官方 README 给出 Google Drive 链接：`https://drive.google.com/file/d/1atwkNXH3aEtCLuqimZoB1Mifj5CwL3CL/view` |
| **能否下载** | ❌ **未验证**（从未尝试） |
| **许可** | ❌ **未确认**（语料由上游数据集汇编，需逐个核对上游许可） |
| 规模 | 未知 |

**下一步动作**：
1. 先尝试下载该语料，记录文件数/总字节/内容哈希；
2. 若无法下载（Google Drive 需代理/配额限制），**如实报告，不要假装完成**；
3. 核对许可：数据集本体是 CC-BY-4.0，但**语料是单独发布的压缩包**，许可需单独确认，
   且其中各上游图片（Imagenet、COCO 等）许可不同。
4. **在许可确认前，重检索结果不得对外发布。**

> 注意：本机 `huggingface.co` DNS 被污染、`github.com` 被本地代理拦截，
> Google Drive 大概率也需要处理网络问题。见 `a-side/setup/MACHINE_SPECIFIC_PROXY.md`。

### 阻塞 2：E4B 在 8 GB 显存不可行（影响实验设计）

实测 4bit 加载即占 **8.685 GiB > 8.0 GiB** 总额，生成 2 步从 E2B 的 1.0 s 恶化到 **23.0 s**。
根因：**4bit 量化不覆盖 `lm_head`**（0.671 B 参数以 bf16 存储 ≈ 1.34 GiB）。

**影响**：四路径对照中的 **A2/A3（E4B 直接 / 检索+E4B）在本机无法以可比时延复现**。

**可选对策（需与 B 协商，A 侧不能单方面决定）**：
- B 侧若使用更大显存的机器，则 A2/A3 由 B 侧跑，A 侧只报相对耗时；
- 或改用受控 CPU offload 并**如实记录时延代价**；
- 或降低输入分辨率、限制 `max_new_tokens` 以压缩视觉 token 与 KV cache。

### 阻塞 3：与 B 的 8 项确认未回

见 `handover/docs/05_给B的确认与续作提示词.md`。其中 **split 方案**与
**S3 首版范围**会阻塞后续工作。

---

## 5. 🔧 接手时的环境准备（避免重复踩坑）

本机（Windows）有几个已解决但容易被重新踩到的坑：

| 坑 | 解决方式 | 参考 |
|---|---|---|
| `github.com` 被 Watt Toolkit 本地拦截，`git` 报 `CRYPT_E_NO_REVOCATION_CHECK` | 临时用 `-c http.sslVerify=false`，**但这不是标准做法** | `a-side/setup/MACHINE_SPECIFIC_PROXY.md` |
| 该代理会造成 **GitHub API 假 404** | 用已知存在的公开仓库做对照判断 | `a-side/scripts/verify_github_api_authenticity.py` |
| HTTPS 到 GitHub **间歇性失败** | 复用已有工作副本 + 退避重试，**不要每轮删除重建** | `a-side/scripts/publish_to_repo.py` |
| `huggingface.co` DNS 被污染 | 设 `HF_ENDPOINT=https://hf-mirror.com` | `a-side/scripts/project_config.py` |
| `download.pytorch.org` **下载完全停滞** | 用 SJTU 镜像（实测 13.31 MB/s） | `a-side/scripts/probe_mirrors.py` |
| PowerShell 5.1 读中文文件乱码 | 用 `read` 工具或 `-Encoding UTF8`；**不支持 heredoc** | — |
| 重资源占工作区 35 GiB | 已外置到 `EDGECORAG_STORE`（junction 链回） | `a-side/scripts/bootstrap_store.py` |

**解释器位置**（已配好，直接用）：
```
.venv-main/Scripts/python.exe    # transformers 5.x：EmbeddingGemma 2 / Gemma 4
.venv-mrag/Scripts/python.exe    # transformers 4.x：作者代码
```
系统 Python 里的是 **CPU-only torch**，**不要用**。

---

## 6. 🚫 已知的表述陷阱（接手者必须避免）

这些是 A 侧**自己犯过并已修正**的错误，很容易重犯：

| ❌ 不要写 | ✅ 应写 | 原因 |
|---|---|---|
| 「官方候选池泄漏答案（55.9%）」 | 「**GT 图像字节级精确匹配命中率 55.9%**」 | 无法区分正常检索命中与使用标注生成；官方候选产生过程未说明 |
| 「所以自研重检索是干净基线」 | 「另一条件，同样需实测命中率」 | 低命中率≠干净；命中率低也可能只是检索器弱 |
| 「哈希不重叠即证明无正确证据」 | 「只证明没有相同字节；需近重复+语义抽查」 | 同类不同实例图不会被 dHash 判近重复，却是主要干扰源 |
| 「`heldout_external`（外部验证）」 | 「`internal_holdout`（内部留出）」 | 同源同分布，**不是**外部验证；外部验证须用 VisDoM/MMDocRAG |
| 「图片保留原始字节」 | 「JPEG95 重编码产物」 | 实测 `im.fp` 为 None，原始字节取不到 |
| 「关掉 TLS 校验是克隆方式」 | 「本机代理所致，标准做法不带该参数」 | 不应把降级安全当通用方案 |
| 「第一个 token 的 True/False logit」 | 同（这条是对的） | 已验证 Gemma 4 两者均为单 token |

---

## 7. 建议的接手顺序

```
1. 读 handover/README.md 与 handover/docs/01、03、official_pool_provenance.md
2. 跑 python a-side/scripts/verify_handover_sample.py   # 确认拿到的是完整包(应 28/28)
3. 尝试下载官方检索语料 -> 报告可下载性与许可            # ← 关键路径
4. 若语料可用: 建索引 -> 重检索 -> 用 audit_gt_match_rate.py 口径报告命中率
5. 生成全量冻结证据列表（按 evidence_list.schema.json）
6. 改写 gemma.py 支持 Gemma 4 -> 跑通效用选择器
7. 等 B 确认 split 与 S3 范围 -> 生成 20 题冻结清单 / S3-pure
```

**第 3 步是真正的瓶颈**：如果语料拿不到，第 4–5 步都做不了，
届时应转而在报告中明确「重检索路线受阻」，并考虑是否改用
「只用官方候选池 + 显式报告其命中率」作为唯一的 S1 条件。

---

## 8. 数据与代码版本锚点

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench` @ `43620fde4044bb150e158c67ad7af6b6b11e1da2`（CC-BY-4.0） |
| 官方评测代码 | `mragbench/MRAG-Bench` @ `4ae2241fdc5a` |
| 作者代码 utility-mrag | `Hcnaeg/utility-mrag` @ `d5b9e573ece6`（MIT，分支 **master**） |
| 作者代码 RAGRouter | `OwwO99/RAGRouter` @ `808fef756844` |
| 作者代码 VQQP_Bench | `phycholosogy/VQQP_Bench` @ `5099a82130c4` |
| EmbeddingGemma 2 | `google/embeddinggemma-2` @ `914f7f89142e33e7` |
| 切分种子 | `20261015` |
| 本机硬件 | RTX 4060 Laptop **8 GB**（跨机器耗时不具可加性） |

详见 `a-side/data/source_manifest.csv`。
