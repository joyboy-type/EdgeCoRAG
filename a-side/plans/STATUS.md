# A 侧成果索引（已完成什么、在哪、怎么用）

> 本页是**导航页**。远端 `main` 已包含全部已完成内容；
> 未完成事项见 [`NEXT_STEPS_AND_BLOCKERS.md`](NEXT_STEPS_AND_BLOCKERS.md)，
> 待总部决策见 [`DECISIONS_NEEDED.md`](DECISIONS_NEEDED.md)。

**核对基线**：`41aa349694df526afb987083fa6a209fbe45b174`

---

## 0. 三分钟上手（B 侧）

```bash
git clone https://github.com/joyboy-type/EdgeCoRAG.git
cd EdgeCoRAG

# 1) 读接口约定与证据规则
#    handover/contracts/接口对齐_A侧确认.md
#    handover/docs/03_证据规则.md

# 2) 用 6 题接口样例打通程序（含图片，无需额外下载）
python -m pip install pillow
python -c "import json,pathlib; ..."   # 见 handover/README.md 的示例代码

# 3) 校验你拿到的包是否完整（应输出 29/29 通过）
python a-side/scripts/verify_handover_sample.py
```

**注意事项（务必先读）**：
- `scoring_only` 区**只用于评分**，绝不进入证据选择或 prompt；
- `evidence_order` 中 `used_in_prompt=false` 的条目（Incomplete 截断候选）**不要送入模型**；
- 官方提示模板的图片占位符数量**写死**（常规 6、Incomplete 2），改 top-k 必须同步改；
- `status != "ok"` 的题**不得丢弃**，计入固定题单分母。

---

## 1. 给 B 的交接包 `handover/`

| 文件 | 内容 |
|---|---|
| `README.md` | 交接包入口 + 可复制的使用代码 + 四条纪律 |
| `docs/01_检索侧分工与进度.md` | 回答 B 的 5 个问题、Incomplete 规则意见 |
| `docs/03_证据规则.md` | 三集合区分、**命中率的准确定义**、ID 映射、近重复方法 |
| `docs/04_S3干扰证据规范.md` | S3 构造 + **三层校验**（字节哈希/近重复/语义三态） |
| `docs/05_给B的确认与续作提示词.md` | **可直接整段复制给 B** 的提示词 |
| `docs/official_pool_provenance.md` | ⚠️ **已核实 9 项 / 未确认 6 项**，避免把命中率误读为"泄漏" |
| `contracts/evidence_list.schema.json` | 检索侧→B 侧的证据清单契约 |
| `contracts/result_row.schema.json` | B 侧→分析的逐题结果契约 |
| `contracts/接口对齐_A侧确认.md` | 与 B 的 `strict_choice_v1` 对齐，**不另写第二套评分器** |
| `contracts/官方评测接口差异.md` | 官方代码 **4 处缺陷**（含会崩溃的类型错误） |
| `samples/` | **6 题接口样例**（含图片，S2 可跑） |
| `samples/验收说明.md` | 样例的版本、路径根目录、编码说明、验证输出 |
| `freeze/冻结清单模板.md` | 正式实验前必须冻结的每一项 |

## 2. A 侧可复现资产 `a-side/`

### 2.1 决策与状态（`a-side/plans/`）

| 文件 | 用途 |
|---|---|
| **`DECISIONS_NEEDED.md`** | ⭐ **4 项待总部决策 + 推荐方案 + 选项** |
| `VERIFICATION_SUMMARY.md` | 本轮所有验证的**实际运行结果** |
| `SPLIT_V2_CHANGES.md` | 切分 v2 修正了哪三处缺陷 + 实测证据 |
| `REVIEWED_IDS.md` | 已调试题与标签接触范围（**不得假设已穷尽**） |
| `NEXT_STEPS_AND_BLOCKERS.md` | 未完成事项、阻塞项、接手顺序、**表述陷阱** |
| `EXTERNAL_ARTIFACTS.json` | 外置材料清单（24.57 GiB）：获取方式/版本/大小/SHA-256 |

### 2.2 题单与切分（`a-side/splits/`）

| 文件 | 说明 |
|---|---|
| `split_manifest.v2.json` | **当前版本**：种子 `20261015`、规则、计数、哈希 |
| `smoke_20.v2.txt` / `dev.v2.txt` / `internal_holdout.v2.txt` / `frozen_test.v2.txt` | 四子集清单 |
| `reviewed_ids.txt` | 已调试题（支持 `#` 注释） |
| `entity_groups.json` | 实体连通分组（用于说明为何无法隔离） |
| `*.txt` / `split_manifest.json` | **v1 旧版，保留未删**（供对照回退） |

