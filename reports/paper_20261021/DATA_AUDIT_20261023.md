# 数据审计：数据地图与第二阶段复核（2026-10-23）

**当前状态：第一阶段地图已接受，第二阶段复核见文末；第三阶段未开始。** 下文至“第一阶段停止点”为第一阶段交付快照，当时能耗汇总缺失；本次已补本分支产物，并完成A侧固定提交的来源与方法对账；两处均值法复算一致。

**第一阶段原交付范围（历史快照）：** 直接解析下列 CSV、压缩 CSV、JSONL、JSON 及私有归档成员，核查记录粒度、行数、键、分母、条件和来源绑定；不运行推理、不新增实验或区间，原论文对照评级与方向筛选留待后续。

## 核查口径与来源索引

CSV“数据行”不含表头；JSONL 按对象计，压缩文件先解压；普通 JSON 按对象/数组元素计，不能以排版行数充当观测数。“缺行为零”仅指已声明题单、条件矩阵或联接范围内的完整性，不表示覆盖整个基准。时间来自记录或回执，**不以文件修改时间代替实验时间**。

仓库根目录：`/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/publish-20261021/EdgeCoRAG`。下文所有仓库相对路径均相对于此目录。私有文件仅记录路径、计数与摘要，不复制题干、答案或输出正文。

|代号|已打开的原始产物|
|---|---|
|M|`logs/B_predictions.jsonl.gz`；`reports/v1.10.1/quality.csv`|
|J|`reports/next_stage_20261019/error_partition_20261021/{join_v2.csv.gz,partition_rows.csv.gz,main_2x2/main_table.csv}`|
|P|`reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv`|
|Q|私有目录 `/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/next-experiment-20261019/continuous-complete-backup`，打开其中各 split 的 `results/generate-*/{predictions.jsonl,receipt.json}` 及 `closeout-manifest.json`|
|QS|私有目录 `/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/next-experiment-20261019/corrected-protocol-scoring`，打开全部 `*__*__*.private.json` 的 `per_question/overall/source_predictions_sha256`|
|D|`reports/next_stage_20261019/无自匹配检索_维度消融.csv`；对应 Markdown 四维表；私有 `/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/next-experiment-20261019/dimension-ablation-private/per-query.private.json`|
|N|`logs/results_20261020/mmdocrag_evaluation_numeric_metrics.csv`|
|G|`reports/next_stage_20261019/gpu_judge_s3_20261021/judge/{scores.csv,raw_outputs.jsonl.gz,meta.json,consistency.json}`|
|S|`reports/next_stage_20261019/gpu_judge_s3_20261021/S3/*.csv` 及各 `receipt_*.json` 的上下文；Gemma 原始记录来自 M|
|E|`reports/next_stage_20261019/gpu_cost_20261021/{device_samples.jsonl,index_residency.json,switches.json,manifest.json}`|
|F|`reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`，读取 `numbers/source_catalog`，本阶段不作全面数字结论复核|
|K|`reports/next_stage_20261019/pixel_identity_18955_keys_20261021/pixel_identity_18955_keys.csv` 与 `export_receipt.json`|
|A|只读 `/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/a-iface-20261021/EdgeCoRAG/a-side/retrieval_if_v1/corpus/{corpus_manifest.csv,occurrences.csv}`|
|B|`reports/next_stage_20261019/gpu_scores_20261021/{scores_manifest.json,scores_live.csv,scores_history.csv}`|
|T|本地归档 `/Users/joyboy/Documents/Codex/2026-10-19/edgecorag-context-recovery/outputs/autodl_resume_report_20261021/session.tar.gz`，直接读成员，未解压写入仓库|

T 的整包 SHA256 为 `842d76d478ea74e6646e707bd8066d44365282d8382a5653985fd5703a986710`；F.source_catalog 中指向 T 的成员摘要全部匹配，包括 `session/{encoded/pool.csv,receipt_a18_B_cross_stack.json,E3/requests.jsonl,E3/switches.json,encode_timing.json,E3/index_residency.json,utility/receipt.json}`。F 指向的仓库原始文件摘要也全部匹配。注意：匹配的是被列出的来源，不是对整个私有目录作全盘真实性保证。

## 数据地图

|实验|原始文件|观测数 / 分母|测的是什么|能回答什么问题|不能回答什么|
|---|---|---|---|---|---|
|主实验|M 的逐题日志与质量表|日志 21,927 条；正式主表筛选后 15,495 条，即各模型各条件同一题单；每格 1,033 题（M.stage/split/condition/qid）；质量表 34 个汇总格|无证据、共享证据、金标证据下的严格选择题正确率及解析状态|同题、固定证据条件的模型表现；格式失败作为错误保留|自主检索能力、同视觉 token 成本、纯证据质量因果效应；金标条件的证据数量不同|
|分格与伤害|J.join_v2、partition_rows、main_table|联接 5,165 行；全日志标注 21,927 行；正式分格 5 个模型汇总（J.model/qid/source_line）|金标身份命中与 S1 答对的交叉表；S0 答对到 S1 答错的伤害覆盖层|证据是否出现、出现后是否答对，以及条件切换时的损失|“未命中”是否无语义支持；伤害的因果机制；旧四类不能当互斥分类|
|三策略|P；Q 全部 generate 预测；QS 对应评分|P 60 行；Q 18,045 条，按 smoke/dev/frozen 分开；每模型每策略各 split 分母分别为 20/150/1,033（Q.split/selection_strategy）|固定候选池的 cosine/random/utility 选证据后答案；P 另含 dev 选择路径与事后 Oracle|逐策略的选中身份、条件表现及答案比较；逐题记录现已可得|P 的路径不能当四个独立策略；事后 Oracle 不能当可部署收益；Q 的选择不能与主实验 S1 当同一检索输出|
|维度消融|D 的 CSV、私有逐题统计及 Markdown 四维表|CSV 12 行；私有 4,812 个题×维度统计；每维覆盖 20/150/1,033 三个分开的 cohort（D.cohort/dimension/questions）|历史排序缓存在移除自匹配后的精确身份 any-hit、集合 Recall、MRR 与理论向量载荷|历史池内部的维度与命中关系；不同检索指标的差别|当前语料池的性能、下游答案质量、重新编码速度、实测整机内存/能耗或等价性|
|MMDocRAG|N；G 的数值评分及原始 judge 输出|N 1,000 行，五模型每个 200 题；G.scores 同样 1,000 行；G.raw 1,050 条含重复检查（N.model/q_id；G.repeat）|固定候选下的引用 P/R/F1、词面指标及另阶段的五维 judge|小规模文档问答的引用与输出画像；分列不同指标|自主召回与跨数据集命中×答对分格；词面/引用/judge 不能互称事实正确率|
|S3 干扰|S 的 Qwen CSV；M 的 Gemma S3-pure|指定目录 6 个 CSV 共 72 行，只含两个 Qwen；合并 M 的 72 个 Gemma 正式/开发记录后共 144 条；每模型 dev/holdout/frozen 分母 5/2/29（S.qid；M.stage）|经辅助审阅的固定干扰子集响应|在同一子集与自身 S1 配对的变化|不能称四模型全题集四条件；不能混入性能重复，也不是人工盲审语义无关性验证|
|成本与能耗|E；T::session/E3/requests.jsonl；F.cost.*|请求 69 条＝60 热请求+9 预热，每模型热请求 20；功率样本 570 条（requests.warmup/model；samples.epoch）|固定证据、短输出的分项时延、采样设备内存与 GPU 功率；F 有 22 条成本条目|已测模型与边界内的成本画像；完整性及热/冷请求拆分|五模型完整成本、生成长答案、整机/边缘能效；指定 energy_summary 缺失，历史能耗值尚无本轮汇总文件复核|
|索引与 a18|K、A、T::encoded/pool.csv、T::receipt_a18_B_cross_stack.json、B|K 18,955 行；pool/A manifest 4,712 唯一身份；occurrences 14,475 次使用；a18 查询清单 1,203 个；B 两张评分表各 50 行（各自字段见下）|q95 字节身份集合对账、角色覆盖及指定栈的批大小敏感性|发布索引与当前语料的身份关系；回执记录的 batch 不变性与小范围评分链路|不同身份基线不能直接交集；B 的小样本评分不是完整 a18；回执本身不足以独立重算全部批排序|

## 逐文件完整性、条件与时间核查

### 主日志与质量汇总（M）

