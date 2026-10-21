# B侧接口接入复核：B1–B7

结论：不能进入GPU申请。B1原始校验仍失败；B2来源对账与schema未知字段未闭环；B栈a18及目标线程值未测。本批没有GPU、服务器连接、模型加载、生成或评分，没有重复fetch，没有改A脚本/CSV/清单，没有回写历史结果。

B分支：b-side/a-interface-review-20261021。A只读工作树HEAD=89ddb29e61313b0875e33d45b9d55b654d3777ab；172个已跟踪文件前后字节完全一致，工作树干净。本批只在B目录追加提交，计划本地标签b-iface-20261021，不移动P0/P1或b-offline旧标签。

## 复验环境

命令从B工作树根目录执行。PROJECT指项目根目录，A指既有work/a-iface-20261021/EdgeCoRAG，R指本报告目录。PY指已有NumPy/Pillow运行时。B1-only只用标准库，可直接python3；B2/B3需要同一私有历史归档，不下载或发布原始材料。
```sh
R=reports/next_stage_20261019/a_interface_review_20261021
PROJECT=<项目根目录>
A="$PROJECT/work/a-iface-20261021/EdgeCoRAG"
PY=<已有NumPy/Pillow运行时python3>
```

## B1 原始失败与独立行尾复核

原始a17复现rc=1，artifacts_checked=36、fail_count=72（36个sha+size mismatch）。a17会写verify.json，因此用其原生EDGECORAG_IFACE环境变量指向B侧字节原样副本运行；脚本未patch，A源目录未写。原始日志保留，公开版本仅脱敏本地PROJECT路径。独立检查确认磁盘CRLF计数均0，每个文件恰少rows+1字节。

需纠正字面步骤：对当前LF文件做CRLF→LF不会改变字节，故直接与CRLF manifest比较仍0/36，不可能变36/36。本批在内存中将LF恢复CRLF，36/36哈希和大小与原清单完全一致，再归一化回磁盘LF完全一致；若不是纯行尾差异，脚本在任何B2/B3读取前中止。没有改清单、CSV或a17。结论：内容完好，仅清单行尾口径不一致，待 A 修。B1仍为“失败：清单口径缺陷，待 A 修复”。

```sh
python3 -B analysis/next_stage_20261019/a_interface_evidence.py --a-repo "$A" --out "$R" --b1-only --verify
```

- `reports/next_stage_20261019/a_interface_review_20261021/B1_original_a17_verify.json` — SHA256 `c694ac2cd3e0954eeb92d84d0a13997ba28c9dcbb5a536a999b7520cd5dfe8fb`
- `reports/next_stage_20261019/a_interface_review_20261021/B1_a17_stdout.txt` — SHA256 `74fa375f8c223496b0ebf0e050340859238919ea9fdb7558b61f00e18b1a5381`
- `reports/next_stage_20261019/a_interface_review_20261021/B1_original_invocation.json` — SHA256 `7d2482b80eda1ac2f083b46df231928f5f4806f9f312d5ea7c551a559c500201`
- `reports/next_stage_20261019/a_interface_review_20261021/B1_newline_proof.csv` — SHA256 `c54b5fcced3acb6d02d077fa0224370189b81fb405e0a9b96f44be897daa1048`
- `reports/next_stage_20261019/a_interface_review_20261021/B1_independent_check.json` — SHA256 `269b9114837daba0c4a61eb4cdc81d69cacf2235e55b26e983043a290fec2865`

所有A CSV引用必须带：`provisional: manifest 行尾口径待 A 修复`。独立内容证明不是B1原始校验通过。

## B2 索引构建回执

直接读归档npy头部为18955×768、存储float32；历史receipt编码dtype=bfloat16。已按backup-manifest复核向量与回执哈希，源controls哈希与round2 plan绑定、索引行序一致。不把存储float32写成fp32编码。没有原始字节/q95身份链、去重决策、构建commit等独立证据的字段留null；语料batch仅在绑定旧源码中为4，实际批回执缺失，字段留null并在B3参数中区分来源。

a20原脚本正常CLI返回0、errors=[]，但有告警：matches_neither，A工具计算delta=4480（对14475实例）、14243（对4712唯一内容）；只报上述差值，不下结论；两字段 identity.rule / dedup.by_identity 为“A 合同待补”。窄口径schema lint覆盖本合同使用的关键词，不冒称通用Draft7引擎；严格合同还有2处拒绝null：identity.rule、dedup.by_identity。不能为通过而猜值，也未改A schema。a20是必要子集校验，通过不等于完整schema通过。