| 子集 | 题数 | 用途 |
|---|---|---|
| `smoke_20` | 20 | 打通接口 |
| `dev` | 150 | 调参（结果只能叫 dev） |
| `internal_holdout` | 150 | 内部留出（**不得称外部验证**） |
| `frozen_test` | 1033 | 最终评估 |

### 2.3 关键脚本（`a-side/scripts/`，38 个）

| 脚本 | 用途 |
|---|---|
| `verify_split.py` | **切分 18 项不变量**（互斥/覆盖/已调试题不泄漏/可重现） |
| `make_split.py` | 生成切分（`--dry-run` 不写文件、确定性） |
| `verify_handover_sample.py` | **证据包 37 项验收** |
| `build_evidence_package.py` | 按题单生成证据包 |
| `audit_gt_match_rate.py` | GT 精确匹配命中率 |
| `quantify_entity_connectivity.py` | 实体连通性量化 |
| `probe_corpus_access.py` | 语料可取得性探测 |
| `near_duplicate_check.py` | dHash 近重复 |
| `project_config.py` | 共享配置（**路径不绑定盘符**） |

### 2.4 实测数据（`a-side/data/`，14 个）

| 文件 | 关键数字 |
|---|---|
| `gt_match_rate_audit.json` | 任意 **55.9%** / rank-0 **32.6%** / 全覆盖 **2.3%**（分母 1353） |
| `entity_connectivity.json` | 跨题共享图片哈希 **2688**；仅精确重复即连成 **1338 题**一组 |
| `corpus_access.json` | Google 系域名**不可达** → 语料当前无法验证 |
| `vram_diagnosis_e4b.json` | E4B 4bit 加载即占 **8.685 GiB > 8.0** |
| `acceptance_report.json` | 证据包验收输出 |
| `smoke_20_file_hashes.csv` | smoke_20 包**逐文件** SHA-256（220 文件） |

---

## 3. 已完成 vs 未完成（**不合并表述**）

| 项 | 状态 |
|---|---|
| 环境与工具链（双 venv、CUDA torch） | ✅ 完成 |
| 作者代码单元测试 | ✅ 23/23 |
| EmbeddingGemma 2 检索**接口** | ✅ 完成（**R@1/R@5/MRR 未做**） |
| Gemma 4 True/False 打分链路（E2B） | ✅ 完成 |
| 数据集版本锁定与字段核验 | ✅ 完成 |
| 官方评测代码缺陷核验 | ✅ 4 处 |
| GT 精确匹配命中率 | ✅ 完成 |
| 实体连通性量化 | ✅ 完成 |
| 切分 v2（含缺陷修正与可重现） | ✅ 完成 |
| 6 题接口样例 | ✅ 29/29 通过 |
| **smoke_20 完整证据包** | ✅ 37/37 通过（**外置，不入库，可确定性重建**） |
| **S1** | 🟡 **部分**：smoke_20 范围可用；**正式题单待决策 2**；独立重检索**不可能**（语料不可达） |
| **S2** | 🟢 **可用**：GT 按真实数量落盘，映射完整 |
| **S3** | 🔴 **未开始**：仅规范与三层校验设计 |
| 检索质量指标 R@1/R@5/MRR | ❌ 未做 |
| 正式题单证据包 | ⛔ 阻塞于决策 2 |
| 端到端 GPU 性能 | ⛔ 需目标硬件，**不编造** |

---

## 4. 三个必须知道的实测结论

1. **官方候选池的 GT 精确匹配命中率为 55.9%** —— 这**不等于**"泄漏答案"。
   无法区分「检索器独立命中」与「候选生成使用 GT 标注」，官方候选的产生过程未说明。
   它**也不能**反推自研重检索是干净基线。详见 `handover/docs/official_pool_provenance.md`。

2. **图片级实体隔离在本数据集上不可行** —— 2688 个图片哈希跨题共享，
   仅精确重复就把 1338/1353 题连成一组；每题平均与约 9 道其它题共享图片。
   切分因此退化为逐题分配，并**如实声明"跨子集相关性未能隔离"**。

3. **Gemma 4 E4B 在 8 GB 显存不可行** —— 4bit 加载即占 8.685 GiB，
   生成 2 步从 E2B 的 1.0 s 恶化到 23.0 s。根因是 **4bit 不覆盖 `lm_head`**。

---

## 5. 需要动作的事项

| 谁 | 做什么 |
|---|---|
| **总部** | 确认 `DECISIONS_NEEDED.md` 的 **4 项决策**（其中**决策 2 是唯一硬阻塞**） |
| **B** | 确认 `handover/docs/05_给B的确认与续作提示词.md` 的 8 项；回传环境与字段清单 |
| **B** | 补充**完整**的已调试 `raw_id` 清单（当前只给了 7 个） |
| 能在 Google 环境者 | 重跑 `probe_corpus_access.py`，或向官方作者询问镜像 |
