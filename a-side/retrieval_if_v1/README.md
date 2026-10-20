# 检索接口 v1 产物（A 侧交付给 B 的消费入口）

协议串 `a-side/retrieval-interface-v1`。规范说明见 `../../reports/next_stage_20261020/interface_freeze.md`。
**这里只有派生数值与身份哈希，不含任何原题文本、gold 答案或图片。**

## 目录

| 路径 | 内容 |
|---|---|
| `pools/<cohort>__dim<D>__top10.csv` | 每题 10 个候选：`qid,pool_id,retriever_id,embed_dim,rank,sha256,score,is_self_removed,refill_used` |
| `select3/<cohort>__dim<D>__cosine+random.csv` | cosine 与 random 各 3 张/题（utility 由 B 回传分数后另物化） |
| `pool_quality/<cohort>__dim<D>__margins.csv` | 分数结构 + `min_adjacent_margin`（脆弱度判据） |
| `metrics/retrieval_metrics_by_dim.csv` | any-hit / set-recall / all-GT / MRR，按维度与 cohort |
| `corpus/` | 语料身份映射（`manifest` 4,712 行、`occurrences` 14,475 行、`meta`） |
| `artifacts.json` | 全部文件的 sha256 / 字节 / 行数 |

cohort：`smoke_20`(20) / `dev_150`(150) / `frozen_test`(1033)，维度 `768/512/256/128`。
`internal_holdout` 未产出任何产物。

## 三步消费

```bash
# 1) 用你自己的数据集副本重建并校验语料（约 190 s）
python scripts/a06_build_corpus.py            # 产出 images/ + manifest + occurrences
python scripts/a06_build_corpus.py --verify   # 逐文件 sha 复算，mismatches 必须为 0
#    比对 content_digest = 31ade7b7e2454d0b9fcd58568247dd2a6862e15273fdd65e1d12ed50e373264e

# 2) 物化证据包（逐文件复算 sha，verify.json 的 mismatch 必须为 0）
python scripts/a15_materialize_packets.py --cohort dev_150 --dim 768 --strategy cosine

# 3) utility 策略：你回传 qid,sha256,score 后再物化
python scripts/a15_materialize_packets.py --cohort dev_150 --dim 768 --strategy utility --scores <b_scores.csv>
```

物化产物（`packages/<cohort>_dim<D>_<strategy>/`）内是 `evidence_index.csv` + `evidence_list.jsonl` + `package_meta.json` + `images/`，**schema 与既有 `handover/samples`、`packages/*` 一致**，你现有 loader 不用改。

## 三条不能越过的线

1. **顺序以本接口为准**：需要重跑时请沿用 `pools/` 的 rank 顺序，不要自己再排一次（排序脆弱性见 `interface_freeze.md` §6）。
2. **维度只能用 dev_150 选**，`frozen_test` 的数值只作描述性报告。
3. **gold 只进评分/Oracle**，不进候选、排序、选择、prompt。
