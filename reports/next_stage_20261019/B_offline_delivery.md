# B侧离线收口 D1–D7

分支b-side/offline-closure-20261021；本批独立提交，不混入P1。为保留前批26项和52个待审文件，已在本地建立前置快照61fe155，原目录待审改动不动。P0/P1旧标签不变。本批标签frozen-20261021-b-offline仅标记离线批次，不是GPU授权或新fp32就绪版本。分支含前批未确认范围，因此不自动推送。
没有GPU/服务器连接、模型加载或实验重跑；只读小型README/API，未下载大数据。路径均相对B工作树，PY使用NumPy/Pillow运行时。D1/D2只需公开文件；D4/D7需要相同私有元数据/归档，公开包不含QA、答案、原始预测/图片或私有导出。实际UTC来源核验时间见source checks。

## D1 来源聚类CI与Holm

通过。只读公开18045条，1033题/564分量；10000次有放回seed42，题目加权。79解析失败保留计错，生成错误0，无重parse。族大小20：15策略+既有合同预定5个dev选择P3模型对。15策略均跨零，不能排除无差异；5模型对校正后不跨零（清单如下）。描述性、未预注册。Holm step-down p与保守联合接受域矩形分开；矩形数值等同Bonferroni basic区间，有限重采样近似。P3不保证相同选入证据，不作可替代或因果论证。R22保持限定完成。

```sh
$PY analysis/next_stage_20261019/b_offline_closure.py --verify
```

- `reports/next_stage_20261019/B_source_cluster_ci.csv` — SHA256 `23ee43c068ba791b719447f84e7f381b4a9a9aa4503bcc4567a41cbfd949f240`
- `reports/next_stage_20261019/B_holm_summary.json` — SHA256 `56d1f12c107f72aca5f8e09bfd5e5a3ae6ac8943ff9f66b790c3c63a03cc956a`

## D2 四类机制

部分完成、分区验收阻塞。原a/b与c可能重叠；d是模型对质量/成本属性，不是单题补集。不能自创优先级凑互斥。当前缺A pools/ranks与可用公开GT联接，a/b/d留空并标blocked，不填0。公开21927条按原stage取S0/S1；frozen每模型1033，c类计数按模型顺序为105/79/112/86/100。S1发布候选与D1 no-self不同，不能拼成替代证明。d引用D1校正区间，跨零只能写不能排除无差异，仍缺共享证据、同负载低成本与预注册非劣效/等价判据。R21保持部分，不声称四类回加1033通过。

```sh
$PY analysis/next_stage_20261019/b_offline_closure.py --verify
```

- `reports/next_stage_20261019/B_mechanism_four_class.csv` — SHA256 `6395b90d0995f70879417a6d0ac721f0c361a2d1e1a55350107da49d2294fdf7`
- `reports/next_stage_20261019/B_mechanism_four_class.md` — SHA256 `89e18ea2644fee7fc59048fd59179dddf949ebb172851ebbf71a49598c0fbb42`
- `reports/next_stage_20261019/B_mechanism_availability.json` — SHA256 `0f27d2e4207a90c4292ffaeca07df3781b4dedff809deb84957717e70369cb0d`

## D3 新记录政策

政策、代码与CPU合同通过；GPU实际采样未测。新成功/失败请求带recording，HFBackend从实际processor tokenize=False结果脱敏并存原UTF-8指纹。20ms与边界CUDA mem_get_info取整卡最大观测值，只是峰值下界；allocator独立保留。host RAM用MemTotal−MemAvailable，非RSS/容器独占。energy.status=not_measured、value=null只代表明确缺测，不能作为0或有效数据。旧rendered_prompt、整卡/RAM/energy/P95缺失不可回溯。新增采样/渲染开销改变后续运行条件，不能与round1直接并表。8项新增主目录CPU测试含失败保全和append-only；R20保持部分。

```sh
$PY -m unittest discover -s tests -p "test_b_*.py"
```

- `reports/next_stage_20261019/B_record_gaps.md` — SHA256 `65825a72e119475de55a488582c4bc86497d229bed26d31258de54229dc30be4`

## D4 官方格式导出

通过限定格式门槛。75文件、20295全量槽位、117解析失败原样保留；新增choices和真实option_count，独立核对源字段/顺序/错误。私有导出位于工作树外../private-official-export/submission_format，不入库；公开只放元数据回执。四种旧暴露cohort不是1353新盲测。固定官方score.py缓存SHA 06cf633e01af2504e791926eb86ddf6ff10c7050279ad184ed7c9889e96eb905，AST字段核验通过；未执行会重parse的官方scorer，不报告官方新得分。R30保持限定完成。

