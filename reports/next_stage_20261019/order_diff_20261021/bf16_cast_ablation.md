# bf16-cast 消融：停于 fp32 精确基线门禁

状态：**未完成**。本机离线运行，不用GPU、不读取图像、不加载模型；未修改A树或已有分数表。

## 基线一致性核对

从本机会话包读取原始字节，V.shape=(4712,768)，Q.shape=(5,768)，均为float32。按现有similarity_bypass.py计算 `scores=V@Q[i]`，`np.lexsort((identity,-scores))`，剔除metadata指定self，取top10。沿用已归一化向量，不额外归一化。

- 五题、50行：qid/rank/identity/sha256 **50/50一致**，没有候选或顺序差异。
- score_fp32/score_fp32_hex：**15/50精确一致，35/50不一致**。
- 最大分数绝对差：**2.384185791015625e-07**。
- 本机NumPy：2.3.5；原始live表来自远端栈。本次未证明具体哪个内核/归约实现导致差异，不把可能原因写成结论。
- 精确分数门禁实际返回 **rc=1**。未放宽为容差比较，未替换或修补原分数。

| qid | 排序/身份一致行数 | 分数不一致行数 |
|---|---:|---:|
| mragb:10 | 10/10 | 5 |
| mragb:1049 | 10/10 | 6 |
| mragb:1051 | 10/10 | 6 |
| mragb:1062 | 10/10 | 9 |
| mragb:1117 | 10/10 | 9 |

示例：mragb:10 rank1，本机0.9157231450080872（0x1.d4d9aa0000000p-1），live0.9157232046127319（0x1.d4d9ac0000000p-1）。全部35行原值/期望值与hex见JSON。

## 消融前后top10差异

**未完成**。用户规定“必须逐行一致，否则先停”，因此未执行bf16转换，不填changed_order/changed_set/changed_top3为0，也未计算换位对分差。

## 与history的比较结论

**未完成**。基线门禁未过，未继续做raw→q95键映射或history对照。不能归因精度，也不能裁定池不同或编码路径不同。已有history/live使用不同池是既有事实，不能据此证明某个gap的原因。

方法边界：最终向量float32→bf16→float32只模拟最终向量量化，不等价于bf16模型内部编码。即使后续未复现，也不足以单独区分池差异与编码路径差异。

## 复算精确门禁

在具备NumPy的本机Python中运行下列代码；SOURCE为本机会话包，不需要GPU。输出每行差异并在任何差异时rc=1。

```python
import tarfile, io, csv, json, numpy as np
SOURCE = "/Users/joyboy/Documents/Codex/2026-10-19/edgecorag-context-recovery/outputs/autodl_resume_report_20261021/session.tar.gz"
with tarfile.open(SOURCE) as t:
    def read(n): return t.extractfile("session/" + n).read()
    V = np.load(io.BytesIO(read("encoded/V.npy")), allow_pickle=False)
    Q = np.load(io.BytesIO(read("encoded/Q.npy")), allow_pickle=False)
    assert V.shape == (4712, 768) and Q.shape == (5, 768)
    assert V.dtype == Q.dtype == np.float32
    pool = list(csv.DictReader(io.StringIO(read("encoded/pool.csv").decode())))
    meta = json.loads(read("encoded/encoding.json"))
    qids = read("encoded/qids.txt").decode().splitlines()
    live = list(csv.DictReader(io.StringIO(read("scores_live.csv").decode())))
ids = np.array([x["identity"] for x in pool]); bad = []
for i, q in enumerate(qids):
    scores = V @ Q[i]
    order = [int(j) for j in np.lexsort((ids, -scores))
             if ids[j] != meta["query_identities"][q]][:10]
    for rank, j in enumerate(order, 1):
        expected = next(x for x in live if x["qid"] == q and int(x["rank"]) == rank)
        actual = dict(qid=q, rank=str(rank), identity=str(ids[j]), sha256=pool[j]["sha256"],
                      score_fp32=repr(float(np.float32(scores[j]))),
                      score_fp32_hex=float(np.float32(scores[j])).hex())
        diff = {k: {"actual": v, "expected": expected[k]}
                for k, v in actual.items() if v != expected[k]}
        if diff: bad.append(dict(qid=q, rank=rank, differences=diff))
print(json.dumps(dict(rows=50, mismatch_rows=len(bad), mismatches=bad), indent=2))
raise SystemExit(1 if bad else 0)
```