- M 日志按完整 `row_key` 及 `(task_id,qid)` 检查均无重复、空键或非法 JSON 对象。若错误地只按 `model_key/split/condition/qid` 去重，会看到 **1,560 条重复超额**，来自阶段/重复测量，不能直接删除。
- 主表筛选固定为 `stage=quality AND split=frozen_test AND condition in {S0,S1,S2}`，各模型条件题号集合完全相同，键 `(model_key,condition,qid)` 无重复。日志中仅筛 `split=frozen_test` 还会带入 S3 子集，不能代替上述筛选。
- 日志阶段计数（M.stage）：`quality=17807`、`development=2260`、`performance=1550`、`smoke=300`、`preflight_single=5`、`preflight_multi=5`。quality 汇总覆盖 frozen 和 internal_holdout，不含 dev。
- M.quality.csv 的每个 `n/correct/format_failures/generation_errors` 都与日志对应 quality 行一致；`n` 合计 17,807。未发现既定质量矩阵的缺行。
- 主表的 `evidence_ids_order`：S0 无证据，S1 每题三张，S2 常规五张而 Incomplete 一张；`input_image_count` 还包含查询图，不能直接当证据数。主表没有按解析成功缩分母：Qwen3-VL-8B S1 有 4 条解析失败，Qwen3.5-4B S1/S2 各 21/55 条（M.parse_status）；这些仍在相应固定分母中。
- M.`synthetic=false`、`run_batch_id=v1.10.1`、`protocol_version=published_top3_actual_gt_d1_v1` 覆盖整份日志；各模型主表只有一个 `model_revision`。日志无逐条绝对时间字段；运行身份可核，不能按文件日期另筛一个“某天实验”。`timing` 是耗时而非发生时间。

### 分格输入和旧分类（J）

- `join_v2.csv.gz` 按 `(model,qid)` 无重复，所有 `joinable=True`，`missing_reason` 为空；`source_line_S0/S1/S2` 均能定位到 M 对应的 frozen quality 行；S0/S1 正确标记逐条一致。另将 M.evidence_ids_order 的角色别名通过 A.occurrences 的 `(qid,role,rank)` 转为 SHA，与该题 GT 身份集合比对，逐行重建的命中布尔值与 J.top3_gt_hit 全部一致；不是只检查联接表自洽。
- 该文件的 `membership_count` 属于旧四标签：全表为零/一/二重归属的行数分别为 1458/2009/1698（J.membership_count），因此旧标签不是互斥分格。当前互斥分格必须从 `top3_gt_hit × S1_correct` 构造；重算后与 J.main_table 的各格及伤害列一致，未新定义指标。
- `partition_rows.csv.gz` 与 M 每条 `source_line/qid/model/split/stage/condition` 对应，无丢行或重复。但其 `category` 实际只有“不可判定”和“检索伤害”：前者 21374 行、后者 553 行，不能当完整互斥分格表。
- “检索伤害”标签还跨 split：frozen 482、dev 63、smoke 8（J.partition_rows.category/split）。不能把全文件的伤害总数用于 frozen 分母。

### 三策略及路径矩阵（P、Q、QS）

P 的唯一键为 `(model,path,split)`，全矩阵无重复，`missing_prediction` 合计为零，全部预期路径×模型×split 组合齐全。路径含义必须保留：

|路径|实际含义（P.path/selected_strategy/post_hoc_oracle）|
|---|---|
|P1|cosine|
|P2|utility|
|P3|在 dev 选择后固定的策略，随模型不同；不是 random 别名|
|P4|逐题事后 Oracle，不是新增训练或可部署路径|

P3 在所有 split 中保持相同选择：Qwen3-VL-4B、Gemma E2B 选 utility；Qwen3-VL-8B、Qwen3.5-4B 选 cosine；Gemma E4B 选 random（P.model/path/selected_strategy）。因此不能用 Qwen3-VL-4B 的 P3 行代表 random。

Q 每个模型文件均包含 `cosine/random/utility`；唯一键为 `(qid,selection_strategy)`，每条 `selected_ids` 恰有三个不同 ID，没有缺字段、重复选择或空键。所有模型/策略的同 split 题号集合一致；Q 的 frozen 集合与 M 主表题单一致，smoke/dev/frozen 题号两两不交。每份 Q 文件的 SHA256 与 `closeout-manifest.files` 一致，`receipt.completed_rows` 与实读行数一致。

QS 的各 `per_question` 与 Q 对应策略题单一致，`source_predictions_sha256` 全部匹配，`overall.total/correct` 与逐题计数一致；P 的 P1/P2/P3 汇总与对应 QS 无不一致。P4 标为 post hoc，仅保留其既有身份，本阶段未评价收益或部署能力。

|模型（Q 文件名 generate- 后缀）|smoke_20 文件行数|dev 文件行数|frozen_test 文件行数|每文件重复/缺口|
|---|---:|---:|---:|---|
|qwen3vl_4b|60|450|3099|无；按各自 split×策略题单|
|qwen3vl_8b|60|450|3099|无；按各自 split×策略题单|
|gemma4_e2b|60|450|3099|无；按各自 split×策略题单|
|gemma4_e4b|60|450|3099|无；按各自 split×策略题单|
|qwen35_4b|60|450|3099|无；按各自 split×策略题单|

上表每格是 Q 对应 `split/results/generate-模型/predictions.jsonl` 的实读对象数，亦为物理行数；每格再分别除以策略类别数才是该 split 题数。QS 共 45 个私有 JSON，每个按 `per_question` 对应上述文件的一项策略，未混入另一批生成。

Q 的 `receipt.started_epoch` 范围换算为 UTC 为 2026-10-19T04:47:28.416463+00:00 至 2026-10-19T12:32:51.964897+00:00；`closeout-manifest.epoch` 是完成归档时点，不是每条预测的时间。预测行没有逐题绝对时间；未用日期目录名作为筛选条件。

**后补 utility 是另一批数据。** 已直接打开 T 中 `session/utility/dev_150_dim{128,256,512,768}_scores.csv`：每个文件数据行 1,500、物理行 1,501，字段为 `qid/sha256/score`，每维恰有 150 个题号、每题 10 个不同候选，键 `(qid,sha256)` 无重复、score 均为有限数。四文件共 6,000 行，与 T::session/utility/receipt.json 的 `expected/completed` 及 `artifact_sha256` 对应。该回执 `started_epoch` 为 2026-10-21T00:10:37.637665+00:00，晚于 Q。它是 raw last-token logit 补分；没有与它绑定的后续新生成记录，不能把它写成 Q 那批端到端预测已经使用的评分输入。

### 维度消融（D）

- D.CSV 唯一键 `(cohort,dimension)` 完整；维度为 128/256/512/768，各维度内 smoke/dev/frozen 分母分别固定 20/150/1,033，不把三个 cohort 混成正式评估分母。
- 私有逐题文件以 `(qid,cohort,dimension)` 唯一；`hit_at_1/5/10` 的合计、`recall_at_1/5/10` 与 `mrr` 的题均值均与 D.CSV 对应行一致。Markdown 四维主表的命中计数与 CSV 一致，无遗漏维度。
- `hit_at_5_questions` 是至少命中一个精确 GT 的题数；`mean_recall_at_5` 是题级 GT 集合召回的平均，不能混称。主表的分母来自 `questions`，不是整个缓存查询行数。
- 这是历史索引缓存的离线过滤/复核，`dense_float32_vector_payload_mib` 为理论载荷列；不是新编码、实测完整索引文件体积、系统内存或下游准确率。无逐行发生时间字段，不按审计日期重新定义 cohort。

### MMDocRAG 数值指标与 judge（N、G）

- N 全部 `split=evaluation, setting=15, dataset_revision=04b58dbc5c6c4955291124eed411b09114728061`；完整键 `(dataset_revision,split,setting,q_id,model)` 无重复/空键，五模型题单一致。各引用及词面分数均在定义范围内，无非法数值。目录名 results_20261020 不能替代生成发生时间；N 无逐条绝对时间，不能据此称整批与后续 judge 同时生成。
- N 的 `generation_error_present=False` 覆盖全表；Gemma E2B 有 7 条 `processed_response_empty=True`，仍保留固定分母。此处空响应不是缺行。
- G.scores 按 `(model,q_id)` 无重复、无空分数；各维度值均为整数且落在 0–5。与 N 的模型—题号键集合完全一致，联接既不丢行也不扩行。
- G.raw 实读 1050 条，其中 50 条 `repeat=True`，另有 1000 条初评记录；原始日志按模型—题号有 50 条重复超额，属于一致性复评，不能算新增样本。初评 `parse_ok` 全部为真；复评采用另一记录结构，不含该字段，不能据此判为解析失败。初评、复评分值均与 G.scores 对应记录一致。
- G.consistency 的 `details` 长度与 `n` 均为 50，键无重复，`first/second/same` 一致。它只检验同一 judge 的复评一致性，不能建立外部事实性。
- N.`judge_evaluated=False` 是早期无 judge 指标导出的状态；G 是后续独立阶段，不能用该旧字段否定后续评分存在，也不能覆盖原始导出改为 True。G.scores 不带 revision/split/setting，当前键集虽匹配，但跨版本联接必须依赖 N 的受限上下文与 G.meta 的 source bindings；G.meta 有 gold/prompt 摘要，未提供逐条绝对时间。
- G.meta.`model_id/revision` 与被评 Qwen3-VL-8B 重叠，须保留 self-judge bias；引用、词面和 judge 必须分表或分列。