```sh
$PY analysis/next_stage_20261019/a_interface_evidence.py --project "$PROJECT" --a-repo "$A" --out "$R" --verify
PYTHONDONTWRITEBYTECODE=1 python3 -B "$A/a-side/scripts/a20_validate_index_receipt.py" "$R/B2_index_receipt.json"
$PY analysis/next_stage_20261019/interface_schema_lint.py "$A/a-side/contracts/index_receipt.schema.json" "$R/B2_index_receipt.json" # 预期rc1、2个缺失证据类型错误
```

- `reports/next_stage_20261019/a_interface_review_20261021/B2_index_receipt.json` — SHA256 `d98695efd4a3f6ba92083d45546c615fe0a4212a4ea3da597a566d398e5ba468`
- `reports/next_stage_20261019/a_interface_review_20261021/B2_a20_validation.json` — SHA256 `615da1f3a4725d85f557dd4bd9051de32554595c1ddb632fd1837ead5f96d0fb`
- `reports/next_stage_20261019/a_interface_review_20261021/B2_full_schema_validation.json` — SHA256 `10cd723acf3ac01789b673b9cacc359eec84532c641958b019b85c134f78f79b`

## B3 五题历史/现场数据

history按已保存no-self ranks原顺序取5题各10行，50个排名/sha齐全；源文件没有分数，全部留空，不重新点积打分、不排序、不补造。round2部分归档仅有mragb:10/1049，按每题第一条已记录请求取20条live排名/分数；1051/1062/1117无live，30个缺失槽位明确标missing_live_pending_GPU。不能把100个表格槽位叫100条实测分数。

历史5题从query_embeddings.npy逐行按小端float32字节直接算SHA256；现场只有2题原先保存的float32序列化指纹，向量本体未保存。历史cache原输出与live后转float32归一化是不同序列化对象。双方模型编码均bfloat16、非fp32。现场batch=1；历史源码batch≤4；API normalize_embeddings=False与Normalize模块/后转float32归一化分开声明。torch2.8.0+cu128、torchvision0.23.0+cu128、Pillow11.3.0、transformers5.19.0来自旧setup；numpy旧版本未记录，保持null。

```sh
$PY analysis/next_stage_20261019/a_interface_evidence.py --project "$PROJECT" --a-repo "$A" --out "$R" --verify
```

- `reports/next_stage_20261019/a_interface_review_20261021/B3_history_live_top10.csv` — SHA256 `baebbdf806d5e7be3dd770b4479d23866c0e15f469a98504d9d5acba2cf3fdc9`
- `reports/next_stage_20261019/a_interface_review_20261021/B3_vector_fingerprints.json` — SHA256 `467b1c3423f6765d46520b67f7f43eae86b3ff00fb975fe2ee112745dc28d8f8`
- `reports/next_stage_20261019/a_interface_review_20261021/B3_encoding_parameters.json` — SHA256 `b3fc29374d55abf330177e1f72de1436520cdd6bc8a59ee4952fd808dc98b1d4`

## B4 CPU线程收口

7个子进程敌意环境全部执行：abc、空串、0、-1、4.0、空格4均识别为非法，正常8识别合法，按计划/cgroup封顶后覆盖，环境读回8。torch与threadpoolctl本机没有，torch_intra/torch_inter/blas_pools/blas_matches_requested明确unavailable，未跳过或填1/8代替库实测。新a12 dry-run因此用hardware.cpu_thread_env="unfixed"，并保留preflight环境读回8；a12_observed是记录器规范化回显，不是独立库线程探针。a12自动标技术联调，不进正式基准。

新thread_measurement.schema.json lint通过；非法字符串、quota封顶、apply失配、BLAS失配、interop非1拒绝等测试通过。历史receipt相对e06fdfa只有新增cpu_thread_warning_note；warning仍true，round2 thread-configuration文件不改，inherited全null事实只引用来源SHA。本机macOS不能复现目标libgomp告警；目标库有效值和告警验证待获批GPU会话。

```sh
$PY analysis/next_stage_20261019/thread_preflight.py --out <新的线程JSON>
$PY -m unittest discover -s tests -p test_thread_preflight.py
$PY analysis/next_stage_20261019/interface_schema_lint.py b-side/contracts/thread_measurement.schema.json "$R/B4_thread_provenance.json"
```