```sh
$PY analysis/next_stage_20261019/verify_official_schema.py --official-source ../../publish-20261021/quality-closure-20261021/official-score-4ae2241.py --metadata-dir ../../pre-experiment-20261018/final-readiness --export-dir ../private-official-export
```

- `reports/next_stage_20261019/B_official_export_receipt.json` — SHA256 `1f2ddd019a99aa5ea4e8146cf500cc2aaf5c1fa6b96275da2c1f7251fcb247ec`
- `reports/next_stage_20261019/B_official_export_validation.json` — SHA256 `74317455b88d51f5aeb8b6a198267d957f7cfd06a06a9f84ac933c5f4d186151`

## D5 MMDocRAG judge协议

仅协议，不运行。既有5模型×200=1000行judge_evaluated=False。固定judge/revision、盲模型身份、五个0–5序数维度、失败保留200分母、100重复一致性与50答案×2人人审。1100次完整judge调用含多次自回归前向，不等于一次tensor forward。条件成本1100×假设1/10/60秒×假设2.18元/小时=18.33/183.33/1100 GPU分钟，0.6661/6.6611/39.9667元；非实测、非当前报价、非区间预测，不含启动/加载/存储/保全。实际吞吐不可识别，未申请预算。README CC BY-NC、HF Apache与research-only冲突未澄清。未执行、不得引用语义准确率。按本批要求R06由待补变部分完成，依据既有无judge交付与本次协议；许可与语义仍阻塞。

```sh
$PY analysis/next_stage_20261019/b_offline_protocols.py --verify
```

- `reports/next_stage_20261019/B_judge_protocol.json` — SHA256 `f7c92d7406d7523fac49dae55e890d5e233610feb72880dd16ee96442be2b43a`
- `reports/next_stage_20261019/B_judge_cost_scenarios.csv` — SHA256 `61fd68e65047e31381948fa7db5891fa3ea0378fe78988ed4302f903c29b9442`
- `reports/next_stage_20261019/B_judge_feasibility.md` — SHA256 `da9d36e629f2cd3f682b9debdb617d586e911b23f5c13531d0ca0a92a81db0e2`

## D6 VisDoM可行性

仅可行性。固定revision README及仓库API返回200；requirements.txt返回404，license=null，上游五数据集权利待核。README声明2271queries/1277docs，未下载计数。PDF/OCR/向量库/PyTorch与可选检索模型依赖未锁定，不能报可执行。多文档自由问答/word-overlap F1与MRAG ABCD严格准确率不同，需另冻协议。缺页数、后端、上下文、吞吐，GPU小时不可识别，只列编码+检索+生成公式，不造范围。未开展复现，不再提升R06。

```sh
$PY analysis/next_stage_20261019/b_offline_protocols.py --verify
```

- `reports/next_stage_20261019/B_visdom_source_checks.json` — SHA256 `cf5d73e32620de8e928f9e616e6a1b10ed508b345e5a682da56c060e44aecb1a`
- `reports/next_stage_20261019/B_visdom_feasibility.json` — SHA256 `0065ad004a3dbabb4141b0d831b85ba36920a328660a44fdf5d8c213b583cceb`
- `reports/next_stage_20261019/B_visdom_feasibility.md` — SHA256 `ae8351a44ba075b430c538062e8ed76366ea3c02f9c4dca0b78e2e7a8a5ab136`

## D7 回执与pins

通过只追加验收。仅在公开回执增加source_archive；所有旧键逐项对照34a7e6a一致，cpu_thread_warning仍true。旧回执SHA 27109ba0b381e95614f77b659ffbaa8b73468e74529c7bfb002e6648e8b740ad保留。round1归档SHA 4e0fdb7ab586d432381e9431deb0f5de8fec4f8556535defe9c7948b85938893，14/14成员复算成功。任务称4个A pins，但回执实际只有2个，不虚报另2个。4个B源码快照均可从归档复算；当前run_candidate仍同pin，其余当前差异按完整表披露，不改旧pins。R35保持历史完成。

```sh
$PY analysis/next_stage_20261019/b_append_archive.py --archive ../../next-experiment-20261019/e2e-smoke-prepared/e2e-smoke-results-20261020.private.tar.gz --verify
```

- `reports/next_stage_20261019/B_pin_reproducibility.csv` — SHA256 `633f1a51b6c6ae4d0e2fd0f718ff66015b8f06099fdf00bd043719bfdfdfa3ec`
- `reports/next_stage_20261019/B_source_archive_validation.json` — SHA256 `48bb46b901a4bd9d15fe7ec616e0d90b2bf5cfb437fbc5f93e82ba2dd0248368`

## D1 校正后仍不跨零的完整清单

右减左，单位pp；P3仅dev150选择。