### S3 分目录检查（S、M）

|S 的文件名|数据行 / 物理行|correct=True|重复键 / 缺行|
|---|---:|---:|---|
|S3_qwen35_4b_dev.csv|5 / 6|2|无 / 对回执既定子集无缺行|
|S3_qwen35_4b_frozen.csv|29 / 30|7|无 / 对回执既定子集无缺行|
|S3_qwen35_4b_holdout.csv|2 / 3|1|无 / 对回执既定子集无缺行|
|S3_qwen3vl_4b_dev.csv|5 / 6|1|无 / 对回执既定子集无缺行|
|S3_qwen3vl_4b_frozen.csv|29 / 30|8|无 / 对回执既定子集无缺行|
|S3_qwen3vl_4b_holdout.csv|2 / 3|1|无 / 对回执既定子集无缺行|

上表数值均来自对应 CSV 的 `qid/choice/gold/correct/status`；逐行 `choice==gold` 与 `correct` 一致，所有 `status=ok`。文件本身不带 model/split/时间字段，按文件名与收货回执上下文绑定，不能脱离该上下文使用。

**回执行尾差异：** S 的逐模型 receipt.csv_sha256 均不等于当前 CSV 的 LF 字节摘要；把当前 CSV 仅恢复为 CRLF 后，各个摘要都与原 receipt 匹配。G.meta.files_sha256 对 scores.csv 也保留 CRLF 摘要。最新 final_receipt.json 的 hash_canonicalization 与 csv_sha256/outputs 则记录入库 LF 摘要，与当前文件匹配。应同时保留原始字节摘要与规范化摘要，不把这项差异误判为评分变化，也不能说所有历史回执都直接匹配当前字节。

Gemma 原始 S3 来自 M：筛 `condition=S3-pure AND stage in {development,quality}` 后两模型各 dev/holdout/frozen 为 5/2/29 条；合计 72 条。若只筛 `condition=S3-pure` 会读出 122 条，其中另有 50 条性能重复（M.stage）。合并上述 Qwen 后，各 split 的题号集合在四模型间完全相同，且对应自身 S1 子集无缺失。指定 S 目录本身**不包含四模型的全部结果**；M.quality.csv 也未回填后补 Qwen S3，不能把它当最新四模型 S3 汇总。

### 成本、时间窗口与能耗缺口（E、F、T）

- 指定 `reports/next_stage_20261019/gpu_cost_20261021/energy_summary.json` **缺失**。已检索当前仓库及本项目 work 目录树，并查看 T 成员；该范围未找到同名产物。不能把“未找到文件”写成零能耗，也不宣称其他机器没有该文件。
- T::session/E3/requests.jsonl 的 `condition=fixed_cosine`，所有 `generated_tokens=2`；各模型有 23 条记录，其中热请求 20、预热 3（requests.model/warmup）。整行无重复，热请求按 `(model,qid,condition)` 无重复，无 generation_error；`preprocess_ms/encoder_ms/retrieval_ms/generation_ms/e2e_ms/device_peak_bytes_sampled/allocator_peak` 均未缺失。预热有重复题号，必须靠行序及 warmup/cold 状态区分，不能把它当独立质量样本。
- 对现有 F 的热请求 P50/P95 条目按原定义核对，均匹配；峰值条目有的包含预热，不能统一套用 `warmup=false`。首请求 `encoder_ms=493.8607579`、`generation_ms=639.6936402` 同属 cold warmup 行（T::requests 第一行；F.cost.cold_first.encoder_ms），不代表热请求均值，也不支持“编码整体主导成本”。
- E.samples 的 `epoch` 唯一且严格递增；无缺失功率；窗口为 2026-10-21T00:09:12.643921+00:00 至 2026-10-21T00:10:36.185174+00:00，跨度 83.541253 秒（由 epoch.max−epoch.min 核对，与既有约数口径一致）。绝对时间以 UTC 报告。
- `4.35 Wh` 目前仅能追到 `DATA_INVENTORY.md` 等文字陈述；F 中没有 energy 条目，指定汇总 JSON 缺失。本阶段确认了原始功率样本与时间跨度，**未把文字能耗值提升为已复核数值，也未新建能耗汇总或重积分**。
- T::requests.`retrieval_scope` 明示“当前向量池点积 + 消费固定证据、不重排候选”；测了组件链路，但不是把现场新排名闭环送入生成的完整自主检索。E.index_residency.`storage` 是 CPU NumPy 驻留，不能写 GPU 索引驻留。
- E.switches 是顶层数组，元素数量为 3；E.index_residency 是一个对象。请求行不带逐条绝对时间，采样窗口也未逐请求绑定，不能把整个窗口能量按题或模型任意摊分。

### 索引身份、评分样本与 a18（K、A、B、T）

- 指定 `reports/next_stage_20261019/index_reconciliation_20261021/` 目录缺失；不是因此断言对账无法核。当前可用 K 的 `sha256_raw/sha256_q95`、T 的 pool.`sha256` 及 A 的角色表恢复身份集合核对。
- K 的 raw、q95、l1b 各列在本文件内均唯一；T.pool 的 `identity/sha256` 无重复，A.corpus.`sha256` 集合与 T.pool 完全一致；A.occurrences 的 `(qid,role,rank,sha256)` 无重复，无孤立到语料外的 SHA。
- 按 q95 同口径交集得到 4282，当前语料缺 430；缺失角色为 query-only 415、GT-only 9、GT/official_retrieved 6（K.sha256_q95 ∩ T.pool.sha256；A.occurrences.role）。这些是唯一图像身份，不是题数。
- A.occurrences 跨整个原始题域，角色计数为 query=1353、gt=6357、official_retrieved=6765（A.role）；不是仅 frozen 子集。缺失 GT 图像数不能直接换算成 frozen 受影响题数，更不能与 D 中“全部 GT 不在历史池”的题数混用。
- 故意用 K.`sha256_raw` 与 q95 pool 交集会得到零，属于身份口径错配，不能拿来声称语料完全不相交。K.export_receipt.`source_same_origin_as_A_parquet` 仍为“未验证”，`l1b_scope` 仅粗筛候选，不是像素或语义等价证明。
- B.scores_manifest 是一个 JSON 对象，列出两个评分 CSV；逐文件数据行、列数与 SHA 均匹配。每个 CSV 是五个查询身份各十个候选，不是完整 a18 题单。live/history 的 pool 大小、编码 dtype 与身份基线不同，不能把两张表当同池精度或批大小消融。
- a18 原始回执在 T::session/receipt_a18_B_cross_stack.json；本地 `/Users/joyboy/.codex/.chatgpt-projects/g-p-6acf980f24fc8191aa5a917d5c41b108/work/autodl-resume-report-20261021/completed_artifacts/receipt_a18_B_cross_stack.json` 为可读副本。回执 `queries.n/results.total` 与 `inputs/a18_qids.txt` 的实读且不重复题号数一致；`corpus.rows` 对应当前 pool，`limit_applied=null`。
- a18.`params.batch_pair=[16,1]`，`results.changed_order/changed_set/changed_top3=0`；回执记载指定 fp32、TF32 关闭及栈版本。T 内未见 a18 专用的逐查询双批排名 CSV/NPY/JSONL，故本次核到了**原生回执、查询清单和配置**，未从全部原始排名独立重算零翻转。也不能扩大为任意栈/设备/精度不变性。

## 数据与叙述的偏差

本节仅登记影响后续审计的口径问题，不筛选论文方向、不改原文。