- `reports/next_stage_20261019/a_interface_review_20261021/B4_thread_preflight.json` — SHA256 `155c07341d7ea260aa4d0c5fe022986d3d5a3666d90ce7f8b81b7d22c1c375f7`
- `reports/next_stage_20261019/a_interface_review_20261021/B4_thread_provenance.json` — SHA256 `acd8c8a222d55db12f0f93fd004c41df82b9e66e9e0275ca2c6dbb142f558f1a`
- `reports/next_stage_20261019/a_interface_review_20261021/B4_schema_validation.json` — SHA256 `aebb3fa8c9a017d9848baa957c46e54de0f757a85e4f103de1c44ae47b84749d`
- `reports/next_stage_20261019/a_interface_review_20261021/B4_receipt_append_validation.json` — SHA256 `8ec790e563eefbf892026a3a7b937f09fc45fcafb578b4c138d1ad4275aeff6c`

## B5 冻结接口的CPU接入

新B入口直接读取A pools，严格要求文件内rank1..10，绝不重新打分、排序或按sha重排。选入证据从A的select3文件逐slot消费，不把top10当top3。20个CPU dry-run请求，每题1查询+3证据元数据；独立反读持久化请求，与源CSV逐行、与A select3逐slot一致，打乱CSV或输出顺序均拒绝。没有物化/解码图片，也没有模型前向，不能当GPU质量或成本结果。

调用未改动的原生A a12作唯一外层；CPU只计selection_request_build_seconds，其余编码/排名/utility/生成/切换均unmeasured。资源API纯构造测试确认外部方法可接、allocator被拒绝，实际整卡/RAM/energy均unmeasured。回执含cpu_thread_env="unfixed"及thread_evidence。

未来编码适配明确torch.float32，编码前关CUDA/CUDNN TF32，采用A的image dict输入、float32层归一化；仅配置/CPU替身验证，实际EG2参数和前向未测，不能外推A栈0/1203。与round1 bf16不可比。utility辅助函数只导出qid,sha256,score三列、保持10候选顺序、原样保留ℓ(True) raw logit，记录input_order/batch；缺分数明确报错，top3及物化交A15。真实utility前向/模板绑定与GPU资源验收仍后置。旧v1.10.1 BF16入口与回执未改写。

```sh
$PY -B b-side/a_interface_runner.py --dry-run --a-repo "$A" --thread-evidence "$R/B4_thread_preflight.json" --out <新的B_DRY目录>
$PY analysis/next_stage_20261019/verify_a_interface_dry_run.py --a-repo "$A" --output <B_DRY目录>
$PY -m unittest discover -s tests -p test_a_interface_runner.py
```

- `reports/next_stage_20261019/a_interface_review_20261021/B5_dry_receipt.json` — SHA256 `8d04e7b9f402988330b04c535b18f9c8802403348ada63d7aa2ed66d0b880ebd`
- `reports/next_stage_20261019/a_interface_review_20261021/B5_a12_dry_records.jsonl` — SHA256 `fabc50231137c704148fda98a6b2cb3562b10b785d0e4eda9eb70d57140f7874`
- `reports/next_stage_20261019/a_interface_review_20261021/B5_pool_order_hashes.csv` — SHA256 `d8038fcaa59661bfa78db78a64358d0f1588090e27cfbb89de8dbe3158c3926b`
- `reports/next_stage_20261019/a_interface_review_20261021/B5_independent_validation.json` — SHA256 `000bd303e06d81af7fcb6c90f9ebc94d59f898e0fff49fd0736a614d3f493e03`
- `reports/next_stage_20261019/a_interface_review_20261021/B5_resource_api_contract.json` — SHA256 `2a46c467a30e8c9757033080815e8a3ec902116ec822d6978b4759f601a5ca4e`
- `reports/next_stage_20261019/a_interface_review_20261021/B5_missing_utility_negative.json` — SHA256 `8f825973c63bbb1d07d7ac44099aa6a840bdce5cf72b66e56bf72d0ac10f8840`

## B6 官方格式导出与回执补齐

原已验证75份投影字节原样复制到新的私有目录，不重parse、不修补、不重新生成回答或评分。全量15文件共20295槽位，117解析失败保留；另外60份split文件含三目标split及既有legacy holdout，仅原样存档，不新增holdout使用。公开仅脱敏回执，包含源预测SHA、行数/失败数、字段映射、本次原样导出UTC时间与代码SHA；原始第一次导出时间未记录，不冒称可回溯。源预测SHA df22ac5f70ce127629dbc807fd389af32282613c3d95815a68fe20760bf63c38。

真实choices/option_count、顺序、错误、原始字段独立反查通过。固定官方score.py缓存SHA 06cf633e01af2504e791926eb86ddf6ff10c7050279ad184ed7c9889e96eb905已只读AST字段核验；未运行官方scorer，未做官方评分/排行榜复核，不报告新官方分数。R30维持限官方格式导出的历史完成状态。