|左模型/策略|右模型/策略|差值|未校正95%|Holm兼容矩形|
|---|---|---:|---|---|
|qwen3vl_4b/utility|gemma4_e2b/utility|-21.975|[-25.929, -17.910]|[-27.736, -16.004]|
|qwen3vl_8b/cosine|gemma4_e2b/utility|-22.362|[-26.499, -18.064]|[-28.624, -15.884]|
|qwen3vl_4b/utility|gemma4_e4b/random|-16.263|[-20.329, -12.168]|[-22.591, -9.929]|
|qwen3vl_8b/cosine|gemma4_e4b/random|-16.651|[-20.823, -12.471]|[-23.217, -10.264]|
|gemma4_e2b/utility|gemma4_e4b/random|5.712|[2.051, 9.269]|[0.086, 11.123]|

## 关键pin逐项可复算性

|路径|历史pin SHA256|归档成员|当前是否相同|
|---|---|---|---|
|b-side/e2e_smoke.py|`f3538fbcaec2b7a7f17b7d280b3f8394b58ca013b1dfe387fb46130312908a03`|code/b-side/e2e_smoke.py|False|
|b-side/e2e_lease.py|`05bbb616431c4cd46216a107480567f0e41d00149a0cff5c09e082f1009ed418`|code/b-side/e2e_lease.py|False|
|b-side/model_adapters.py|`60cfc2d051a68646f2556b04bc134b6f06d7495d90de96ce103dfbc6f53b9c01`|code/b-side/model_adapters.py|False|
|b-side/run_candidate.py|`5e7870adc04fec937807e6ac9f6e5f12ad674d1b3f52ec0ee80290c27c1eabf5`|code/b-side/run_candidate.py|True|
|a-side/scripts/evidence_selection.py|`f0b9d3552ca4f038115a35b6adf18511e790c934f2ff7fe2046b8ed51c1c3088`|code/a-side/scripts/evidence_selection.py|True|
|a-side/scripts/independent_retrieval.py|`70aa9a910463f9c12352e371f2d999f967b6bbe884f6d8475f5d78234831c2ed`|code/a-side/scripts/independent_retrieval.py|True|

## 完成度与自检

本批前26/4/4/3 → 26/5/3/3（完成/部分/待补/后置）。仅R06待补→部分完成，其他status保持；status为唯一分桶权威，limit不参与。B_completion_counts.json含逐行原始输出。P1已发布基线22/6/6/3；前批四行提升未回退。
主测试109项全绿；analysis39项全绿；需求审计errors=[]、warnings=[]；发布凭证/禁止路径/超过5MiB三项干净。a-side与logs对P1零差异；历史回执只追加source_archive。CPU合同不证明真实GPU测量已完成。

```sh
$PY -m unittest discover -s tests -p "test_*.py"
$PY -m unittest discover -s analysis/next_stage_20261019 -p "test_*.py"
$PY analysis/next_stage_20261019/report_completion_counts.py
EDGECORAG_EXPORT_DIR="$PWD/../private-official-export" EDGECORAG_OFFICIAL_SOURCE="$PWD/../../publish-20261021/quality-closure-20261021/official-score-4ae2241.py" $PY analysis/next_stage_20261019/audit_requirement_evidence.py
python3 a-side/scripts/audit_before_push.py --worktree .
```

## 评分变化表

78/100与分项分数为用户内部参考，尚无冻结的可复算百分制换算函数。不能把预计70→85冒充本批实测；下表仅报实际证据变化，后分不伪造。

|交付|原参考分|本批实际新增证据|后分|
|---|---:|---|---|
|D1统计|约70|纯公开20配对，1033/564/18045对齐，两类区间齐全|未按百分制重评|
|D2机制|约70|60格可用性表，15格c类可核实，互斥分区与能力替代阻塞|未按百分制重评|
|D3同机smoke|62|新记录政策+8项CPU测试，历史峰值/P95未补造|未按百分制重评|
|D4代码/导出|80（总体参考）|75文件补真实选项数及独立源字段复验，117失败保留|未按百分制重评|
|D7源码交付|80（总体参考）|回执追加归档入口，14/14pins复算，实际2个A pins如实披露|未按百分制重评|

## 完成与阻塞

已完成可复算：D1公开统计、D3政策/CPU合同、D4格式与源字段核验、D5/D6协议/可行性身份、D7只追加与归档pins。
仍阻塞：D2互斥定义/GT联接/能力替代；judge许可与吞吐；VisDoM许可与可执行环境。
待GPU：正式同机四路径P50/P95/整卡/RAM/索引、缩维下游、正式固定RAG新增生成、Pareto、9B、VQQP、真跑judge。待A：原生pools/ranks与a12/a15/a18/selection_policy冻结接口，本批未改其脚本，也未向A发送消息。