|编号|叙述/入口|原始证据与偏差|后续应采用的口径|
|---|---|---|---|
|ΔA|“全部日志就是正式主实验”|M 混有性能、开发、冒烟、预检和 S3；完整键无重复，简化键会重复|主表必须使用 M 的 stage/split/condition 筛选，性能记录不进质量分母|
|ΔB|把 partition_rows 当互斥分格，或直接相加旧四类|J.category 只有伤害/不可判定；J.membership_count 有交叠与未归类|从 top3_gt_hit×S1_correct 重建；伤害作为独立覆盖层；不能把全文件跨 split 伤害计数套 frozen 分母|
|ΔC|P3=random、路径数等于策略数|P.P3 随模型固定为 dev 选中策略；P4 是 Oracle|直接用 Q.selection_strategy 识别三策略；P3/P4 不添独立策略样本|
|ΔD|“逐题策略证据没有记录”|Q 的真实预测文件完整保留 selected_ids，并通过 closeout 摘要|PAPER_EVIDENCE_REVIEW/DECOMPOSITION/DATA_INVENTORY 中“因此放弃策略检验”的旧段落已过时；以后续外推报告为准，但本阶段不评价外推结论|
|ΔE|“新补 utility 分数就是已有端到端策略生成的评分输入”|Q 与 T.utility.receipt 的时间及来源绑定属于不同批次|分别写历史策略生成与后补 dev 四维打分；没有后补分绑定的新生成，不串成同一端到端增益|
|ΔF|“四模型 S3 全在补跑目录/已进统一 quality 表”|S 目录只有 Qwen；Gemma 在 M，M.quality 没有后补 Qwen|合并来源并只取既定子集，不称全量四条件；AI 辅助、label-aware 边界保留|
|ΔG|“judge 没做”或“原始 judge 对象数都是独立样本”|N.judge_evaluated 是旧导出状态；G 后续记录存在，G.raw 含 repeat|初评与一致性复评分开；跨文件连接限制到当前 revision/split/setting，self-judge 不作独立事实证据|
|ΔH|“压维度几乎不损回答上限/实测系统体积降至三分之一”|D 是历史池身份命中和理论向量载荷，无下游答案与完整系统资源测量|仅报告历史池各指标与理论载荷，不称答案天花板或等价性；不混当前池|
|ΔI|energy_summary 与 index_reconciliation 已在仓库|两处指定入口缺失；能耗只有样本，索引底层表可恢复|能耗值暂列未复核；对账使用已核的 K/A/T 路径；区分路径缺失与数据不可得|
|ΔJ|“编码主导成本”“完整端到端自主检索/整机能耗”|T.requests 冷启动编码与生成不是热均值；retrieval_scope 固定证据；E 只采 GPU|限三模型短输出 pilot、组件测量与 GPU 功率画像；不推完整系统或边缘收益|
|ΔK|“发布索引与语料按原始字节直接对账”“跨栈零翻转有完整逐题排名证据”|对账交集依赖 q95 身份；K 原始来源等价尚未验证；a18 主要为回执证据|注明 q95 同口径、来源边界；零翻转标回执读数，B 小样本表不替代完整排名|
|ΔL|“原 receipt 摘要可直接核对当前 S3/judge CSV”|S 逐模型回执和 G.meta 保留 CRLF 摘要；最新 final_receipt 记录 LF 摘要|标注行尾规范化层；两套摘要各自匹配，不混称同一字节哈希|

## 文件行数与来源指纹

以下“物理行”包括 CSV 表头；JSON 行数只是序列化排版。计数是本次直接读取结果，指纹用于定位审计对象，不能代替观测定义。

|文件（代号下路径）|数据记录 / 元素|物理行|唯一键与重复超额|
|---|---:|---:|---|
|logs/B_predictions.jsonl.gz|21927|21927|row_key 或 task_id+qid|0|
|reports/v1.10.1/quality.csv|34|35|model_key+split+condition|0|
|reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz|5165|5166|model+qid|0|
|reports/next_stage_20261019/error_partition_20261021/partition_rows.csv.gz|21927|21928|source_line|0|
|J/main_2x2/main_table.csv|5|6|model|0|
|reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv|60|61|model+path+split|0|
|reports/next_stage_20261019/无自匹配检索_维度消融.csv|12|13|cohort+dimension|0|
|D 私有 per-query.private.json|4812|JSON 单数组，按元素计|qid+cohort+dimension|0|
|logs/results_20261020/mmdocrag_evaluation_numeric_metrics.csv|1000|1001|revision+split+setting+q_id+model|0|
|reports/next_stage_20261019/gpu_judge_s3_20261021/judge/scores.csv|1000|1001|model+q_id|0|
|G/raw_outputs.jsonl.gz|1050|1050|model+q_id|50|
|G/consistency.json|1对象，details=50|按数组字段计|details 的 model+q_id|0|
|T::session/E3/requests.jsonl|69|69|热请求 model+qid+condition；预热按行序区分|0|
|reports/next_stage_20261019/gpu_cost_20261021/device_samples.jsonl|570|570|epoch|0|
|E/switches.json|3元素|275|模型切换记录；未定义跨次自然主键|无整行重复|
|E/index_residency.json|1对象|19|非逐题表|不适用|
|E/energy_summary.json|缺|缺|不适用|不适用|
|F/frozen_numbers.json|172|1943|numbers.id|0|
|reports/next_stage_20261019/pixel_identity_18955_keys_20261021/pixel_identity_18955_keys.csv|18955|18956|sha256_raw；sha256_q95 也唯一|0|
|T::session/encoded/pool.csv|4712|4713|identity/sha256|0|
|A/corpus_manifest.csv|4712|4713|sha256|0|
|A/occurrences.csv|14475|14476|qid+role+rank+sha256|0|
|B/scores_manifest.json|1对象，files=2|120|files.path|0|
|reports/next_stage_20261019/gpu_scores_20261021/scores_live.csv|50|51|qid+rank|0|
|reports/next_stage_20261019/gpu_scores_20261021/scores_history.csv|50|51|qid+rank|0|
|T::session/receipt_a18_B_cross_stack.json|1对象|52|汇总回执|不适用|
|T::session/inputs/a18_qids.txt|1203|1203|qid|0|

S 每个 CSV 的行数已在上节逐文件列出；Q 每个预测文件的行数也已逐模型、split 列出。Q、S 指定文件均已打开，不是依赖汇总文件猜计数。普通 JSON 对象与私有数组不用排版行数定义样本量。不存在的入口无法报告“实际为零行”，故明确标缺。

关键原始文件 SHA256：

|文件|SHA256|
|---|---|
|`logs/B_predictions.jsonl.gz`|`df22ac5f70ce127629dbc807fd389af32282613c3d95815a68fe20760bf63c38`|
|`reports/v1.10.1/quality.csv`|`161b5d1f15abe1e9f1b4db74812b90d2533874336b8d2513a90e01294e3f2a4d`|
|`reports/next_stage_20261019/error_partition_20261021/join_v2.csv.gz`|`9c31fa7ee5d745085af7fe541d2bd4955566ea0abbf7c71ef559944097931712`|
|`reports/next_stage_20261019/error_partition_20261021/partition_rows.csv.gz`|`970623c5e4d0a5b98145c80ac58a78fcbe25060a045b1940b617fb4982419946`|
|`reports/next_stage_20261019/quality_closure_20261021/fixed_rag_matrix.csv`|`22f73f3ba7d2d4090856ae6753183409f66cc8bfa2b0038cc538e910329f9e37`|
|`reports/next_stage_20261019/无自匹配检索_维度消融.csv`|`6585620fe1069aa7a9022d6308931a2d9e6e53d016b8112c2a198aab5234674f`|
|`logs/results_20261020/mmdocrag_evaluation_numeric_metrics.csv`|`09ec6a82b84a17d26c569cf3cc5368edcc33bb7b7a5346ad35c9a3eb3076f0be`|
|`reports/next_stage_20261019/gpu_judge_s3_20261021/judge/scores.csv`|`c905914883c333e8fc42ed34d63322a67088df2d3c678c998bdd156ade59bb63`|
|`reports/next_stage_20261019/gpu_cost_20261021/device_samples.jsonl`|`88927af9710678f757b66fb8953fbfe7461df40ce119d3b06689d601a3492db6`|
|`reports/next_stage_20261019/pixel_identity_18955_keys_20261021/pixel_identity_18955_keys.csv`|`7d51cf8e6b18e038cf7eeac0a88bf1cd8114a56af0fe529e8b687079fcdd4208`|
|D 私有逐题统计|`7500bd01710d074867cd520d3ee1b5b6307d1eb667eec66cbaeea13f4e96c8f3`|
|G 原始 judge 日志|`af25c028cafaf05a7d9dc2aeb0fab307a0d4cc03fc75aff5d3aaa2a0a357b6d1`|
|T::session/E3/requests.jsonl|`81a4d644922d96040b62de5f8944d3f2ae3577885f591e0b0c956a456bf77b28`|
|T::session/receipt_a18_B_cross_stack.json|`b4eeabba661010847ac0f65810acf54f1fc1ed0282d30aa478b5e6ce36a14f6a`|

