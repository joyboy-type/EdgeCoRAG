# #2 当前池V/Q可得性核验（2026-10-24）

**结论：V可得且完整，Q仅5题，不满足1,203题实验。状态：需补齐原始Q；若原始完整Q无法取回，则需对缺少的查询重编码。当前不能执行所注册的零GPU压维度实验。** 本次到输入核验为止，不产生排名、命中、Recall或MRR数值。

预注册已先提交：`ee730175761cda113d7dd48726d9050e1d0359b4`；文件`reports/paper_20261021/PREREGISTRATION_20261024.md`；SHA256=`c68300e6a76f4bafa888080f284e8a9b76371887b1c2386d7fe6986ad76e2307`。本回执在该提交之后读取矩阵头与行映射；没有改注册、开机、重编码、加载模型或计算检索指标。

## 当前批次的实际产物

归档路径：`/Users/joyboy/Documents/Codex/2026-10-19/edgecorag-context-recovery/outputs/autodl_resume_report_20261021/session.tar.gz`，SHA256=`842d76d478ea74e6646e707bd8066d44365282d8382a5653985fd5703a986710`；与既有`gpu_scores_20261021/scores_manifest.json`的source_tar摘要一致。

|成员|实读情况|能否用于本实验|
|---|---|---|
|`session/encoded/V.npy`|fp32，形状(4712,768)，pool.csv为4,712个唯一身份|V输入可得|
|`session/encoded/Q.npy`|fp32，形状(5,768)|Q不足，不能代表1,203题|
|`session/encoded/qids.txt`|5个唯一qid，与encoding.json的查询映射完全一致|只覆盖5道smoke题|
|`session/encoded/encoding.json`|model_id=google/embeddinggemma-2；revision=914f7f89142e33e77833254d9c9b90c3cef7303b；dtype=float32；batch16；TF32=False|与矩阵头和行数一致，并非完整查询集回执|

5个qid为：`mragb:10`, `mragb:1049`, `mragb:1051`, `mragb:1062`, `mragb:1117`。每个qid的query identity与SHA均能在pool.csv内精确匹配；本次未对缺失查询补造映射。编码源权重SHA256及软件栈见结果JSON的current_archive.encoding。

## 逐split覆盖

|split|所需题数|已有Q题数|缺少Q题数|
|---|---:|---:|---:|
|smoke_20|20|5|15|
|dev|150|0|150|
|frozen_test|1033|0|1033|
|合计|1,203|5|1,198|

来源：原始`logs/B_predictions.jsonl.gz`按注册所列split/stage/condition过滤，与归档qids.txt逐qid比较。缺少的1,198个题号完整列入`r2_input_availability_20261024.json → missing_qids`；其排序题单SHA256=`899f1a4a4b3500bd64dfb3640ffb10ca32e8ef7ea65eb2b2c3ac8a462f20a0cc`。这不是新检索结果，仅是输入覆盖。

## 其他归档与替代输入

- 第二份`/Users/joyboy/Documents/Codex/2026-10-19/edgecorag-context-recovery/outputs/autodl_session_pickup_20261021/session.tar.gz`中的上述5个成员SHA256均与第一份相同，**没有额外查询**。其Q也仅(5,768)；不是两份各5题可拼成10题。
- 旧源`/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/instance394-preflight/formal-retrieval-embeddinggemma2-backup/results/formal-retrieval-embeddinggemma2`确有`query_embeddings.npy`(1353,768)及`corpus_embeddings.npy`(18955,768)，npy保存dtype是float32；但`receipt.json → model_dtype=bfloat16`，属于历史编码批次。**保存为float32不等于用FP32模型编码。** 与当前FP32 live V不能未经验证直接混用，历史18,955池也不能替代当前4,712池。
- 不从历史ranking数组反推向量，不把V的query身份行冒充原Q，不将50个score行（5题×top10）当成50个查询。
- 在结果JSON.discovery.census所列两个本地根目录内，递归清点数组文件与44份归档；相关矩阵实读头信息，归档扫描结果与路径完整保留。忽略依赖库样例数组作为实验输入。43份归档可扫描，另1份第三方NLTK `punkt_tab.zip`非合法ZIP，明确记录，不能声称所有文件都完整读取。未探测远程实例，也不声称全机器或未挂载私有盘均无完整Q。

## 该补什么，下一步怎么做

优先找回与当前V同批次、同图像身份/预处理/FP32协议的完整Q及行映射；若取不回，至少缺1,198个查询向量需重新编码，V本身无需因Q缺失而默认重做。是否重编所有查询以统一运行批次，须在开机准备时先说明并作协议修订。实际重编码后不得继续标为“完全复用现有V/Q的零GPU实验”。

补Q归入后续与#1/#3合并会话的准备清单。开机前仍须报告固定题单、卡型、预计耗时及费用；本轮到此停止，不租卡，不执行#2。没有写`r2_dimension_compress_20261024.{json,md}`性能结果，避免把可得性回执当成已完成实验。

## 成员摘要（输入可追溯）

|归档成员|字节数|SHA256|
|---|---:|---|
|`session/encoded/V.npy`|14475392|`31a3e122be53f528d59b5ece290b0814461027d7792a0dd1ff6c2841bab827ce`|
|`session/encoded/Q.npy`|15488|`e6465e40cc63ae745e534c4001722d2066f0db9541ff4ca8a7e3cd2620b6890e`|
|`session/encoded/pool.csv`|640848|`12f1e2fee88b142868282cc9a9d8217b2615c6ce16d22f4cad155e758eca025d`|
|`session/encoded/qids.txt`|53|`8d30239c8b8f92ce268297cf17453fcddfb6fc9aa0e0946e9cded555c7bfd847`|
|`session/encoded/encoding.json`|1609|`8e7b75c90b5f6e014d789a4dccb0cd8bc9a34dc8e6161e83e1bfbcd0ed8f864c`|

本回执数字与源路径完整见`r2_input_availability_20261024.json`，其SHA256=`b47cd0f6c0784014db9b1fc739e7e2828998e7f7acaea6d358c995c61c83a48c`。主初稿、冻结表与a-side保持不变。
