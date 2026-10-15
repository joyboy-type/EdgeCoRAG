# 验证摘要

> 本轮（切分 v2 + 决策清单 + smoke_20 证据包）所有验证的**实际运行结果**。
> 每条都可复现；命令与输出一一对应。

---

## 1. 切分 v2 不变量（18 项）

命令：`python scripts/verify_split.py --version v2`

```
计数: smoke_20=20  dev=150  internal_holdout=150  frozen_test=1033
已调试题: 7

✅ I1  子集互斥（无 qid 跨子集）
✅ I2  总覆盖完整 — 唯一 1353 / 期望 1353
✅ I2b 无重复计数 — 总行数 1353 vs 唯一 1353
✅ I5  raw_id 为字符串
✅ I6  qid 格式 mragb:<raw_id>
✅ I3  已调试题不进入 internal_holdout
✅ I3b 已调试题不进入 frozen_test        ← v1 在此失败（泄漏 3 题）
✅ I4  已调试题全部有归属 — 7 题均已放置
✅ I8  声明计数 == 文件行数
✅ I8b 文件哈希与 manifest 一致
✅ I9  manifest 声明了机器可校验的分配规则
✅ I10 声明了实体/近重复组的处理方式
✅ 全部通过（18/18）
```

**v1 的失败证据（同一验证器）**：

```
❌ I3b 已调试题不进入 frozen_test — 泄漏 3: ['mragb:3', 'mragb:4', 'mragb:43']
```
→ 证明验证器**确实能抓到**该缺陷，而不是事后补写的检查。

## 2. 可重现性（相同输入 → 相同字节）

| 验证 | 结果 |
|---|---|
| 切分子集三次独立运行（含不同输出目录） | ✅ 四个子集哈希全部一致（`363f6918…` / `8d5346df…` / `3181bc8e…` / `c9f95065…`） |
| manifest 两次运行字节级比对 | ✅ `4938A5B8771E3FD5` == `4938A5B8771E3FD5` |

**为达成这一点修掉的问题**：`split_manifest` 原先写入墙上时钟 `generated_at`，
导致重跑字节不同。已改为**由输入派生的 `input_digest`**（`fb7df569304763e9`），
`generated_at` 置 `null`。

## 3. `--dry-run` 语义

执行前后比对 `splits/` 文件列表 → **完全一致** → 确实不写文件。 ✅

## 4. 实体连通性量化

命令：`python scripts/quantify_entity_connectivity.py`

```
跨题共享的图片哈希: 2688
    gt<->ret           1423
    gt<->gt            1091
    query<->query      162
    ret<->ret          11
    query+gt+ret       1
[仅精确重复] 组数 7，最大组 1338 题
每题平均共享图数: 8.02（中位 8，最大 11）
```

→ **组原子分配的实测后果**：`smoke_20=8  dev=7  internal_holdout=0  frozen_test=1338`
（荒谬，故 v2 检测到巨型组后自动退化为逐题分配并记录原因）

## 5. 语料可取得性

命令：`python scripts/probe_corpus_access.py`

```
❌ drive.google.com        TimeoutError
❌ docs.google.com         TimeoutError
❌ www.googleapis.com      TimeoutError
⚠️ googleusercontent.com   解析到 127.0.0.1
✅ lh3.googleusercontent.com  可达

⛔ 本机网络无法访问 Google 系域名
   -> 不能说明语料不存在或不可用；只能说明当前网络下无法验证
```

## 6. smoke_20 证据包（37 项）

命令：`python scripts/verify_handover_sample.py --dir packages/smoke_20 --jsonl-name evidence_list.jsonl --check-coverage`

```
题数 20，索引条目 216
✅ A. Schema 合规   (1/1)
✅ B. ID 体系       (7/7)    JSONL 216 / CSV 216，无孤儿
✅ C. 图片哈希       (3/3)    全在、字节哈希一致、格式与扩展名一致
✅ D. 图片解码       (3/3)    全部可开、尺寸一致、可转 RGB
✅ E. 顺序一致       (1/1)
✅ F. 数量正确       (3/3)    Incomplete 场景证据数为 1（1 题）
✅ G. 跨字段         (6/6)
✅ H. 隔离性         (4/4)
✅ I. 覆盖率         (8/8)    coverage_rate=1.0，缺失 0
✅ J. 失败行可保存    (1/1)
总计 37/37 项通过 -> ✅ 验收通过
```

**package_meta.json**：`content_digest=a8f174fb5893cc2a…`、`deterministic=true`、
`generated_at=null`。

## 7. 6 题接口样例（回归）

命令：`python scripts/verify_handover_sample.py`

```
总计 29/29 项通过 -> ✅ 验收通过
```
（比上一轮多 1 项，因为新增了 J 组失败行检查）

## 8. 已知限制（**必须随结论一起报告**）

| # | 限制 | 影响 |
|---|---|---|
| 1 | **实体/同源相关性未能隔离** | 数据集属性：2688 个图片哈希跨题共享，仅精确重复就把 1338 题连成一组。**建议 B 把 `(scenario, image_type)` 作为分层变量** |
| 2 | **已调试题清单可能不完整** | B 只提供 7 个 `raw_id`；若还有其它，需补充后生成 v3 |
| 3 | **语料不可得（网络）** | 独立重检索路线当前不具备可执行条件 |
| 4 | **E4B 不可行（8 GB）** | A2/A3 需更大显存机器 |
| 5 | **A 侧曾在全量题目上计算 GT 聚合统计** | 未用于挑题，但作为标签接触已如实声明 |
| 6 | **图片为重编码产物** | 原始字节取不到；哈希与落盘字节同源，编码确定性已验证 |
| 7 | **本机耗时不可与 B 机器相加** | 跨硬件耗时不具可加性 |

## 9. 未做的验证（明确列出）

| 未做 | 原因 |
|---|---|
| 真实 GPU 端到端性能 | 需目标硬件；**不编造耗时** |
| R@1/R@5/MRR | 尚未在真实数据上跑检索评测（接口已验证可用） |
| S3 干扰集的 L3 语义抽查 | S3 未开始（依赖决策 3） |
| 正式题单（top-k 确认后）的证据包 | 依赖决策 2 |
| Gemma 4 效用选择器 | 属方法扩展，未列入本轮硬门槛 |