Q 的每份预测摘要已与其 closeout 清单逐文件比对一致；不在仓库复制私有预测正文。S 的各 CSV 摘要与收货回执匹配。公开 B 评分样本的摘要与其 manifest 匹配。

## 验证与停止点

本次只新增本文件。未修改 a-side、冻结表、初稿或已有汇报；未开机、未训练、未运行推理、未重算 bootstrap。

按要求运行现有测试，实际输出：

```text
python -B -m unittest discover -s tests
Ran 157 tests — OK

python -B -m unittest discover -s analysis/next_stage_20261019
Ran 64 tests — OK
```

分析侧目前为既有测试加新增 `test_extrapolation.py` 的测试，不再是旧文档记载的 54 项；本次完整发现并运行，未删减到旧计数。运行使用已有 venv-519 与 mmdocrag-analysis-deps 依赖目录，未安装依赖。

**第一阶段停止点（历史记录）：** 用户现已接受以上地图；下文继续第二阶段，仍不提前给方向结论。

---

# 第二阶段：能耗补件、内部数字及原论文对照复核

**本次范围：完成能耗本分支复算、2.1 内部数字复核与 2.2 归档原论文对照；不开展第三阶段。** 上文是用户已接受的第一阶段快照，原快照文件 SHA256 为 `2d642195a04c709c3728ea022e9d514f5e7170c9089ec65314d44d2888fcb1d0`；其中“能耗文件缺失/尚未复核”等措辞指补件前状态，当前进展见本节。第一阶段原始观察未被覆盖或改写。

## 0. 能耗补件与方法对账

已新增：
- `reports/next_stage_20261019/gpu_cost_20261021/energy_summary.json`
- `reports/next_stage_20261019/gpu_cost_20261021/energy_summary.md`

原样本未改；筛 `power_W` 非空行，输入/有效样本均为 570，排除 0（新 JSON.`samples`）。样本均值 187.359491228 W、最小 31.25 W、**采样到的最大值** 312.17 W（新 JSON.`power_W`）；有效样本的窗口 83.541253090 s，显示为 83.5 s（新 JSON.`window.duration_seconds`）。

|计算/对账项|本次复算|状态与可写表述|
|---|---|---|
|实际时间间隔的梯形积分|4.357463724433 Wh → **4.36 Wh**（新 JSON.integration.energy_wh）|积分方法及线性插值假设明确；节点权重形式的独立算术检查一致；不是 A/B 两处独立实验|
|样本算术均值×窗口|4.347846298744 Wh → **4.35 Wh**（新 JSON.legacy_4_35_reconciliation.sample_mean_times_window_wh）|复得历史报告的两位小数；必须标“样本均值近似”，不能称实际间隔积分值|
|A 侧既有回执|已读取提交4312359的原JSON/MD；未舍入电量 **4.347846298744446 Wh**，与本分支均值法差值 **0 Wh**|**两处独立复算一致**，仅指同源样本的均值×窗口近似；源SHA、样本、功率统计、窗口端点/时长逐字段一致；不是两次独立测量|
|测量边界|只含约 **83.5 s 的 E3 pilot**（E.samples.epoch；新 JSON.scope/window）|GPU 功耗非整机；包括窗口内预热、热请求及间隔活动；不能摊成每题/每模型能耗或外推整个研究成本|

两种算法相差 0.009617425688 Wh（新 JSON.`legacy_4_35_reconciliation.trapezoid_minus_sample_mean_approximation_wh`）。不得调整公式来迎合 4.35。此后引用该数值应直接指向本分支新 JSON 的近似字段；若用实际时间间隔积分，则使用 4.36。

### A 侧原回执补充核验（关闭能耗来源待核项）

来源固定到分支 `a-side/next-stage-20261017` 的提交 `4312359cdfdb8e39352415b182893f613a07ebda`：

- `a-side/reports/gpu_cost_20261021/energy_summary.json`，SHA256 `3ffcd8f2272b8846077d64ba74fff0bd003ae14df82ceb43e06a5d16e3a64c15`。
- 同路径的 `.md`，SHA256 `f58fc7a21c61f93c9d09da72a6cb2ab3dabf5dab677c7eb925f3fcd5b5b44112`。

逐字段比较写入本分支 energy_summary.json 的 `legacy_4_35_reconciliation.field_checks`，原文固定链接见该JSON及配套MD；两份本分支产物彼此互链，均引用A原始回执。A记录的 `input.device_samples_sha256` 与本分支 `source.sha256` 相同；另两项 index_residency/switches 摘要也匹配。

A 的 `input.records_total/power_W_non_null_parsed/power_W_null_or_unparsable` 分别为570/570/0；与B计数相同。`stats.mean_power_W/min_power_W/max_power_W`、首末epoch和window_seconds均逐项完全一致。A说明中公式为均值功率×窗口时长/3600；未舍入 `stats.energy_Wh=4.347846298744446` 与B的 `legacy_4_35_reconciliation.sample_mean_times_window_wh` 完全相等，不仅是四舍五入一致。

因此写：**两处独立复算一致（同源原始样本、均值×窗口近似口径），电量约4.35 Wh。** 源相同意味着这不是独立采集的重复实验，也不能将A未计算的梯形积分混入该一致性结论。B保留4.357463724432720 Wh的梯形积分作为另一算法结果，不取平均、不覆盖任一数值。

过滤边界：A把空/不可解析功率计入排除；B排除空值、对非空非法值报错。当前570条均为有效值，因此保留集合完全相同；不宣称对假设坏输入的规则也相同。A/ B首末有效样本相同，窗口定义在当前数据上完全一致。采样到的最大值、仅E3 pilot、约83.5秒、GPU非整机等限制均保留。

## 2.1 项目内部数字复核

新增来源代号：

|代号|原始文件与本次使用字段|
|---|---|
|V|`reports/v1.10.1/paired_comparisons.csv`：model_key/split/comparison/n/delta_pp/ci_low_pp/ci_high_pp/method/resamples/seed/improvements/regressions|
|CI|`reports/next_stage_20261019/quality_closure_20261021/source_cluster_ci.csv`：comparison/left_model/left_strategy/right_strategy/delta_pp/ci_low_pp/ci_high_pp/holm_ci_low_pp/holm_ci_high_pp/components/resamples|
|L|`reports/next_stage_20261017/B_paper_table_evidence.csv`：evidence_id/paper/model/setting/metric/reported_value/unit/table_or_page/source_sha256/checked_at|
|PE|`reports/next_stage_20261017/B_paper_evidence.csv`：原论文摘录的设置、评分和复现边界；不能代替缺少的原表单元|
|PM|`reports/next_stage_20261019/quality_closure_20261021/papers_matrix.csv`：paper/reported_values/verified_numeric_cells/numeric_verification/reproduction_status/differences|
|MC|`reports/next_stage_20261017/B_mmdocrag_scoring_contract.md`：已归档的 scorer 静态审计，引用并集宏平均与论文模态平均文字定义的差异|

### 共同筛选和分母

主实验完整对照使用 M 中：
`stage=quality & split=frozen_test & condition in {S0,S1,S2}`，共 **15,495** 条（M.stage/split/condition）。

**S1 读数及命中诊断必须进一步筛 `condition=S1`，只取其中 5,165 条，即每模型 1,033 题。** 不能把完整对照记录数当作 S1 分母；求 S2−S0 等差值时，分别取对应条件并按同一 qid 配对。失败记录保留分母；M 的主表题号与 J 的题号集合一致。

|常用引用|本次从原始产物核对|判定|
|---|---|---|
|S2−S0 为 +4.65 至 +10.36 pp|从 M.correct 配对计数计算；与 F.`T2.*.S2_minus_S0_pp` 及 V 的相应行一致|通过；五模型均在该范围，V 既有描述性区间均不含零；不是统一聚类检验后的结论|
|S2−S1 为 +3.68 至 +11.81 pp|从 M 的对应条件与 qid 配对；与 V.`comparison=S2 − S1` 一致|通过；**F 未提供同名 T2 的 S2_minus_S1 条目**，引用 M/V，不能编造 frozen id|
|S1−S0 四模型无法与无变化区分|按 V 的既有区间逐行核查|通过，但只能使用 V 的场景分层配对口径；Gemma E4B 是描述性区间不含零的一个模型|
|Qwen3-VL-4B 策略观测排序|QS.`per_question.correct`、Q.`selection_strategy` 与 P 匹配：utility 623 > cosine 618 > random 615，各分母 1,033|数字通过；仅该模型、该题单的点估计排序；不是已建立可泛化优势。P3=dev 选中的 utility，非 random；P4=711 只作事后 Oracle|
|“检索天花板”516/1,033|逐行经 M 的证据角色别名与 A.occurrences 的 GT 身份核对，J.top3_gt_hit 一致；五模型该布尔序列完全相同|计数通过，名称需收紧为“本接口精确 GT 身份可得率”，**不是答案准确率上限**|
|索引交集4,282、缺430、其中GT15|重读 K.sha256_q95、T.pool.sha256、A.occurrences.role，与 F.index.intersection_q95/live_absent/absent_GT 一致|通过；当前语料的唯一图像身份，q95 同口径；GT15 不是题数或必然答错数|

