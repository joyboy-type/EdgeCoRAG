# B 批修复验收

复验入口（从任意干净检出根执行；四个输入路径由使用者显式给出，定义见 docs/portable_requirement_audit.md）：

```sh
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

## 线性关系与保全

仓库实际已经是 34a7e6a → 61fe155 → e06fdfa → da1b91a。merge-base 为 34a7e6a，与“兄弟分支”描述不符，已先报告。没有重复 cherry-pick 或改写历史。52 个暂存文件逐字节与 61fe155 对应文件一致，已包含在历史中；因此保留后续修正，不以旧快照覆盖新版。原工作树仍保留52个staged文件，另有私有patch备份；逐文件SHA见 linearity_and_staging.json。旧 b-iface-20261021 标签不移动。A源码及产物没有修改。

## 审计与状态

已移除按 checkout 祖先位置猜私有根的逻辑，也不再用环境变量静默回填。登记命令保持相对脚本和占位符；绝对登记路径、未知占位符、缺参数、路径不存在/类型不符都被拒绝。官方 source 提供固定 commit 的公开URL、SHA与只下载/核验文本的获取脚本，从未执行官方score.py。无输入的负向审计按预期返回1，R03/R24/R30明确缺参，不冒称通过。

显式输入的本工作树审计 rc=0，errors=[]，warnings=[]；25条独立复算命令全部rc0。最终提交还需在新建干净检出上以显式输入再次验收，其输出与最终commit记录随用户交付回报保存。R03/R22/R24/R30本批保持原有带范围限定的完成状态，不新增提升；若最终复验失败，按用户指示恢复原状态，不打完成标签。计数仅按status列脚本输出：完成26 / 部分5 / 待补3 / 后置3；原始逐行输出见 completion_counts.json。Requirements.md与CSV一致。

## 117 与 79 对账

117来自logs/B_predictions.jsonl.gz：strict_choice_v1、S0/S1/S2主stage、含internal_holdout四split、20295全量槽位；79来自logs/results_20261020/no_self_scored_outcomes.jsonl.gz：同解析器、三策略三split、不含holdout、18045行。文件/条件/split/分母不同，非同一统计。仅计已归档parse_status，不重解析、不改失败分母。可复算JSON及源SHA见failure_denominators.json。

```sh
$PY analysis/next_stage_20261019/reconcile_export_failures.py --verify
```

## B2与已知阻塞

历史B2回执不改：identity.rule=null、dedup.by_identity=null。两者显式登记“A 合同待补”，不为通过schema而猜值。a20 matches_neither仅报4480 / 14243两个差值，不推断原因、内容缺失或可配对性。附加证据见B2_contract_gaps.json。B1仍“失败：清单口径缺陷，待A修”；B栈fp32敏感性、目标机线程与资源实测均待GPU。

## 缩减预算（假设、非实测、非申请）

不缩短原假设单次时长，只缩范围：E3从6轮降2轮，123生成请求（含3暖机），只是技术pilot，不能宣称正式P95完成；E5只保留smoke20×4维cosine共80请求，不选维、不跑frozen，dev150×4及frozen选中维度、utility选中维度后置。E0语料重建移出窗口，开跑前必须已有核验过的可转移fp32索引；否则停止，不能用bf16替代。

合计3774.59秒；较慢假设情景6949.18秒（含600秒保全），向上取整116分钟。硬窗口7200秒，T0+6600停工作、T0+7200硬停机。假设2.18元/小时，仅计算费：2.289元 / 4.214667元；120分钟硬窗口4.36元，不含未知附加费用。报价与实际UTC开机时间未知；所有数字不是性能实测或费用保证，不能进入GPU申请。

```sh
$PY analysis/next_stage_20261019/a_interface_budget.py --verify
```

## 自检

主目录123项 / analysis48项全绿（含9项新增回归）；发布扫描需在所有文件暂存后验收，a-side相对543de53与本批基线diff为空。未开GPU、未连接GPU服务器、未加载模型；旧预测/回执/测量字段未改。

## 独立复算命令返回值（本工作树实跑）

|登记命令（前缀均为 $PY）|rc|
|---|---|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R01`|0|
|`analysis/next_stage_20261019/verify_quality_closure.py --work-dir {work_dir} --artifact-dir reports/next_stage_20261019/quality_closure_20261021`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R04`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R09`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R10`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R11`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R12`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R14`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R15`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R16`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R19`|0|
|`analysis/next_stage_20261019/b_offline_closure.py --verify`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R23`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R25`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R26`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R27`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R28`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R29`|0|
|`analysis/next_stage_20261019/verify_official_schema.py --official-source {official_source} --metadata-dir {metadata_dir} --export-dir {export_dir}`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R31`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R32`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R34`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R35`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R36`|0|
|`analysis/next_stage_20261019/verify_requirement_evidence.py --id R37`|0|

## 本批关键产物SHA256

- `reports/next_stage_20261019/b_iface_fix_20261021/B2_contract_gaps.json`: `95dd65acc70a93ee06e3c2eb7508814178e584e13e2e0a464850fcfe2ed9c0be`
- `reports/next_stage_20261019/b_iface_fix_20261021/analysis_tests.txt`: `7edfcd335ddcba019952a540c05c8fe97c6ba42e49ab34fbeda3d8cd39b73f40`
- `reports/next_stage_20261019/b_iface_fix_20261021/completion_counts.json`: `9bdf343c1945541685ee9bc1b89d058324957296d05a59ee1e160d7f77e7d8d8`
- `reports/next_stage_20261019/b_iface_fix_20261021/failure_denominators.json`: `147a33d644d2ff13abe95f54f1197fbd24496ec036c499261192ef41326856c0`
- `reports/next_stage_20261019/b_iface_fix_20261021/full_tests.txt`: `a46c8849deba55b9dd8d989c2e3e692417dab980661ea01b7c261f553f3deab3`
- `reports/next_stage_20261019/b_iface_fix_20261021/linearity_and_staging.json`: `9620a1fde245a21c289b083dd94c5957ba63e514602b230624ff115b0ce44e39`
- `reports/next_stage_20261019/b_iface_fix_20261021/missing_roots_negative.json`: `f5afbe3f4cbca3383de34b1c90f4c210d9fb840a309b63e80a41682bbce81e67`
- `reports/next_stage_20261019/b_iface_fix_20261021/requirement_audit.json`: `4b5aba5d0caaebc932143a286546bce0f1eae096cbc664dff5241280f50c514c`