```sh
$PY analysis/next_stage_20261019/copy_official_export_receipt.py --source <已验证私有导出> --out <新的私有导出>
$PY analysis/next_stage_20261019/verify_official_schema.py --official-source <固定score.py缓存> --metadata-dir <已有official-metadata目录> --export-dir <新的私有导出>
```

- `reports/next_stage_20261019/a_interface_review_20261021/B6_export_receipt.json` — SHA256 `aaefd1e553b7da3a4d96b4b033c8b94bcf4415a8f4c176a051573c11bf01e984`
- `reports/next_stage_20261019/a_interface_review_20261021/B6_official_export_validation.json` — SHA256 `50ddd11ec018d066224bf14e44c494f2027d4deda0dbeda106145fedd81d2673`

## B7 回传、异议与预算

8项来源与SHA见下表/JSON，异议单列O1–O4。B栈a18未执行，只有schema来源身份，不伪造changed_order/total计数。按A原文保留跨栈任务，不用B6官方导出代替它。B版与A原文编号、旧悬空引用、选择规则和预算差异逐项登记。历史Q3按旧合同的最高dev计数选择结果不回改；未来A-native采用已交selection_policy，跨零仅能作为预先声明的并列决策规则，不能写统计等价、无差异或可替代。

本轮修复以缩小工作量控制窗口，所有单次时长沿用原假设，没有把假设改成实测：E1仍2406次编码，E2仍5次；E3从6轮降到2轮（123次含暖机），仅技术pilot，不得出正式P95；E4仍80次生成；E5只做一个模型的smoke20×4维、cosine共80次，不选维，dev150×4、frozen选中维度和utility选中维度后置。E0语料重建移出本范围，必须先有已核验可转移fp32索引，否则停止，不能临时省略或使用bf16冒充。

假设算术：3774.59秒，较慢情景6949.18秒（含600秒保全），上取整116分钟；硬窗口7200秒，T0+6600停止工作，T0+7200硬停机，至少600秒保全。假设费率2.18元/小时对应63分钟2.289元、116分钟4.214667元；7200秒窗口仅计算费4.36元，不含未报价存储等，当前报价仍未知。这是“假设、非实测、非申请”，B1/A合同/线程门槛仍阻塞，不构成开机授权。详见新 B_fix 报告；旧超限方案留在父提交历史中。

```sh
$PY analysis/next_stage_20261019/a_interface_budget.py --verify
```