下表各列的正确题数来自 M.`correct`；差值由配对计数计算，范围源为 F 的 T2 条目或 V。所有区间直接读取 V，**没有重新 bootstrap**。

|模型|S0 / S1 / S2 答对题数（各 n=1,033）|S2−S0 pp|S2−S1 pp|S1−S0 pp 与 V 的95%区间|
|---|---|---|---|---|
|Qwen3-VL-4B|621 / 595 / 717|+9.29|+11.81|−2.52 [−5.13, +0.19]|
|Qwen3-VL-8B|583 / 580 / 690|+10.36|+10.65|−0.29 [−2.61, +2.13]|
|Gemma4-E2B|375 / 366 / 441|+6.39|+7.26|−0.87 [−3.49, +1.84]|
|Gemma4-E4B|397 / 427 / 493|+9.29|+6.39|+2.90 [+0.19, +5.71]|
|Qwen3.5-4B|553 / 563 / 601|+4.65|+3.68|+0.97 [−1.74, +3.78]|

F 引用模板：`T1.{model}.{S0|S1|S2}.correct/n` 与 `T2.{model}.{S1|S2}_minus_S0_pp`；每行模型 key 依次为 qwen3vl_4b、qwen3vl_8b、gemma4_e2b、gemma4_e4b、qwen35_4b。S2−S1 用 V.`model_key/split/comparison` 定位。

### 区间方法不可混用

|对象|原始产物实际记录的方法|对现有说法的校正|
|---|---|---|
|官方共享证据主表 S1−S0、S2−S0、S2−S1|V.method=`paired_scenario_stratified_bootstrap`，resamples=2,000、seed=42；源码 `analysis/v1.10.1/reproduce_public.py:paired` 明示 `source_clustering=False`|不能写成“所有主表区间均为564组件聚类”；本表区间是题级、场景分层的配对重采样，无多重校正|
|无自匹配策略/路径比较|CI：564个图像关联组件、10,000次、seed=42；basic 区间和 family-adjusted 矩形投影区间分列|不能把 CI 的策略区间挪给主表官方 S1；Holm step-down p 与等同 Bonferroni 的矩形投影也不能混称更窄区间|
|条件比例分解| `decomposition_20261021.json` 的 interval/resamples/seed：题级百分位、10,000次、42|不是 V，也不是 CI；其字段提及 frozen cluster 不等于所有冻结主表区间都是聚类|
|场景命中后比例| `scenario_extrapolation_20261021.json.interval`：场景内百分位重采样、4,000次、42|零成功的退化区间不能读作总体成功率确定为零|
|预注册外推检验| `extrapolation_test_20261023.json.no_new_confidence_intervals=true`|该检验没生成新的置信区间，不能借用其他口径装饰其结果|

额外核对 CI 发现：未校正的十五项模型内策略比较中，十四项无法与无变化区分；Gemma E4B 的 utility−cosine 为 +2.710552 pp，basic 区间 [0.596983, 4.756983]。其 family-adjusted 区间为 [−0.759345, 5.907251]，无法与无变化区分（CI：left_model=gemma4_e4b,left_strategy=cosine,right_strategy=utility）。**“十五项均无法与无变化区分”应限定为校正后的区间**；`Requirements.md` R22 未明确该限定。

Qwen3-VL-4B 的 utility−cosine、utility−random、random−cosine 三个既有 basic 区间均无法与无变化区分（CI 的该模型三行），所以点估计排序不等于稳定策略优势。以上仅作范围/统计口径说明，不作为论文主张。

初稿 `paper_EN_v0.md` §3.6 的“所有区间统一聚类”与这些原始产物不一致。本次只登记修正要求，未修改初稿。

### 必须进入后续对照的四项口径

|已确认约束|原始证据|使用规则|
|---|---|---|
|S1 主表诊断的分母|M.stage=quality、split=frozen_test、condition=S1；逐模型 n=1,033|每个条件单独计分，再按 qid 配对；完整三条件的 15,495 条不作单条件分母|
|judge 正式分母|G.scores=1,000；G.raw=1,050，后者含 repeat=True 的50条|正式指标不含复评；N.judge_evaluated=False 保留早期导出原貌，不能据此否定 G；同一模型作 judge 的偏差保留|
|S3 四模型来源|M 中 Gemma 两模型开发/quality各子集；S 目录补跑 Qwen 两模型；各自 dev/holdout/frozen=5/2/29|合并说明来源与既定题号，不能称同一原始文件覆盖四模型，也不将性能重复加入|
|utility 两批数据|Q 的生成与 closeout 在前，T.utility 四维 dev 补分在后，source hash/时间绑定独立|既有策略结果与后补分分别报告；不写成后补分已产生端到端收益|

## 2.2 原论文对照：逐行核验

### 等级定义与原表完整性

本轮直接打开 L 与 PM，另用 PE 核对已归档设置；**未联网查原文，也未把 Markdown 的摘要趋势填成原表数值**。

- **已核（有页码/DOI）**：仅指 L 已记录原表单元核验且提供可定位的 PDF 页码/印刷页码，继承 `checked_at=2026-10-17`；并非本轮重新打开原文完成独立复核，更不是复现实验。当前满足此条件的是 Utility 与 VisDoM。
- **转引未核**：本轮可核归档摘录及其内部对应，但按当前要求缺页码/DOI。MRAG 与 MMDocRAG 的 L 行有 HTML 表号/源摘要，仍保守使用此等级；不得补造 PDF 页码或 DOI。
- **本项目实测**：仅用于 M/P/Q/QS/N/G/D 等本项目产物及本次对这些已有记录的算术复核，绝不用作原论文等级。
- **缺**：原表目标单元或本项目对应实验未归档/未开展。不以相关趋势、别的任务或别的条件补造。

L 实读36个单元、evidence_id均唯一；PM 的 `verified_numeric_cells` 合计36，逐个 P001–P036 均在 PM.reported_values 中找到，数值/单位/模型设置与 L 对应。该检查只核归档内部一致性，不把同源摘录互相引用当成独立原文验证。按上述页码判据，原表36行中18行继承“已核”、18行“转引未核”；其核验日期均为 L.checked_at 的2026-10-17。

**表中比较一律检查六维：题集、模型、评分、池、k、答案长度。** 原文未归档的答案长度写“缺”，不猜测等长或默认预算。下面每行“我方”列为本项目实测或明确标缺；我方主表来自 M/F/V，无自匹配策略来自 P/Q/QS，文档任务来自 N/G。

### 本项目文档任务读数（用于对照，不是冻结表条目）

N 逐模型200条、G 正式逐模型200条；由 `citation_f1/bleu/rougeL` 按固定分母取均值，judge 取 `Fluency/Citation Quality/Text-Image Coherence/Reasoning Logic/Factuality` 五维等权均值，不含 G.raw 的50条复评。引用F1乘100显示，词面指标保留0–1，judge保留0–5。

|模型|引用并集宏F1 %（N.citation_f1）|BLEU（N.bleu）|ROUGE-L（N.rougeL）|五维judge均值（G五字段）|
|---|---:|---:|---:|---:|
|Qwen3-VL-4B|52.17|0.1326|0.2921|3.672|
|Qwen3-VL-8B|50.71|0.1480|0.3098|3.764|
|Gemma4-E2B|44.41|0.0927|0.2645|2.838|
|Gemma4-E4B|60.72|0.1453|0.3075|3.545|
|Qwen3.5-4B|29.87|0.0982|0.2569|3.777|

N/G 的排序不能彼此替代。judge 与被评模型重叠，以上均值不作为独立事实性得分；不与作者 judge 的分数相减后声称能力差距。MC 已记录作者论文的模态平均文字说明与源码逐题引用并集宏平均不一致；本项目按后者投影，不冒称复现作者 Overall 列。

### L 的全部原表单元：原论文数值—我方—可比性

