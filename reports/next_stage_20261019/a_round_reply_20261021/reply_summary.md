# A轮回应：本批结果

基线12f7886；本批全离线，只新增本目录，不改a-side、实现、历史回执或需求状态。

## 四项产出

- `sources_inventory.json` sha256 `7133fdc9a387608ad9e15dc6ddc8afe566cfbfdb3cbb13cb0218d7c107b0d747`
- `ranking_reply.md` sha256 `43c5742ead0caa2b089d571a3b81dee59f964fa5d3ac5ee6ab84d6db303b1d74`
- `reconciliation.json` sha256 `fb40d27e303903ba24a404f44c55e8e94eecc5b4128af42c5ce402ff2435e1ab`
- `cross_stack_budget.md` sha256 `67080e140e61a066a7c058a2f14ba5dca364262571ab062bcacfca0caf125ef9`

来源清单5条，索引文件2份，NPY shape分别为18955×768、1353×768。本次只读非图像元数据、NPY头及文件哈希；未打开私有图像，不重新验证图像字节，不编码/评分/排序。历史身份唯一性、语料编码耗时标“来自归档读数，未二次执行”。A的14475=1353+6357+6765及4712唯一内容为A提供，待A确认。

## 本次原始rc

完整输出见tests.txt、analysis_tests.txt、audit_bare.txt、audit_explicit.txt、publish_audit.txt；逐命令rc见command_rc.json、publish_rc.json。

|命令|本次结果|
|---|---|
|主测试discover -s tests|126 tests OK；rc0|
|分析测试discover|54 tests OK；rc0|
|裸需求审计|rc1：缺显式私有输入，fail-closed设计如此|
|四输入需求审计|rc0；errors=[]；warnings=[]；计数26/5/3/3|
|A侧逐跟踪文件sha256对543de53|90文件；diff=[]；rc0|
|新增/改动文件CRLF|files_with_crlf=0；rc0|
|双后缀检查|无*.json.json；rc0|
|publish audit|rc0|

四输入审计命令（变量必须显式指向合法现存输入；原始输出和rc在本目录）：

```sh
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

A的②不可满足：history50行分数全未保存，live只有20行有分数、30行待GPU；完整双边分数在本栈不存在，不是拒绝提供。替代交付5题×10行“有序无分”材料。原生a18命令可执行，但分数旁路仍需A交付；不把方案当已测。

## 待A确认

- 两套口径、14475/4712论文引用政策与各自证据；B不自行裁定最终口径。
- dedup.notes指快照唯一性，不是观察到的建库去重决策。
- 28份parquet构成与4712唯一内容的可复算依据。
- 相同候选身份映射和同池fp32相似度旁路导出；根因未定，等a18复跑同池分数落地。
- 4712图约26分钟的硬件/协议来源；与历史bf16锚点约5.6倍差异未证明原因。

归档原值1122.371070432011秒与本轮转述1122.377不同，以原始回执为准。2倍fp32折算及0.12秒/图是假设；本批未测e、不选预算门、不申请或启动GPU。

需求状态保持26/5/3/3；本批没有以新回应提升状态。
