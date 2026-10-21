# 排序差异回应

B3_history_live_top10.csv共100行；history的50行分数全部为空，status=archived_order_score_not_saved；live仅20行有分数，30行为missing_live_pending_GPU。“history/live各10行含分数”这份材料在本栈不存在，不是拒绝提供。

替代材料history_order_without_scores.csv为5题各10行“有序无分”候选身份、rank与status，逐行保留归档顺序。sha256列为image:*身份后缀，不能当原JPEG字节哈希。历史/live均为bf16，不称fp32。

1.27e-4／7.82e-4是相似度变化量的下界／上界（翻转给下界、不越界给上界），不是相邻分差。A的2.89e-4／8.81e-5／3.84e-3是相邻分差，两种量不可直接对撞。这些数值来自本轮交来的裁定，本批未重新评分。

1049 差 13.78%，与池不同一致（B 2.54e-4 vs A 2.89e-4；以B为分母，约14%；以A为分母约12.11%）。池不同已有来源计数支撑（见 sources_inventory.json）；未证明的是池差能否完全解释 gap 的幅度差（B 2.54e-4 vs A 2.89e-4）。B的history输入为queries=1353、corpus=18955；live的round-2 plan为corpus=18955、corpus_order=18955。A重建为4712池（A提供，见reconciliation.json）。规模差异已有证据，仍不能将幅度差写成“已解释”；结论仍是根因未定。

## A可自跑的替代方案（待获批GPU阶段，本批不执行）

原生a18采用全语料fp32、TF32关闭、batch16与1。固定同一语料及行序、五题清单、同一候选池CSV并绑定sha256；先对齐两栈候选身份，不把B的image:*后缀当A的q95字节sha。两batch共享同一语料向量V，分别得到Q；用float32落盘同一冻结池各项相似度，旁路字段为qid,batch,rank,candidate_identity,similarity。旁路只读冻结池，不重排/重建池；A即可对被换对两行求分差，附池sha与dtype/TF32/归一化证据。

```sh
python "$A_REPO/a-side/scripts/a18_batch_sensitivity.py" --corpus "$CORPUS" --qids-file "$FIVE_QIDS" --dtype fp32 --batches 16,1 --weights-sha256 "$WEIGHTS_SHA256" --out "$NEW_OUT/receipt_a18_five.json"
```

这条是A可直接执行的原生回执命令，但原生CLI不导出逐候选相似度，单跑它不足以交出分差。此前旁路待交付；本次已新增B侧纯NumPy导出器，调用与限制见下。a18尚不保存V/Q，获批编码阶段仍须另存对齐的V/Q和完整池清单；本批不改a-side、不声称已取得现场向量或同池分数。根因未定，等a18复跑的同池分数落地。


## 追加：B侧分数旁路（基线62c1e65）

新增 `b-side/similarity_bypass.py` 及 `tests/test_similarity_bypass.py`。只读保存的float32 V/Q与冻结池清单，不读图像、不加载模型、不改原池；按lexsort(-score, identity)派生诊断top10，仅剔除self。该诊断CSV不替换历史池，也不作新质量评估。

输入合同：pool.csv每行与V同一行对应，列identity,sha256，身份与sha均唯一；不能把top10池配上18955行V。qids.txt逐行对应Q。metadata含编码dtype、tf32_enabled布尔、batch_size正整数、stack_versions字典、query_identities（qid→self身份）。输入存储必须float32；历史bf16编码保存成float32时仍如实标dtype=bfloat16。只算原始点积，不额外重归一化。向量是否已按协议归一化由上游编码回执证明。pool_id为清单精确字节sha256；command_sha256绑定命令、工具代码与五份输入哈希。

输出固定列：qid,source,rank,sha256,score_fp32,dtype,tf32_enabled,batch_size,pool_id,stack_versions,command_sha256。score_fp32将NumPy原始float32值精确展开为可回读CSV数值，不四舍五入、不截断。stack_versions额外记录旁路使用的NumPy版本；CPU NumPy点积不是历史CUDA内核的替身。

GPU轮示例（须获批编码阶段先在新目录保存匹配向量；本批不执行真实数据）：

```sh
$PY b-side/similarity_bypass.py --vectors "$NEW/V.npy" --queries "$NEW/Q.npy" --pool "$NEW/pool.csv" --qids "$NEW/qids.txt" --metadata "$NEW/encoding.json" --source live --out "$NEW/live_scores.csv"
```

history/live与batch16/1分别调用、分别写新文件；已有输出拒绝覆盖。配套metadata示例：

```json
{"dtype":"float32","tf32_enabled":false,"batch_size":16,"stack_versions":{"torch":"上游实际版本","numpy":"上游实际版本"},"query_identities":{"mragb:1049":"与池identity同口径的self身份"}}
```

## 判定（出数前冻结，出数后不得改）

先锁定完整池身份及行序、pool_id、V/Q行映射、归一化协议；同池比较时dtype=fp32且TF32关闭。以下为预登记诊断方向，不能以一次观察冒充已证实因果：

1. 同池fp32下复现同样换位 → 归因方向为数值栈（dtype/内核/batch）。只有逐项受控对照才能指出具体因素；fp32条件下不能反称已证明bf16是原因。
2. 不复现 → 归因方向为历史归档（bf16或不同池）。需分别只改变dtype或池的对照，并明确哪项复现；缺这些对照就写“bf16与池差尚不能区分”，不能凭不复现任选一项作结论。
3. 连gap都对不上 → 先按“池仍不同”假说回退核对pool_id及候选身份映射；pool_id不同先阻断跨池比较。若pool_id、身份映射均一致，不能仅凭gap不同断言池不同，继续保留数值栈/向量差异未定。

以上方向与确认门槛现在固定；本批没有真实向量复算、未选择归因，结论仍是根因未定。


## 本次验收（分数旁路追加批）

原126项及新增3项合计129 tests OK，rc0；分析侧54 tests OK，rc0；裸审计rc1（缺显式私有输入，fail-closed设计）。合成向量CLI导出10行，rc0。A侧90个跟踪文件对543de53逐文件哈希差异为空；本批新增/改动文件CRLF=0，无*.json.json。发布审计实际rc见similarity_bypass_validation/publish_rc.json；命令及原始测试输出在同目录。未对真实向量打分或重排历史池，未运行GPU，不提升需求状态。判定方向与确认门槛在出真实数值前登记。