以下每行数值都来自 L.`evidence_id/reported_value/unit`，定位来自同一行 `table_or_page`。为了保持粒度，**逐单元列出，不把不同模型、数据集、指标合并成一个提升幅度**。

|ID / 论文 / 模型|原条件与报告值|核验等级 / 定位（继承核验日期见上）|我方对应读数或缺口|可比性：题集；模型；评分；池；k；答案长度|
|---|---|---|---|---|
|P001 / MRAG / Human|无RAG：38.47%|转引未核；HTML Table3；页码/DOI缺|S0五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；双方不使用证据池；k均0；原长度缺/我64上限。仅条件参照|
|P002 / MRAG / Human|CLIP检索：61.38%|转引未核；HTML Table3；页码/DOI缺|S1五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；CLIP检索池/官方候选；k原5(特殊1)/我3；原长度缺/我64上限。仅方向参照|
|P003 / MRAG / Human|GT证据：71.63%|转引未核；HTML Table3；页码/DOI缺|S2五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；均为金标证据；k均5(特殊1)；原长度缺/我64上限。无跨文排名|
|P004 / MRAG / Human|GT−无RAG：33.16 pp（绝对差）|转引未核；HTML Table3；页码/DOI缺|+4.65–10.36 pp（M/F/V）|题集1353/1033；模型异；作者解析/我strict；均为无证据到金标；k均0到5(特殊1)；原长度缺/我64上限。仅方向参照|
|P005 / MRAG / GPT-4o|无RAG：68.68%|转引未核；HTML Table3；页码/DOI缺|S0五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；双方不使用证据池；k均0；原长度缺/我64上限。仅条件参照|
|P006 / MRAG / GPT-4o|CLIP检索：68.96%|转引未核；HTML Table3；页码/DOI缺|S1五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；CLIP检索池/官方候选；k原5(特殊1)/我3；原长度缺/我64上限。仅方向参照|
|P007 / MRAG / GPT-4o|GT证据：74.50%|转引未核；HTML Table3；页码/DOI缺|S2五模型读数见§2.1；未测Human/GPT-4o|题集1353/1033；模型异；作者解析/我strict；均为金标证据；k均5(特殊1)；原长度缺/我64上限。无跨文排名|
|P008 / MRAG / GPT-4o|GT−无RAG：5.82 pp（绝对差）|转引未核；HTML Table3；页码/DOI缺|+4.65–10.36 pp（M/F/V）|题集1353/1033；模型异；作者解析/我strict；均为无证据到金标；k均0到5(特殊1)；原长度缺/我64上限。仅方向参照|
|P009 / Utility / Qwen3-VL-8B|MRAG零样本：59.35%|已核（继承）；PDF第6页/印刷35096，Table1|Qwen3-VL-8B S0=583/1033=56.44%（M/F）|题集1353/1033；同名8B、原revision缺，代理异；EM/strict；原GT富集池/我无自匹配top10；utility均取3，零样本无证据；原长度缺/我64上限。无跨文排名|
|P010 / Utility / Qwen3-VL-8B|MRAG utility选证据：67.55%|已核（继承）；PDF第6页/印刷35096，Table1|同名8B utility=616/1033=59.63%（QS/P）|题集1353/1033；同名8B、原revision缺，代理异；EM/strict；原GT富集池/我无自匹配top10；utility均取3，零样本无证据；原长度缺/我64上限。无跨文排名|
|P011 / Utility / Qwen3-VL-8B|Visual-RAG零样本：52.41（0–100 judge，非准确率）|已核（继承）；PDF第6页/印刷35096，Table1|缺：未做Visual-RAG对应实验；MMDocRAG不可顶替|题集原Visual-RAG374/我缺；模型与judge不匹配；原LLM评分非准确率；GT富集池/我缺；原utility取3或零证据/我缺；原长度缺。不可比|
|P012 / Utility / Qwen3-VL-8B|Visual-RAG utility选证据：63.77（0–100 judge，非准确率）|已核（继承）；PDF第6页/印刷35096，Table1|缺：未做Visual-RAG对应实验；MMDocRAG不可顶替|题集原Visual-RAG374/我缺；模型与judge不匹配；原LLM评分非准确率；GT富集池/我缺；原utility取3或零证据/我缺；原长度缺。不可比|
|P013 / Utility / Ovis2.5-9B|Visual-RAG零样本：52.67（0–100 judge，非准确率）|已核（继承）；PDF第6页/印刷35096，Table1|缺：未做Visual-RAG对应实验；MMDocRAG不可顶替|题集原Visual-RAG374/我缺；模型与judge不匹配；原LLM评分非准确率；GT富集池/我缺；原utility取3或零证据/我缺；原长度缺。不可比|
|P014 / Utility / Ovis2.5-9B|Visual-RAG utility选证据：63.24（0–100 judge，非准确率）|已核（继承）；PDF第6页/印刷35096，Table1|缺：未做Visual-RAG对应实验；MMDocRAG不可顶替|题集原Visual-RAG374/我缺；模型与judge不匹配；原LLM评分非准确率；GT富集池/我缺；原utility取3或零证据/我缺；原长度缺。不可比|
|P015 / MMDocRAG / GPT-4.1|纯文本固定20候选：68.3（0–100 F1）|转引未核；HTML Table3；页码/DOI缺|N：五模型29.87–60.72%（代码并集宏F1）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；原Overall与代码定义异/我并集宏F1；原固定20(8图12文)/我setting15原样候选；k非同口径；原长度缺/我512上限。仅画像|
|P016 / MMDocRAG / GPT-4.1|纯文本固定20候选：4.07（0–5 judge）|转引未核；HTML Table3；页码/DOI缺|G：五模型2.838–3.777（仅正式初评）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；judge身份/实现异，非独立事实性；原固定20(8图12文)/我setting15原样候选；k非同口径；原长度缺/我512上限。仅画像|
|P017 / MMDocRAG / GPT-4.1|多模态固定20候选：70.2（0–100 F1）|转引未核；HTML Table3；页码/DOI缺|N：五模型29.87–60.72%（代码并集宏F1）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；原Overall与代码定义异/我并集宏F1；原固定20(8图12文)/我setting15原样候选；k非同口径；原长度缺/我512上限。仅画像|
|P018 / MMDocRAG / GPT-4.1|多模态固定20候选：4.14（0–5 judge）|转引未核；HTML Table3；页码/DOI缺|G：五模型2.838–3.777（仅正式初评）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；judge身份/实现异，非独立事实性；原固定20(8图12文)/我setting15原样候选；k非同口径；原长度缺/我512上限。仅画像|
|P019 / MMDocRAG / GPT-4.1|BGE/original自主检索：54.4（0–100 F1）|转引未核；HTML Table7；页码/DOI缺|N：五模型29.87–60.72%（代码并集宏F1）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；原Overall与代码定义异/我并集宏F1；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P020 / MMDocRAG / GPT-4.1|BGE/original自主检索：3.53（0–5 judge）|转引未核；HTML Table7；页码/DOI缺|G：五模型2.838–3.777（仅正式初评）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；judge身份/实现异，非独立事实性；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P021 / MMDocRAG / GPT-4.1|BGE/clauses自主检索：57.5（0–100 F1）|转引未核；HTML Table7；页码/DOI缺|N：五模型29.87–60.72%（代码并集宏F1）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；原Overall与代码定义异/我并集宏F1；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P022 / MMDocRAG / GPT-4.1|BGE/clauses自主检索：3.71（0–5 judge）|转引未核；HTML Table7；页码/DOI缺|G：五模型2.838–3.777（仅正式初评）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；judge身份/实现异，非独立事实性；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P023 / MMDocRAG / GPT-4.1|multiple/clauses自主检索：59.9（0–100 F1）|转引未核；HTML Table7；页码/DOI缺|N：五模型29.87–60.72%（代码并集宏F1）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；原Overall与代码定义异/我并集宏F1；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P024 / MMDocRAG / GPT-4.1|multiple/clauses自主检索：3.79（0–5 judge）|转引未核；HTML Table7；页码/DOI缺|G：五模型2.838–3.777（仅正式初评）|题集原eval2000/我子集200；原GPT-4.1/我五小模型；judge身份/实现异，非独立事实性；原自主检索/我固定候选，无召回；原k缺/我固定setting15；原长度缺/我512上限。仅画像|
|P025 / VisDoM / Qwen2-VL-7B|Long Context：12.09（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；本行长上下文不取检索k/我缺；原长度缺。不可比|
|P026 / VisDoM / Qwen2-VL-7B|Text RAG：31.65（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原文本k7/我缺；原长度缺。不可比|
|P027 / VisDoM / Qwen2-VL-7B|Visual RAG：39.06（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉k5/我缺；原长度缺。不可比|
|P028 / VisDoM / Qwen2-VL-7B|VisDoMRAG：39.94（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉5/文本7/我缺；原长度缺。不可比|
|P029 / VisDoM / Gemini-1.5-Flash|Long Context：32.81（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；本行长上下文不取检索k/我缺；原长度缺。不可比|
|P030 / VisDoM / Gemini-1.5-Flash|Text RAG：35.31（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原文本k7/我缺；原长度缺。不可比|
|P031 / VisDoM / Gemini-1.5-Flash|Visual RAG：39.80（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉k5/我缺；原长度缺。不可比|
|P032 / VisDoM / Gemini-1.5-Flash|VisDoMRAG：44.03（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉5/文本7/我缺；原长度缺。不可比|
|P033 / VisDoM / GPT-4o|Long Context：32.78（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；本行长上下文不取检索k/我缺；原长度缺。不可比|
|P034 / VisDoM / GPT-4o|Text RAG：37.33（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原文本k7/我缺；原长度缺。不可比|
|P035 / VisDoM / GPT-4o|Visual RAG：49.02（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉k5/我缺；原长度缺。不可比|
|P036 / VisDoM / GPT-4o|VisDoMRAG：50.01（0–100 F1）|已核（继承）；PDF第7页/印刷6094，Table3|缺：未运行VisDoM，不以N的引用F1顶替|题集原2271查询/我缺；原模型/我缺；原词重叠F1含PaperTab特例≠引用F1；多文档池/我缺；原视觉5/文本7/我缺；原长度缺。不可比|

