# EdgeCoRAG-B 交接包

> 面向 **B 部分（多模型推理、同证据公平比较、统计与错误分析）** 的检索侧交付物。
> 所有事实均在 2026-10-15 于本机对真实数据/代码实测核对，**未核对的项明确标注「待定」**。

## 怎么读

| 你的问题 | 看这里 |
|---|---|
| 一、分工与进度（5 个问题） | [`docs/01_检索侧分工与进度.md`](docs/01_检索侧分工与进度.md) |
| `Incomplete` 规则的意见 | 同上，第 6 节 |
| 三、证据规则（GT/候选/查询图区分） | [`docs/03_证据规则.md`](docs/03_证据规则.md) |
| 五、S3 干扰证据是否承担 | [`docs/04_S3干扰证据规范.md`](docs/04_S3干扰证据规范.md) |
| 二、接口样例 | [`samples/`](samples/) + [`contracts/`](contracts/) |
| 四、冻结清单 | [`freeze/冻结清单模板.md`](freeze/冻结清单模板.md) |
| 六、端到端性能测量 | `docs/01` 第 7 节 |

## 一句话状态

**检索侧（我）已完成数据与工具的实证核验，但尚未产出任何冻结证据列表。**
你可以立刻用**官方 `retrieved_images`** 打通 B 的程序，不必等我——见 `samples/`。

## 目录

```
EdgeCoRAG-B-handover/
├── docs/
│   ├── 01_检索侧分工与进度.md      ← 先读这个
│   ├── 03_证据规则.md
│   └── 04_S3干扰证据规范.md
├── contracts/
│   ├── evidence_list.schema.json   冻结证据列表的 JSON Schema
│   ├── result_row.schema.json      逐题结果行(供你写、我读)
│   └── 官方评测接口差异.md          ⚠️ 官方代码三处缺陷，会影响评分
├── samples/
│   ├── evidence_sample.jsonl       2–5 题样例（官方候选证据）
│   ├── evidence_index.csv          evidence_id ↔ 文件 ↔ sha256 ↔ 尺寸
│   └── images/                     样例图片本体（便于你直接跑通）
├── freeze/
│   └── 冻结清单模板.md
└── scripts/
    └── ...
```

## 怎么用 `samples/` 立刻打通你的程序

```python
import json, pathlib
from PIL import Image

base = pathlib.Path("EdgeCoRAG-B-handover/samples")

for line in (base / "evidence_sample.jsonl").read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    if rec["status"] != "ok":
        continue

    # 1) 查询图固定第 1 位
    q_img = Image.open(base / rec["question_image"]["path"]).convert("RGB")

    # 2) 证据按 evidence_order 顺序跟随(顺序本身是变量)
    ev_imgs = [Image.open(base / e["path"]).convert("RGB")
               for e in rec["evidence_order"]]

    image_files = [q_img] + ev_imgs

    # 3) 组装提示。注意 prompt_image_slots 是官方模板写死的占位符数量!
    #    官方常规=6(查询图+5 证据), Incomplete=2(查询图+1 证据)
    #    你若改用其它 k,必须同步改这个数量,且另立 protocol_version
    n = rec["prompt_image_slots"]

    # 4) 题面与选项(不要读 rec["scoring_only"]!)
    q = rec["task_payload"]["question"]
    ch = rec["task_payload"]["choices"]
    prompt = (f"You will be given one question concerning several images. "
              f"The first image is the input image, others are retrieved examples to help you. "
              f"Answer with the option's letter from the given choices directly. "
              + "<image>" * n + "\n"
              + q + f"\n Choices:\nA: {ch['A']}\nB: {ch['B']}\nC: {ch['C']}\nD: {ch['D']}")

    # 5) ⚠️ 绝对不要用 rec["scoring_only"] 做证据选择
    #    它只用于你事后评分:
    gold = rec["scoring_only"]["gold_choice"]
    leak = rec["scoring_only"]["gt_on_official_pool_ranks"]  # 该题 GT 是否已在池中
```

**三条纪律**：

1. **只读 `task_payload` + `question_image` + `evidence_order`** 来组装模型输入。
2. **`scoring_only` 严禁进入证据选择逻辑或 prompt**。
3. **`status != "ok"` 的题不要丢弃**，要计入分母并单独报告。

## 需要你确认的 6 件事（按优先级）

1. **split 切分方案**：因官方**只有 `test`**（无 dev/val），必须项目内自切分。
   我提议 `smoke_20` / `dev`(100–200) / `frozen_test`(其余) / `heldout_external`。→ `docs/01` §2
2. **协议版本命名**：官方场景规则用 `proto_official_v1`（Incomplete=1 张，其余 5 张）；
   固定 top-3 另立 `proto_fixedk3_v1`，**不得混表**。→ `docs/01` §6
3. **官方评分器缺陷的处理**：官方 `parse_multi_choice_response` 有类型错误会崩溃，
   且 `score.py` 按行顺序而非 ID 对齐。建议实现 `fixed_v1` 抽取器并保留官方结果对比。→ `contracts/官方评测接口差异.md`
4. **图片尺寸与顺序规则**：我提议不预缩放（交给各模型 `image_processor`）、
   查询图固定第 1 位、证据按排名升序。→ `docs/01` §4
5. **S3 首版范围**：是否只做 `D1 同类别不同实例` + `D2 主题相关不支持答案`？
   → `docs/04` §8
6. **接口 schema 是否认可**：`contracts/evidence_list.schema.json` 与
   `contracts/result_row.schema.json`。**尽早提异议，改动成本随时间上升。**

## ⚠️ 三个必须知道的实测发现

| # | 发现 | 影响 |
|---|---|---|
| 1 | **官方 `retrieved_images` 中 55.9% 的题已含 GT 正确证据**（756/1353），场景间从 6.9% 到 81.7% 相差 12 倍 | 官方池**不能当干净检索基线**；场景间对比用它会失真 |
| 2 | **官方 RAG 提示模板的图片占位符数量写死**（常规 6、Incomplete 2） | 改 top-k 必须同步改占位符，否则与官方不可比 |
| 3 | **官方 `score.py` 有 4 处缺陷**（类型错误会崩溃、无 ID 对齐、场景名 `Occlusion`/`Obstruction` 不匹配导致静默丢场景、默认走 GT 而非 retrieved） | 直接跑官方脚本得到的数字不可复现 |

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
| 检索语料 | **公开**（README 2024-11-05 发布，Google Drive 链接）→ 重检索路线可行 |
| 官方默认 rag 模式 | **走 GT 证据，不是 retrieved**（`run_model.sh` 实测） |
