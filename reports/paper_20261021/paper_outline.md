> **状态：部分过时。** 本文件写于 judge / S3 / 两项分解之前，表图清单与贡献条目以 `WRITING_PLAN_V2.md` 与 `PAPER_EVIDENCE_REVIEW.md` 为准。

# 论文大纲（仅结构与证据索引）

## 写作约束与数字入口

- 本文件只列章节任务、表图规范、结论边界与待办，不写正文，不填占位数字，不新增实验或重新选择策略。
- 唯一已冻结数字入口：`reports/next_stage_20261019/p4_frozen_20261021/frozen_numbers.json`。引用按 `numbers[].id`，来源与筛选条件按 `source_catalog` / `selection`，禁止从显示精度反推原值。
- 补充分析入口：`reports/next_stage_20261019/order_diff_20261021/bf16_cast_ablation.json`、`reports/next_stage_20261019/order_diff_20261021/bf16_cast_ablation.md`；只引用本轮已记录的计算结果。
- 缺少已冻结映射的项目标 TBD，并注明现有输入路径和解锁条件；不在写大纲时填值、重算或扩充冻结表。
- 各表图区分“实测”“归档读数”“假设”；历史测量不写成本轮重测。百分比与百分点分列，描述性区间不改写成确认性推断。

## 一、引言

- 研究问题：共享检索何时帮助、何时伤害；候选证据排序稳定性与实际系统成本如何约束可部署收益。
- 贡献安排：冻结协议与失败保留；配对质量比较；命中—答对分格及伤害overlay；限定范围的排序与成本测量。
- 对应证据：T1–T3、T5、F1、F4；数字从冻结入口取，不在引言另造汇总。
- 拟议结论边界：观察到的互补性是讨论路由的动机，不是路由系统已被验证。
- **不能说的话**：Oracle可部署；检索天花板等于模型能力上限；本研究已建立可部署Pareto前沿。

## 二、相关工作

- 子节：多模态RAG与共享检索；证据选择及utility；路由与成本测量；干扰、数据关联与复现。
- 输入：`reports/next_stage_20261019/quality_closure_20261021/papers_matrix.csv`、`reports/next_stage_20261019/quality_closure_20261021/papers_numeric_evidence.csv`。
- 编排：任务、候选池、解析器、评分、成本边界逐项对照；作者报告与本机复现分开。
- TBD：最终参考文献条目与原文页码映射；输入为上述两份CSV的source/pdf及核验字段，未核验项不引数值。
- **不能说的话**：跨论文不同协议的数字可以直接排名；计划或可行性等于已复现；第二数据集已有语义准确率。

## 三、协议与测量

- 子节：S0/S1/S2的路径定义；S3配对干扰子集；no-self策略与post hoc Oracle；数据分割与选择边界；失败保留；统计和计时定义。
- 输入：`logs/B_predictions.jsonl.gz`、`b-side/configs/shared_visual_mcq_v1.json`、`reports/next_stage_20261019/quality_closure_20261021/dev_fixed_selection.csv`、`reports/next_stage_20261019/gate_a1_20261021/numbers.json`。
- 对照规范：S1基线路径与cosine/random/utility实验不是同一套条件；S2 GT路径与三策略Oracle分开。
- 统计规范：区分原S1配对区间与来源聚类bootstrap；保留各自重采样单位、区间方法、比较家族及校正信息，禁止混用。
- 计时规范：冷请求、warmup、热请求分开；编码/索引加载离线成本与在线延迟分开；按冻结定义引用“编码＋加载”的派生构建成本。
- 资源规范：nvidia-smi采样设备峰值与allocator峰值分开；索引CPU驻留与GPU模型占用分开；能耗标未测，不填零。
- 排序规范：固定池身份、self剔除、lexsort、fp32/TF32、bf16-cast容差及事后设定说明按F4证据复述，不调整判据。
- **不能说的话**：跨零等于无差异；描述性区间证明普遍因果；各家视觉token等价；采样峰值等于连续监测绝对峰值；派生构建成本是独立连续计时。

## 四、实验设置

- 子节：数据与图像身份口径；模型与revision；dev选择/frozen评估；GPU与软件栈；E3测量范围；第二数据集的证据边界。
- 输入：`b-side/configs/model_registry.json`、`reports/next_stage_20261019/quality_closure_20261021/dev_fixed_selection.csv`、`reports/next_stage_20261019/a_round_reply_20261021/reconciliation.json`、冻结入口的`index.*`及`source_catalog`。
- 数据编排：历史18,955仅作发布索引行数；当前语料和交集按各自身份口径引用；缺失查询图与GT分类不混成样本数。
- 成本编排：E3仅三模型、20题、每请求2 tokens；质量评估的池、split与成本pilot分别标注。
- 第二数据集输入：`logs/results_20261020/mmdocrag_evaluation_numeric_metrics.csv`、`reports/next_stage_20261017/B_mmdocrag_evaluation_report.md`、`reports/next_stage_20261019/quality_closure_20261021/mmdocrag_judge_feasibility.json`。
- TBD：最终主文环境清单的逐条排版；输入为冻结入口source_catalog所指`session/receipt_a18_B_cross_stack.json`、`session/encoded/encoding.json`及模型registry；不把不同会话的软件版本拼成同一环境。
- **不能说的话**：18,955是实例数；不同身份口径可互换；第二数据集已执行语义judge或可报语义准确率；E3可以代表所有模型、完整回答或完整成本路径。

