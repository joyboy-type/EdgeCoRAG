# P2–P5：本批命令与输入边界

P1不重做；基线61b41e4，交付分支fast-forward须另等用户确认。只读A 4a60d75。所有命令从B仓库根执行，PY是已有NumPy/Pillow运行时；NEW_OUT必须是新目录。需要GPU的命令本批不执行。

|变量|显式所需输入|
|---|---|
|A_REPO|4a60d75（a-iface-20261021-fix7）的只读工作树|
|PROJECT|合法本地项目根，含round-1原始图片/向量归档和round-2部分回传|
|WORK_DIR|已冻结no-self私有归档根，含prepared/、continuous-complete-backup/、corrected-protocol-scoring/；其同级有instance394-preflight/|
|METADATA_DIR|冻结官方元数据页与official-full-field-projection-v3/receipt.json|
|EXPORT_DIR|当前75份私有导出，含真实choices/option_count与export_receipt.json|
|LEGACY_EXPORT_DIR|61fe155版原始75份私有导出，receipt SHA=d2b2c762a048208940485f02fe24f888f7f3d756a9602e490e91fd2d261baaf6；它早于choices/option_count新增，不以旧字段校验替代当前格式校验|
|OFFICIAL_SOURCE|固定公开score.py源码文本，SHA=06cf633e01af2504e791926eb86ddf6ff10c7050279ad184ed7c9889e96eb905；来源与获取命令见portable_requirement_audit.md，绝不执行scorer|
|ROUND1_ARCHIVE|私有round-1归档，SHA=4e0fdb7ab586d432381e9431deb0f5de8fec4f8556535defe9c7948b85938893，2886293字节|
|FROZEN_RECEIPT|由下列Git只读命令取出的61fe155公共历史回执；不含授权文件|

```sh
git show 61fe155:provenance/results_20261020/e2e_smoke_public_receipt.json > "$FROZEN_RECEIPT"
```

## P2

历史产物在 c77e91c 验证；当前钉住4a60d75，包含a17写verify.json弄脏树的修复。仓库实测两提交累计25文件差异，不能称“仅修a17”；原始diff存于新修复回执。A_commit是当前完整SHA，A_evidence_commit保留历史c77e91c完整SHA，新兼容性检查另记、不重写旧回执。

```sh
$PY analysis/next_stage_20261019/verify_a_release.py --a-repo "$A_REPO" --out "$NEW_G1_OUT"
$PY analysis/next_stage_20261019/round1_projection.py --project "$PROJECT" --out "$PROJECTION_OUT" --verify
python3 "$A_REPO/a-side/scripts/a20_validate_index_receipt.py" "$PROJECTION_OUT/G2_index_receipt.json"
```

G1四条原生CLI都在字节相同的B临时副本执行（A工具会写回执）；原A工作树不写入、不改源码。命令原文/rc与源文件SHA在P2_G1/G1_release_check.json。原始图像字节逐份hash核验，未解码、未重编码、未排序。五题CSV的sha256列保留归档image:*候选身份后缀，不是原JPEG字节SHA；二者18955/18955不同，不能重命名。历史/现场都为bf16，序列化float32不代表fp32编码；history分数未保存，live缺三题显式标missing_live_pending_GPU。

G2 schema/a20通过只表示合同检查通过：batch/normalization/tf32在运行回执中未记录；归档源码指定batch4/TF32false、缓存保存后才在ranking阶段float32重归一化，不能写成新运行观测。reconciliation始终pending，a20差值4480/14243仅照录，来源裁定待A。

## P3

```sh
$PY analysis/next_stage_20261019/thread_preflight.py --out "$NEW_THREAD_JSON"
$PY b-side/a_interface_runner.py --dry-run --a-repo "$A_REPO" --thread-evidence "$NEW_THREAD_JSON" --interface-verification "$NEW_G1_OUT/G1_release_check.json" --out "$NEW_DRY_OUT"
$PY analysis/next_stage_20261019/verify_a_interface_dry_run.py --a-repo "$A_REPO" --output "$NEW_DRY_OUT" --interface-verification "$NEW_G1_OUT/G1_release_check.json"
$PY analysis/next_stage_20261019/verify_official_export.py --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR"
$PY analysis/next_stage_20261019/verify_official_schema.py --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

Mac环境读回8；torch/BLAS unavailable，因此a12写unfixed；本机不能复现libgomp。目标机Linux的一行命令就是thread_preflight命令，仅获批GPU会话时执行，届时必须观测库线程一致才可进入正式基准。历史cpu_thread_warning=true保持，未再次改历史回执。

FP32/关闭TF32/后层归一化是代码合同与CPU stub验证，未做真实编码。utility只输出原始logit三列，top3/物化仍由A15。四图与pool逐行顺序由实际dry-run验证，乱序负例拒绝。整卡/RAM/能耗和未执行段都是unmeasured；CPU dry计时不当作正式成本。

## P4

统计头部：固定1033题、564查询图像关联分量，query-weighted bootstrap10000次seed42；报告未校正和Holm兼容保守联合区间（联合矩形与Bonferroni数值相同、step-down p另列），描述性/未预注册；跨零写“不能排除无差异”；Oracle单列post hoc，不是可部署收益。保持原分母和失败规则，不生成新预测/评分。

```sh
$PY analysis/next_stage_20261019/p4_reproduce.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --legacy-export-dir "$LEGACY_EXPORT_DIR" --official-source "$OFFICIAL_SOURCE" --archive "$ROUND1_ARCHIVE" --frozen-receipt "$FROZEN_RECEIPT" --out "$NEW_P4_OUT"
```

每个产物的命令、显式输入、SHA、实际rc见P4_reproduction/artifact_commands.csv；共享命令每组本次仅跑一次。30项中29项复验，1项blocked，整批rc2表示部分阻塞，不冒充全绿。缺输入仅阻塞相关组，其它组继续。

旧Q_requirement_evidence_audit.json保留原字节；原会话的完整登记/环境未全部版本化，不能精确重放。当前审计另交“双命令双rc”，不回填旧回执。历史源码表的current_sha列是当时61fe155快照，使用--source-snapshot显式重建，不能当今天工作文件的SHA。旧导出使用61fe155原校验器重放；当前导出另用新校验器验证，未放宽任何新格式判据。

## 双审计门禁

```sh
$PY analysis/next_stage_20261019/audit_requirement_evidence.py
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

裸跑rc1：缺私有输入（设计如此），含Explicit --work-dir is required。带四输入rc0、errors=[]、warnings=[]才是当前审计通过。counts只能来自report_completion_counts.py，只按status分组，不读limit。

## P5

```sh
$PY analysis/next_stage_20261019/p5_budget_options.py --out "$BUDGET_OUT" --verify
```

两个选项都“跳过E0并缩范围”，不在窗口内重建4712语料。未提供可转移fp32索引；4a60d75的a18原生CLI必先编码语料，无索引复用参数，所以完整E1也后置，不在B栈另起批敏感性实验。E2仅五题指纹，不计算live top10；E3仅固定A池的生成pilot，无现场retrieval全链成本/P95/索引驻留。E5仅四维smoke，不选维、不跑frozen。A保持E4；B将E3再降一轮、E4后置。费率和耗时是假设，费用不含未知附加费，不是实测、预算申请或开机授权；实际报价与用户授权未到，不能进入GPU申请。

既有9537244预算回执原样保留，逐字节复验须配9537244版本脚本；当前脚本只更新A源码能力版本说明，不改预算数字或结论。