L 的 Human 与 GPT-4o 的 GT−无证据数值分别为33.16 pp与5.82 pp（P004/P008），是原表显示单元的**绝对百分点差**，不是相对百分比；不沿用摘要“%”的歧义写法。它们与本项目五模型的条件增益只可作设置背景，不能说本项目更接近人类或复现了 GPT-4o 增益。

另外，P006/P007 可作原表内算术：GPT-4o 的 GT−CLIP 为74.50−68.96=5.54 pp（由 L 对应单元计算，非摘要趋势）。这**不能填入 Utility-MRAG 缺失的 GT−检索原表单元**，也不改变跨论文不可直接比较的边界。

### PM 全部论文行复核及过时状态

|PM.paper|归档数字覆盖（PM.verified_numeric_cells）|当前等级|可比性与状态修正|
|---|---|---|---|
|Utility-Oriented Visual Evidence Selection|6，均对应L.P009–P014|已核（有页码，继承归档）|仅上述单元有核验；GT−检索、utility−相似度成对数值仍缺；作者surrogate未复现，不能写排序方向一致|
|MRAG-Bench|8，对应L.P001–P008|转引未核（按本次页码/DOI判据）|有HTML表号及摘要，缺页码/DOI；题集/模型/解析/候选数/长度不完全可比|
|MMDocRAG|10，对应L.P015–P024|转引未核（同上）|PM.reproduction_status的“not started; no external validation result”已过时；N/G已存在固定候选结果，但没有自主召回或跨集分格；作者完整流程仍未复现|
|VisDoM|12，对应L.P025–P036|已核（有页码，继承归档）|没有本项目对应数据集实测；不能拿MM的引用F1对齐VisDoM词重叠F1|
|RAGRouter|0；PM.reported_values明确“未核验；不填数字”|缺|题集：原为文本RAG/我MRAG；模型、评分、池、k、长度均无成对归档值；视觉适配与路由实验未执行|
|VQQP|0；PM.reported_values明确“未核验；不填数字”|缺|题集、模型、评分、池、k、长度均无本项目成对实验；图像降质未执行，不能以S3干扰替代|

PM 的六行中，“核验单元已归档”与“作者方法已完整复现”是两回事。PM 的部分状态仍停留在本项目后续实验之前，必须用原始产物更新叙述，不改写其历史文件。本轮只在本审计文档登记，不修改 PM。

### 对旧“我们 vs 原论文”说法的最终复核

|对照项|原论文归档能支持什么|我方原始数据能支持什么|结论|
|---|---|---|---|
|GT证据有效|L.P004/P008 的绝对差；转引等级如上|M/F/V 的同题金标条件增益|仅方向/条件设计层面可参照；不同模型题集不能比能力差距|
|Utility 的GT−检索增益|**缺**：L.P009/P010是零样本与utility，不是GT与检索|M/V 有S2−S1|不得用59.35→67.55冒充该比较，也不得用别篇的差值补格|
|utility优于相似度|**缺**：所归档Utility单元没有相似度基线成对数值|Qwen3-VL-4B点估计623>618>615；同名8B的utility616而cosine627（P/QS），非全模型同一排序|撤回“原文与本项目排序一致”的已确认说法；点排序不扩为普遍方法优势|
|MMDocRAG引用指标|固定候选与真实检索分别报告，作者GPT-4.1；Overall定义须谨慎|N五模型固定候选子集，有并集宏F1与词面指标；G另有judge|只作任务画像，不叫自主检索复现、跨集命中诊断或独立事实性验证|
|压维度几乎不损“上限”|**缺**：归档论文表没有同一维度成对比较|D历史缓存有四维any-hit/Recall/MRR及理论载荷|只能称历史池身份命中与载荷；不称答案准确率上限、等价性或实测系统节省|
|MRAG原文“未报可得率”|L只核了指定准确率表，没归档全文负面检索结果|J确实可计算命中×答对|只能写“已摘录原表未含该诊断”；不从摘录缺失推断全文从未讨论|

**第二阶段需携带的修正：** 六项常用内部点估计通过；“答案天花板”改用精确身份可得率；官方条件区间与无自匹配策略聚类区间分开；原论文缺项保持缺；4.35 Wh 限定为样本均值近似，A 原回执已逐字段核对且未舍入数值一致。未做第三阶段筛选。

### 本阶段来源指纹与保护项

|来源|SHA256（本次读取）|
|---|---|
|`reports/next_stage_20261017/B_paper_table_evidence.csv`|`5df03e02f1ac64c836563ac218153570e1017ea0f61d8c4a0ca5fdfe581fd6fb`|
|`reports/next_stage_20261017/B_paper_evidence.csv`|`60fad9530e7609d7db57ea86b6f4118040956cceaccef71c1fb66391cb0a4275`|
|`reports/next_stage_20261019/quality_closure_20261021/papers_matrix.csv`|`bb8edbc09e3abdbfcee0758dde305b8fbc013dd88ca56ed90cbfc1c9768f9a82`|
|`reports/v1.10.1/paired_comparisons.csv`|`04dc6783dbc865c2f26185d8ef6fc65083a91fb238e4f57efb12b824c53a046e`|
|`reports/next_stage_20261019/quality_closure_20261021/source_cluster_ci.csv`|`123cf31bf98cbab0d7638bbb7a71d36b6ad3a9b0935d40fa1c39b5ce36004629`|
|`logs/results_20261020/mmdocrag_evaluation_numeric_metrics.csv`|`09ec6a82b84a17d26c569cf3cc5368edcc33bb7b7a5346ad35c9a3eb3076f0be`|
|`reports/next_stage_20261019/gpu_judge_s3_20261021/judge/scores.csv`|`c905914883c333e8fc42ed34d63322a67088df2d3c678c998bdd156ade59bb63`|
|`reports/paper_20261021/draft/paper_EN_v0.md`|`370b79fde145dd82a63587baec9625b1fb8194d6e8ec0ed47c6a5609ab106b47`|
|`reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`|`73ae61317015ef4f1aacafc1d4c784008747183950bfd52ac4d36ad7ae544b42`|

新增能耗文件不写入 frozen_numbers.json，也不以新实验身份替换任何历史结果。本阶段不生成候选方向清单。

本次交付验证：主测试 `python -B -m unittest discover -s tests` 实际运行157项、OK；分析测试 `python -B -m unittest discover -s analysis/next_stage_20261019` 实际运行64项、OK（既有54项及已存在的10项外推测试）。未安装依赖或新增测试文件。另逐项检查36行原表单元完整性、等级计数、能耗落盘值与原样本算术一致性；冻结 JSON 与初稿 SHA256 仍与上表一致，原始日志仍与 F.source_catalog 指纹一致。`git diff --name-only` 无已跟踪文件差异；本轮新增两个能耗文件并扩展本审计，未改已有汇报或 a-side。

A 侧能耗原回执的路径、源摘要与公式现已补核，前述唯一待核项关闭。该更新只修改本分支能耗JSON/MD及本审计的对账状态，不改A侧历史文件或任何原始数值；第三阶段仍未开始。