## 五、结果

### 主表规范

| 表 | 结构与输入文件 | 口径及冻结引用 | 单位 | 是否描述性及待办 |
|---|---|---|---|---|
| T1 五模型×S0/S1/S2 | 行为模型，列为条件；输入：`logs/B_predictions.jsonl.gz`；交叉检查：`reports/v1.10.1/frozen_test_summary.csv` | `stage=quality, split=frozen_test`，每模型同一qid集，解析/生成失败计错并保留分母；引用冻结`T1.*` | 正确题数、分母、准确率% | 是，经验描述；不自行添加未登记区间 |
| T2 S1相对S0增益 | 输入：`logs/B_predictions.jsonl.gz`、`reports/v1.10.1/paired_comparisons.csv` | `split=frozen_test, stage=quality`，同模型同qid配对，S1−S0；点估计引用冻结`T2.*.S1_minus_S0_pp`；区间从原文件`comparison`及`method`定位，不能借用策略比较区间 | 增益pp；区间端点pp；改善/退化题数 | 是；TBD：S1描述性区间与冻结ID的最终登记映射，输入为本行两文件；未完成前不填区间数值 |
| T3 命中×答对分格 | 输入：`reports/next_stage_20261019/error_partition_20261021/main_2x2/main_table.csv`、`reports/next_stage_20261019/error_partition_20261021/main_2x2/receipt.json` | 四列：未命中但答对／未命中且答错／命中但答错／命中且答对；命中指共享S1 top3含GT内容，先检查五模型命中qid集合一致；引用冻结`T3.*`，伤害引用`harm.*`单列overlay | 题数、占比%；另列命中/未命中计数及分母 | 是；四格可回加分母，伤害overlay与四格重叠，不相加；不使用旧残余桶作“证据无关” |
| T4 cosine/random/utility策略对照 | 输入：`logs/results_20261020/no_self_scored_outcomes.jsonl.gz`、`reports/next_stage_20261019/B_source_cluster_ci.csv`、`reports/next_stage_20261019/B_holm_summary.json`；选择依据：`reports/next_stage_20261019/quality_closure_20261021/dev_fixed_selection.csv` | 同一no-self策略实验内按model/qid配对；冻结评估不重新选策略；报告原区间及已登记家族校正口径；Oracle不占可部署策略行 | 准确率%、策略差pp、区间pp、分母题数 | 是，未预注册；TBD：三策略点估计与来源聚类区间的冻结ID补录，输入为本行文件；不得借用T1的S1质量作为cosine结果 |
| T5 成本分解 | 输入：冻结入口及其source_catalog的`session/E3/requests.jsonl`、`session/E3/index_residency.json`、`session/E3/switches.json`、`session/encode_timing.json` | 列为encoder/preprocess/generation/e2e，冷请求与热请求分组；冻结`cost.cold_first.*`仅用于首冷请求；热generation/e2e引用`cost.<model>.*.P50/P95`；编码＋加载引用`cost.index_build_encode_plus_load_seconds`，单列离线成本 | 请求分项ms；离线构建/切换s；设备峰值bytes或十进制GB，标明换算 | 是，pilot；TBD：三模型热encoder/preprocess统计的冻结ID，输入`session/E3/requests.jsonl`；禁止用首冷值填热P50。分项非互斥核算，不能简单求和冒充e2e |

- T1/T2拟讨论：检索增益的模型差异；**不能说的话**：检索必然提升；S1负点估计自动证明检索有害的普遍因果；跨零等于无差异。
- T3拟讨论：证据命中与答对的联系、伤害overlay；**不能说的话**：未命中意味着模型不可能答对；检索天花板等于模型能力上限；伤害overlay与四格相加；“命中且答对”残余桶等于证据无关。
- T4拟讨论：同协议策略差异与post hoc空间；**不能说的话**：Oracle可部署；未跨零或跨零结果代表普遍替代；在frozen上改dev选择；把GT路径S2当成no-self Oracle。
- T5拟讨论：测量边界、冷热差异与设备驻留；**不能说的话**：E3可外推到完整生成或全部模型；视觉token各家等价；能耗已测；allocator峰值就是设备峰值。

### 主图规范