- `reports/next_stage_20261019/a_interface_review_20261021/B7_eight_items.json` — SHA256 `7a017a017dfbb4a4c2ecd7c89e02b275e87251b45024b8388c8a934397449cac`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_objections.json` — SHA256 `fdd852a37052066546a356e639e87379fb6864588c11d154ce90992ca7143f9c`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_instruction_differences.json` — SHA256 `502061901d773c7a358d2791b3fae59149b95135a7b9b86f78380b6aa5bf0539`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_budget_derivation.csv` — SHA256 `7e023ff93c98372f15923dacd6abe649be5344e0b9c9f6e946a5f2b07eee208d`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_budget_summary.json` — SHA256 `c633931b703bd8cac4a5e3809e991f6ce5e53c4e9f2028947481fc1f79302b0d`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_budget_sources.json` — SHA256 `ce11ffce94aa4975156e3a5ba1f73f7083cd1b8833447386abd26cfa74197d9a`
- `reports/next_stage_20261019/a_interface_review_20261021/B7_a18_pending.json` — SHA256 `79b1c762190e1014c2ebe78882122efe47c81bb2b80f51b493d143d8ba64a9f5`

## A的8项回传

|项|内容|当前口径/状态|产物SHA256|
|---|---|---|---|
|1|a17 native CLI|失败rc1、36文件72项；B1不得记通过|`c694ac2cd3e0954eeb92d84d0a13997ba28c9dcbb5a536a999b7520cd5dfe8fb`|
|2|a06 corpus verification|a17仅能复算清单4712及digest；项目work未发现parquet，未执行a06，不冒充原parquet重建通过|`c694ac2cd3e0954eeb92d84d0a13997ba28c9dcbb5a536a999b7520cd5dfe8fb`|
|3|index receipt|18955x768 float32存储，bfloat16编码；a20只报4480/14243；identity.rule与dedup.by_identity为A合同待补|`d98695efd4a3f6ba92083d45546c615fe0a4212a4ea3da597a566d398e5ba468`|
|4|5q history/live rows|history50条排名无归档分数；live20条真实记录，另30缺失槽位；均历史bf16|`baebbdf806d5e7be3dd770b4479d23866c0e15f469a98504d9d5acba2cf3fdc9`|
|5|fingerprints and encoding params|history5+live2个指纹；缺1051/1062/1117；序列化float32不等于fp32编码|`467b1c3423f6765d46520b67f7f43eae86b3ff00fb975fe2ee112745dc28d8f8`|
|6|OMP effective evidence|环境读回8；torch/BLAS unavailable；a12=unfixed，本机不可复现libgomp|`155c07341d7ea260aa4d0c5fe022986d3d5a3666d90ce7f8b81b7d22c1c375f7`|
|7|source pins and receipt note|旧source_archive保留，历史14pin可复算事实不改；本次只新增CPU note，warning保持true|`8ec790e563eefbf892026a3a7b937f09fc45fcafb578b4c138d1ad4275aeff6c`|
|8|B-stack a18 receipt|未执行，待GPU；只读取schema，A的0/1203不外推到B|`79b1c762190e1014c2ebe78882122efe47c81bb2b80f51b493d143d8ba64a9f5`|

## 接口异议关闭情况

|编号|状态|证据与边界|
|---|---|---|
|O1|仍开放|B7_a18_pending.json；B栈未跑；A0/1203仅A栈|
|O2|已解决（选择流程已交付）|A_reference_pins.csv -> selection_policy.md；本批不选维；跨零作为并列决策不证明统计等价，历史合同不回写，未来须登记新选择协议|
|O3|已解决（资源API接口）|B5_resource_api_contract.json + B5_a12_dry_records.jsonl；CPU合同接受外部方法、拒绝allocator；真实整卡/RAM/能耗均unmeasured|
|O4|已解决（职责与参数接口）|A_reference_pins.csv -> a15; b-side/a_interface_runner.py; tests/test_a_interface_runner.py；B只交raw logit三列；top3/物化归A；未做真实utility前向或GPU物化验收|

## 与续发正文/A原文的差异

|补充项|A原文|执行口径|
|---|---|---|
|B4 CPU线程|③ 固定CPU线程|执行新敌意环境测试，历史告警只加note；a12实测库未知时unfixed|
|B5接口|⑤冻结接口|以interface_freeze为权威，直接A pool/select3/a12；只做CPU dryrun|
|B6官方导出|⑥是a18跨栈回执，原文无此导出任务|不把官方导出替代a18；导出按用户独立授权补齐，a18仍待GPU|
|B7八项回传|⑦表实际9项，最后一项是异议|前8项回传；第9项异议O1-O4单列，不漏项|
|补充预算|§4有旧5h/7.4元粗估|不沿用，逐阶段假设算术，不作为执行授权|
|A④悬空引用|称两个A脚本在任何分支不存在|旧描述过时，P0已有且pin相同，不补源码、不改旧pin|
|A新selection_policy|dev跨零作并列决策，P3并列优先较低在线成本|未来native流程遵守，跨零不作等价/可替代论断；不回改旧Q3最高dev计数选择结果，差异明确登记|

## 自检、状态与发布边界

主目录123项、analysis39项通过。发布扫描凭证/禁止路径/大文件三项干净；扫描通过不代表B1/B2领域门槛通过。requirement证据审计errors=[]、warnings=[]，status列计数仍26完成/5部分/3待补/3后置，未提任何需求状态；两份需求表同步。本批不是新质量比较，没有新准确率或置信区间。

B1原始a17仍rc1/fail72，B2完整schema仍2项缺失证据类型错误；这些领域门槛没有被单元测试全绿掩盖。A原始parquet重建未执行（项目work未发现parquet，不宣称本机所有位置均无文件）。目标库线程/a18/真实utility与资源测量仍待GPU。新GPU请求的预算与阶段范围也未冻结。

所有脚本一行复算入口已列上方；字段导出需私有归档，公开包不含原题/gold/原始响应/图片/向量npy/模型权重/私有归档。A原始172文件前后字节一致、A工作树干净，B侧a-side和logs对e06fdfa无改动；历史回执只有新增note。未重复fetch，不修改A行尾清单，不把它修成0失败。

本批仅本地提交/追加标签b-iface-20261021，不推送。当前不能进入GPU申请：至少需A重发清单、A确认索引来源关系与未知字段合同、完成语料可复算前置，并另行确定可执行的小范围预算；目标栈验证再由获批E阶段完成。

本轮可移植审计复验使用显式四路径参数，见 `docs/portable_requirement_audit.md`；无参数不能把私有归档项目标为复算成功。新结果见 `../b_iface_fix_20261021/`，先前环境依赖的审计日志只是历史记录。
