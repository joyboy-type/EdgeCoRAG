# EdgeCoRAG P2–P5 离线收口

P1不重做，基线61b41e4。提示词修订版另交；本批只改B侧，未改A、未改历史预测/回执/测量口径；不开GPU、不连接GPU服务器、不加载模型。下列“通过”均有本批命令与实际rc，完整输入定义和可复制命令见docs/p2_p5_explicit_inputs.md。

## 审计双回报与计数

- **裸跑rc=1：缺私有输入（设计如此）**，errors包含R03/R24的Explicit --work-dir is required及R30的Explicit --official-source is required。
- **带四个显式输入rc=0，errors=[]、warnings=[]**。不能只展示其中一次。
- status单一权威计数保持完成26 / 部分5 / 待补3 / 后置3，原始逐行输出见completion_counts.json。R07仍“待补 A侧”，只更新事实、证据和限制；没有新增状态提升。两份需求表同步。

```sh
$PY analysis/next_stage_20261019/audit_requirement_evidence.py
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

## P2：G1通过；G2合同检查通过、运行字段与对账仍部分；五题数据部分

```sh
$PY analysis/next_stage_20261019/verify_a_release.py --a-repo "$A_REPO" --out "$NEW_G1_OUT"
$PY analysis/next_stage_20261019/round1_projection.py --project "$PROJECT" --out "$PROJECTION_OUT" --verify
```

A=c77e91c。A工具会写回执，因此在字节相同B临时副本中原样运行，命令与源码哈希绑定；原A工作树前后字节一致，不patch工具、不拼装API输出。

|原生命令（在相同字节副本的根目录执行）|本次rc|原值|
|---|---:|---|
|`python3 a-side/scripts/a17_verify_interface.py`|0|{"artifacts_checked":36,"fail_count":0,"files_with_crlf":0,"hash_normalization":"LF"}|
|`python3 a-side/scripts/a17_verify_interface.py --strict-lf`|0|{"artifacts_checked":36,"fail_count":0,"files_with_crlf":0,"hash_normalization":"LF"}|
|`python3 a-side/scripts/a20_validate_index_receipt.py a-side/contracts/index_receipt.example.json`|0|ok=true, errors=[], computed.verdict=pending|
|`python3 a-side/scripts/a22_crlf_guard_test.py`|0|passed=8, total=8|

原始字节实测：18955文件逐份sha通过，唯一ID18955、唯一原始字节SHA18955、重复0；总核验字节3847169427。所有18955个image:*后缀都不等于源JPEG字节SHA，因此原文把二者等同的映射作废，保留原ID与字节SHA绑定，不改候选池。dedup.by_identity=true/kept_duplicates=0描述快照无重复，不伪称观察了构建去重决策。

|字段|本批实值与差异|
|---|---|
|identity.rule|sha256_raw_bytes：源字节逐份核验；image:*仍是另一套候选身份，不能把后缀当原JPEG字节SHA|
|dtype|npy存储float32；运行回执model_dtype=bfloat16，不是fp32编码|
|batch / TF32|运行回执未记录，保持未知；绑定归档源码指定batch4/TF32false，明确不作运行实测|
|normalization|运行回执未记；源码显示保存缓存后，ranking阶段才对各维float32重归一化；不能说保存的缓存已做这一步。缓存向量范数实测0.995809913..1.004714370|
|row_order|原始包行序与归档plan corpus_order逐位相同，18955行对应向量；未排序/重算排名|
|reconciliation|pending + notes，A仍待裁定；a20只照录4480/14243两个差值，不下原因或可配对性结论|

a20本次rc0、errors=[]，有原生warnings（完整输出保留，不删除）；schema lint本次rc0、errors=[]，仅覆盖实际用到的合同关键词，不冒称通用JSON Schema验证。运行字段缺失不因schema接受null而变成“已测”。

五题CSV精确五列qid,source,rank,sha256,score：history50行（历史分数全部未保存，留空），live20条已有分数，另30个槽位缺失；缺mragb:1051/1062/1117，标missing_live_pending_GPU。现场仅mragb:10/1049，bf16/batch1；历史指纹5个、现场2个，sha256(float32序列化)不意味着fp32编码。CSV的sha256列是归档候选image:*后缀，非源JPEG字节SHA；含义已在脚本/报告中声明，未重解析、未点积、未补分。

## P3：本地代码、原生dry-run、当前导出校验通过；真实GPU指标未测

```sh
$PY b-side/a_interface_runner.py --dry-run --a-repo "$A_REPO" --thread-evidence "$THREAD_JSON" --interface-verification "$G1_JSON" --out "$NEW_DRY_OUT"
$PY analysis/next_stage_20261019/verify_a_interface_dry_run.py --a-repo "$A_REPO" --output "$NEW_DRY_OUT" --interface-verification "$G1_JSON"
$PY analysis/next_stage_20261019/verify_official_export.py --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR"
```

线程7种环境本次rc0，环境读回8；本机torch/BLAS unavailable，所以a12=unfixed，不宣称正式线程已生效。macOS不能复现libgomp，目标Linux验证命令沿用thread_preflight，留待获批会话；旧cpu_thread_warning=true保留，历史回执未再改。

原生a12外层dry-run20题、每题4图，池逐行顺序独立核验rc0；source_status绑定本次G1与当前A源码哈希，不再引用旧失败回执。CSV重排拒绝由单测覆盖；持久化请求换序的独立CLI预期rc1，utility缺分数CLI预期rc1；完整实际rc见P3_command_rc.json。FP32/显式关TF32/float32归一化由代码与CPU stub验证，真实编码未执行；utility只导出原始logit三列，由A15选top3/物化。资源与未执行段写unmeasured，CPU dry时间不是正式成本。

当前75份导出、20295槽位与117解析失败本次反查rc0；真实选项数/choices检查通过，旧输出未修补，官方score.py只做固定版本AST字段核验，**未执行官方评分器**。117来自B_predictions的S0/S1/S2主stage四split含holdout，分母20295；79来自no_self三策略三split无holdout，分母18045，同strict_choice_v1，不能混为一个统计。

## P4：29/30原样复验，1项blocked

统计口径固定1033题/564查询图像关联分量、query-weighted bootstrap10000次seed42；未校正与Holm兼容保守联合区间（矩形与Bonferroni数值相同，step-down p另列），描述性/未预注册；跨零“不能排除无差异”。Oracle单列post hoc，不是可部署收益，不写因果。

```sh
$PY analysis/next_stage_20261019/p4_reproduce.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --legacy-export-dir "$LEGACY_EXPORT_DIR" --official-source "$OFFICIAL_SOURCE" --archive "$ROUND1_ARCHIVE" --frozen-receipt "$FROZEN_RECEIPT" --out "$NEW_P4_OUT"
```

本次整批rc2明确表示部分阻塞，不称全绿；29项所属命令rc0，1项旧Q_requirement_evidence_audit.json的原会话过程无法精确重放，命令rc2、blocked。当前审计双回报另交，不回填旧audit。冻结完成计数与status_changes来自61fe155矩阵/34a7e6a基线，分别原样重建rc0；旧源码表用--source-snapshot61fe155复验（14pins），不把当时current_sha当今天工作文件SHA。

首次使用新导出校验器对照旧回执不一致，核对发现旧61fe155导出没有后来新增的choices/option_count；改为显式冻结原校验源码与原私有导出重放，未修改任何旧行、回执、判据。当前新导出仍单独用新校验器验证真实选项数，不以旧验证替代新门槛。缺输入只阻塞相应组，不锁死其它组。

|产物 → 命令（前缀$PY，共享命令每组本次只执行一次）|rc|状态|
|---|---:|---|
|`C_fixed_rag_and_paths.md` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`D_mechanisms_and_concepts.md` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`E_papers.md` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`F_judge_feasibility.md` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`analysis_receipt.json` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`concept_mapping.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`concept_sensitivity.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`dev_fixed_selection.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`fixed_rag_matrix.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`mechanism_breakdown.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`mmdocrag_judge_feasibility.json` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`oracle_paired_differences.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`paired_differences.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`papers_matrix.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`papers_numeric_evidence.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`source_cluster_ci.csv` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`manifest.json` → `$PY analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|verified_recomputed|
|`mechanism_samples.csv` → `$PY analysis/next_stage_20261019/offline_interface_supplements.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021 --verify`|0|verified_recomputed|
|`O2_partition_and_Holm_references.csv` → `$PY analysis/next_stage_20261019/offline_interface_supplements.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021 --verify`|0|verified_recomputed|
|`O2_upgrade_limitations.json` → `$PY analysis/next_stage_20261019/offline_interface_supplements.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021 --verify`|0|verified_recomputed|
|`O4_measurement_gap_contract.json` → `$PY analysis/next_stage_20261019/offline_interface_supplements.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021 --verify`|0|verified_recomputed|
|`O5_interface_validation.json` → `$PY analysis/next_stage_20261019/offline_interface_supplements.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021 --verify`|0|verified_recomputed|
|`official_export_receipt.json` → `$PY analysis/next_stage_20261019/verify_frozen_export.py --snapshot 61fe155 --metadata-dir {metadata_dir} --export-dir {legacy_export_dir} --official-source {official_source}`|0|verified_recomputed|
|`official_export_validation.json` → `$PY analysis/next_stage_20261019/verify_frozen_export.py --snapshot 61fe155 --metadata-dir {metadata_dir} --export-dir {legacy_export_dir} --official-source {official_source}`|0|verified_recomputed|
|`official_schema_validation.json` → `$PY analysis/next_stage_20261019/verify_frozen_export.py --snapshot 61fe155 --metadata-dir {metadata_dir} --export-dir {legacy_export_dir} --official-source {official_source}`|0|verified_recomputed|
|`source_archive_supplement.json` → `$PY analysis/next_stage_20261019/append_source_provenance.py --archive {archive} --receipt {frozen_receipt} --source-snapshot 61fe155 --verify-json reports/next_stage_20261019/quality_closure_20261021/source_archive_supplement.json --verify-table reports/next_stage_20261019/quality_closure_20261021/source_pin_reproducibility.csv`|0|verified_recomputed|
|`source_pin_reproducibility.csv` → `$PY analysis/next_stage_20261019/append_source_provenance.py --archive {archive} --receipt {frozen_receipt} --source-snapshot 61fe155 --verify-json reports/next_stage_20261019/quality_closure_20261021/source_archive_supplement.json --verify-table reports/next_stage_20261019/quality_closure_20261021/source_pin_reproducibility.csv`|0|verified_recomputed|
|`Q_completion_counts.json` → `$PY analysis/next_stage_20261019/verify_historical_metadata.py --snapshot 61fe155 --artifact Q_completion_counts.json`|0|verified_recomputed|
|`status_changes.json` → `$PY analysis/next_stage_20261019/verify_historical_metadata.py --snapshot 61fe155 --artifact status_changes.json`|0|verified_recomputed|
|`Q_requirement_evidence_audit.json` → `$PY analysis/next_stage_20261019/verify_historical_metadata.py --snapshot 61fe155 --artifact Q_requirement_evidence_audit.json`|2|blocked|

## P5：两个假设预算选项，均不申请/不开机

```sh
$PY analysis/next_stage_20261019/p5_budget_options.py --out "$BUDGET_OUT" --verify
```

未提供已核验可转移fp32索引。静态检查c77e91c a18发现其总会先重编码整套语料，无索引复用参数。因此本批方案明确“跳过E0并缩范围”，E1完整a18也后置，不绕到B栈复测；E2只做未来五题指纹，live top10分数后置；E3仅固定A池生成pilot，不报实时retrieval成本/P95/索引驻留；E5只四维smoke，不选维、不跑frozen。

A建议后续总预算上限5元：E3两轮技术pilot并保留E4；B再砍至少20%：E3一轮，E4后置。它们是“假设、非实测、非预算申请”。所有单次时长沿用原假设，没有用缩短单位时间凑预算。

|选项|期望秒数|较慢假设秒数（含600秒保全）|较慢窗口/计算费（假设2.18元/小时）|硬窗口/计算费|
|---|---:|---:|---|---|
|A_cap5|2506.40|4412.80|74分钟 / 2.688667元|7200秒 / 4.360000元|
|B_cut20|1986.40|3372.80|57分钟 / 2.071000元|3600秒 / 2.180000元|

B较A的较慢情景再减23.5678%。A硬停T0+7200、停工作T0+6600；B硬停T0+3600、停工作T0+3000。两个方案均保留600秒保全，首次失败保全部分不重试，源身份/线程/授权/平台硬停机缺一不得开始。费用只含假设计算费，附加费和真实报价未知，5元/3元都不是已核实总价保证。

完整逐项“请求数×假设单次耗时→阶段秒数”见P5_budget/budget_options.csv。剩余阻塞：A对18955裁定、完整B栈a18、目标CPU/BLAS、语料原字节重建/许可与实际报价；不存在现成index时不在窗口内补建。

## 自检与交付分支

主目录126项、analysis54项全绿；新分析脚本都有复验命令。a-side/**相对61b41e4差异为空，原A c77e91c全部已跟踪文件SHA未变；历史logs/与provenance/差异为空。发布扫描在暂存所有新增文件后运行，实际输出随交付回报提供。

建议61b41e4 fast-forward到交付分支，但等用户明确确认；本批没有移动results/runtime-v1.10.1-delivery，也没有动原52个暂存文件。后续B批提交与标签只追加，不force。

## 分项产物SHA256


P2：

- `reports/next_stage_20261019/p2_p5_20261021/P2_G1/G1_release_check.json`：`b5868ee260c1837d5360c8f37cef72bd6c7a986b733881c567b74e534e9db767`
- `reports/next_stage_20261019/p2_p5_20261021/P2_projection/G2_index_receipt.json`：`8acbb615b3e29ec662e243e29617aab3388b3a958999339667129404a6a45ab2`
- `reports/next_stage_20261019/p2_p5_20261021/P2_projection/G2_measured_evidence.json`：`9b4c89f82f3ff4d2beda1a75151c5f9686af4551ec354d5829202c25151397f1`
- `reports/next_stage_20261019/p2_p5_20261021/P2_projection/five_query_top10.csv`：`47c152270a9545b02ca76efba5fdc5a5d787b43ed669143ebdf5481b77077054`

P3：

- `reports/next_stage_20261019/p2_p5_20261021/P3_thread.json`：`155c07341d7ea260aa4d0c5fe022986d3d5a3666d90ce7f8b81b7d22c1c375f7`
- `reports/next_stage_20261019/p2_p5_20261021/P3_dry/receipt.json`：`a452951d99ad34ef55c3d1a90bda8eec7e609c1e6512578d60ac33bae154be82`
- `reports/next_stage_20261019/p2_p5_20261021/P3_dry_verification.json`：`f14dc05fd843c9758cbc4344abb63a2022ff8fdae8d3f30e13cd8b6d0cfe1ec6`
- `reports/next_stage_20261019/p2_p5_20261021/P3_export.json`：`d436a2774b4eb9bda04e9f2341609ea66a630b1d705b6013049f3ed0544282b5`

P4：

- `reports/next_stage_20261019/p2_p5_20261021/P4_reproduction/summary.json`：`a0bd487add4b1c6e363eec1a62ca463ee0ecd662fbd97d0757c8a374affbab80`
- `reports/next_stage_20261019/p2_p5_20261021/P4_reproduction/artifact_commands.csv`：`0082a3a61a7b792509ff857e19ad7362c517e80e57bdbda48e88aae71572fcc4`

P5：

- `reports/next_stage_20261019/p2_p5_20261021/P5_budget/budget_options.json`：`fc7bf907102dac02556f17e7daf339242da30baf0b7449faf6f16e324368b047`
- `reports/next_stage_20261019/p2_p5_20261021/P5_budget/budget_options.csv`：`b78ba6f71ea35e9fb6477b327ba22e38dc25e0245a8f932067da5553c582e826`

离线批次完成至当前可闭环范围；P4保留1项blocked，其余缺口明确后置。**不能进入GPU申请；等待补齐前置与用户另行批准、开机。**