| 图 | 输入文件及视觉结构 | 口径、单位与描述性标记 | TBD与不能说的话 |
|---|---|---|---|
| F1 质量—成本 | `reports/next_stage_20261019/p4_frozen_20261021/pareto_points.json`、冻结入口；已有草图：`reports/next_stage_20261019/p4_frozen_20261021/pareto_quality_cost.svg`；双面板：质量—P95时延、质量—设备峰值显存 | 每点标模型、条件、来源文件、各轴实测/归档状态；质量%、P95 ms、设备采样峰值GB；描述性跨来源投影。标题/图注必须含“质量协议与成本协议不匹配，非已验证 Pareto 前沿” | TBD：同池、同质量协议的联合成本—质量点；现有输入见本行及`session/E3/requests.jsonl`，现有资料不足以形成匹配前沿。不能说：已经验证支配关系、部署前沿或质量提升必然省成本 |
| F2 S1增益条形＋描述性区间 | T2所列输入；每模型一条S1−S0条形，零参考线，区间方法与配对分母写图注 | 点估计引用冻结T2；条与区间均pp；描述性，不作确认性推断；不得截断横轴隐藏跨零 | TBD：与T2同步完成区间冻结映射，输入`reports/v1.10.1/paired_comparisons.csv`及`logs/B_predictions.jsonl.gz`。不能说：跨零即无差异；把T4的聚类区间套到S1−S0 |
| F3 S3干扰 | `reports/v1.10.1/s3_subsets.csv`、`logs/B_predictions.jsonl.gz`、`handover/docs/04_S3干扰证据规范.md`、`b-side/reception/all_20261016/frozen_test/S3.image_audit.json`；按已审查同qid子集画S3−S1并列覆盖率 | 同模型、同split、同配对子集；增益pp、配对子集题数、覆盖率%；描述性，暴露审查方式与子集选择 | TBD：按split审查记录绑定最终图中子集、区间及冻结ID；输入为本行文件，不填未登记数值。不能说：小子集代表总体鲁棒性；label-aware或模型辅助审查等于独立人审；S3可无条件并入T1总分 |
| F4 排序一致性 | `reports/next_stage_20261019/order_diff_20261021/bf16_cast_ablation.json`、对应md、`reports/next_stage_20261019/gpu_scores_20261021/scores_live.csv`、`reports/next_stage_20261019/gpu_scores_20261021/scores_history.csv`、`reports/next_stage_20261019/pixel_identity_18955_keys_20261021/pixel_identity_18955_keys.csv`；a18来源为冻结入口source_catalog的`session/receipt_a18_B_cross_stack.json` | 分面展示同池a18 batch对照、同保存向量bf16-cast、history/live跨池映射；变化题数或比例、相似度差、映射覆盖；各分母分开；描述性；保留事后容差说明 | TBD：图形编码与逐题标签排版，输入已列明。不能说：最终向量cast完整模拟bf16编码器；不同池差异是单纯数值误差；回退池差已证明全部根因；a18零变化可外推所有栈和池 |

## 六、讨论与 Gate 裁决

- 子节：post hoc Oracle相对dev固定路径的空间；S0/S1/S2互补及反例；假设路由开销与测量成本分离；Gate结论及复议边界。
- 输入：`reports/next_stage_20261019/gate_a1_20261021/verdict.md`、`reports/next_stage_20261019/gate_a1_20261021/numbers.json`、冻结`gate.*`、`cost.*`、F1/F4证据。
- 编排：沿用已记录Gate裁决，不因写作或成本pilot更新而自行升级；逐模型范围、模型子集范围与互补率所属模型明确区分。
- 复议条件：引用原Gate中事后设定的写作形态规则，不包装为预注册统计检验；未评估的路由策略仍标待证。
- **不能说的话**：Oracle可部署；互补率就是路由可回收收益；假设成本是实测；成本pilot已证明Gate可以转continue；跨零即无差异。

## 七、局限

- 数据与身份：历史索引、q95语料、跨池交集和缺失内容分列；**不能说的话**：18,955是实例数，或不同身份口径天然可交换。
- 统计与选择：描述性比较、关联分量、事后容差/规则、冻结集禁选择；**不能说的话**：跨零等于无差异；未预注册结果是确认性结论。
- 测量：E3只覆盖三模型、20题、每请求2 tokens，采样显存、CPU索引驻留；能耗未测；**不能说的话**：完整生成、所有模型或全部路径的成本已齐备；各家视觉token等价。
- 第二数据集：仅报现有数值/协议及许可限制；输入为实验设置所列MMDocRAG文件；**不能说的话**：第二数据集语义准确率、judge已执行或跨数据集能力已获验证。
- 检索与能力：hit/miss是检索覆盖描述，不是模型能力边界；**不能说的话**：检索天花板等于模型能力上限。
- TBD：将第二数据集许可清单中的开放项逐条绑定最终脚注；输入`reports/next_stage_20261019/quality_closure_20261021/mmdocrag_judge_feasibility.json`，不自行宣告许可问题关闭。

## 八、结论

- 写作任务：仅汇总T1–T5、F1–F4中有证据的描述，复述Gate状态和测量范围，不新增数字或扩大外推。
- 面向后续的条目：同协议质量—成本联测、完整生成成本、第二数据集语义评分及许可前置；列为待验证工作，不写成贡献。
- **不能说的话**：Oracle可部署；已完成通用路由或已验证Pareto前沿；第二数据集语义准确率已确认；能耗已测；E3短生成pilot可以代表完整论文成本结论。
