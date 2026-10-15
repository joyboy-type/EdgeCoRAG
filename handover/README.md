# EdgeCoRAG-B 交接包

> 面向 **B 部分（多模型推理、同证据公平比较、统计与错误分析）** 的检索侧交付物。
> 所有事实在 2026-10-15 于本机对真实数据与官方源码实测核对。
> **未核对的项一律标注「未确认」，不写成结论。**

**基准提交**：本包内容对应共创仓库 commit `9ab299329bec65886dfb0fdd33da07ffbe337fad` 之后的修订。

---

## ⚠️ 先读：三条方法学更正（本版核心）

| # | 先前表述 | 现表述 | 原因 |
|---|---|---|---|
| 1 | 「官方候选中包含 GT 就是答案泄漏」 | 「**GT 图像字节级精确匹配命中率**」 | 无法区分『检索器独立命中』与『候选生成使用 GT 标注』；官方候选的产生过程未被完整说明 |
| 2 | 「所以自研重检索是干净基线」 | **不成立** | 低命中率不等于干净；命中率低也可能只是检索器弱 |
| 3 | 「哈希不重叠即证明无正确证据」 | **不成立** | 哈希只证明没有相同字节；同类不同实例图不会被判近重复，却恰是主要干扰源 |

详见 [`docs/official_pool_provenance.md`](docs/official_pool_provenance.md)（已核实 vs 未确认逐条对照）。

---

## 怎么读

| 你的需求 | 看这里 |
|---|---|
| 检索侧分工与 5 个问题的答复 | [`docs/01_检索侧分工与进度.md`](docs/01_检索侧分工与进度.md) |
| **命中率的准确表述 + 计算脚本 + 分母** | [`docs/03_证据规则.md`](docs/03_证据规则.md) §2 |
| **官方候选溯源：哪些已核实、哪些未确认** | [`docs/official_pool_provenance.md`](docs/official_pool_provenance.md) |
| `Incomplete` 规则的意见 | [`docs/01_检索侧分工与进度.md`](docs/01_检索侧分工与进度.md) §6 |
| **接口对齐（不另写第二套评分器）** | [`contracts/接口对齐_A侧确认.md`](contracts/接口对齐_A侧确认.md) |
| S3 是否承担 + 构造与校验规范 | [`docs/04_S3干扰证据规范.md`](docs/04_S3干扰证据规范.md) |
| 官方评测代码的 4 处缺陷 | [`contracts/官方评测接口差异.md`](contracts/官方评测接口差异.md) |
| **5 题样例验收材料** | [`samples/`](samples/) + [`samples/验收说明.md`](samples/验收说明.md) |
| 冻结清单模板 | [`freeze/冻结清单模板.md`](freeze/冻结清单模板.md) |

---

## 关键事实速览（已实测）

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench`，revision `43620fde4044bb150e158c67ad7af6b6b11e1da2` |
| 许可 | **CC-BY-4.0** |
| split | **只有 `test`**，1,353 题，**无官方 dev/val split** |
| 原始题 ID 字段 | `id`（字符串，如 `'0'`）——无原生 `qid`、无原生 `evidence_id` |
| 场景（9 种） | Angle 322 / Partial 246 / Temporal 149 / Others 120 / Obstruction 108 / Scope 102 / Deformation 102 / Biological 102 / **Incomplete 102** |
| `gt_images` | 5 张 × 1251 题，**1 张 × 102 题**（与 `Incomplete` **完全重合**，0 例外） |
| `retrieved_images` | **恒为 5 张 × 1353 题**，**无相似度分数** |
| **GT 精确匹配命中率** | 任意 **55.9%** / rank-0 **32.6%** / 全部 GT 覆盖 **2.3%**（分母 1353） |
| 检索语料 | 官方**已发布**（README 2024-11-05，Google Drive）→ 重检索路线可行，但**许可未确认** |
| 官方默认 rag 模式 | **走 GT 证据，不是 retrieved**（`run_model.sh` 实测） |

---

## 怎么用 `samples/` 立刻打通你的程序

```python
import json, pathlib
from PIL import Image

base = pathlib.Path("EdgeCoRAG-B-handover/samples")

for line in (base / "evidence_sample.jsonl").read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)

    # 失败行不得丢弃：status != "ok" 时仍要计入题单分母
    if rec["status"] != "ok":
        continue   # 但要在统计里保留该 qid

    # 1) 查询图固定第 1 位
    q_img = Image.open(base / rec["question_image"]["path"]).convert("RGB")

    # 2) 证据按 evidence_order 顺序跟随（顺序本身是变量）
    ev_imgs = [Image.open(base / e["path"]).convert("RGB")
               for e in rec["evidence_order"]]

    # 3) S2（GT 上界）用 scoring_only.gt_evidence_refs，不要用 evidence_order
    s2_imgs = [Image.open(base / g["path"]).convert("RGB")
               for g in rec["scoring_only"]["gt_evidence_refs"]]

    # 4) 提示。占位符数量是官方模板写死的，**不可随 k 自由改**
    n = rec["prompt_image_slots"]     # 常规 6（查询图+5）；Incomplete 2（查询图+1）

    q = rec["task_payload"]["question"]
    ch = rec["task_payload"]["choices"]
    prompt = (f"... Answer with the option's letter from the given choices directly. "
              + "<image>" * n + "\n" + q
              + f"\n Choices:\nA: {ch['A']}\nB: {ch['B']}\nC: {ch['C']}\nD: {ch['D']}")

    # 5) ⚠️ scoring_only 只用于评分，绝不进入证据选择或 prompt
    gold = rec["scoring_only"]["gold_choice"]
```

**四条纪律**：

1. 只读 `task_payload` + `question_image` + `evidence_order` 组装模型输入。
2. `scoring_only` 严禁进入证据选择或 prompt。
3. `status != "ok"` 的题**不得丢弃**，计入固定题单分母并单报覆盖率。
4. `evidence_order` 里 `used_in_prompt=false` 的条目（Incomplete 截断候选）**不要送入**。

---

## 需要你确认的 8 件事

**完整清单与可复制的提示词见
[`docs/05_给B的确认与续作提示词.md`](docs/05_给B的确认与续作提示词.md)** ——
可直接整段复制给 B 或接手的 AI。摘要：

1. **split 切分方案**与命名（`internal_holdout` **不得**称外部验证）。→ `docs/01` §2
2. **协议版本命名**：`proto_official_v1` / `proto_fixedk3_v1`，不得混表。→ `docs/01` §6
3. **评分器**：B 的 `strict_choice_v1` 为唯一解析器，A 侧不另写。→ `contracts/接口对齐_A侧确认.md`
4. **`prediction_raw` / `raw_output` 双字段冗余**是否接受。
5. **`parser_version`** 由 B 填、A 置 null 是否可行。
6. **`evidence_version` / `run_batch_id`** 命名与格式。
7. **官方格式导出由谁实现**。
8. **S3 首版范围**与可接受的 `undetermined` 比例。→ `docs/04` §9

---

## 本包明确**不**包含的内容

| 不包含 | 原因 |
|---|---|
| 冻结证据列表（全量） | **未完成**，仅接口样例 |
| 自研重检索证据 | 依赖语料下载与许可确认，**未开始** |
| S3 干扰集 | 依赖 S1 定稿，**未开始** |
| 20 题联调清单 | 依赖双方确认题目划分，**未开始** |
| 完整 smoke_20 | 本包 6 题是**接口样例**，不是 smoke_20 |

`handover/samples/` 中的 6 题**只是接口样例**，用于打通 B 侧程序；
它既不是完整 `smoke_20`，也不是自研检索的冻结结果。
