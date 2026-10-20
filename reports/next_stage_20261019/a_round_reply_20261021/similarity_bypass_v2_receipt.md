# 分数旁路22列与18955 SHA清单追加回执

基线8d02df0；本批全离线。只改B导出器及对应测试，新增报告/清单；不改a-side、不用GPU、不读私有图像、不复制向量、不在真实向量上跑导出器。

## 字段与调用

固定22列见下方完整CLI合成样例。identity原样取实际lexsort键，与sha256独立；生产输入必须保留历史image_id口径，合成样例的a/b只证明并列规则。score先固定为np.float32，再精确展开repr和float.hex，不对十进制截断。k默认10，可用--k明确指定。

metadata新增必填normalize_locus、encoder_weights_sha256、model_revision、query_image_sha256。normalize_locus仅model_internal/post_cast_float32；weights及query图哈希需64位小写hex；query图哈希可为qid映射（多查询必须映射），单查询可用单值。缺失/unknown均拒绝，不能用存储float32代替编码dtype。self身份需存在于完整池中，实际点积含self，输出后仅剔除self。

```sh
$PY b-side/similarity_bypass.py --vectors "$NEW/V.npy" --queries "$NEW/Q.npy" --pool "$NEW/pool.csv" --qids "$NEW/qids.txt" --metadata "$NEW/encoding.json" --source live --k 10 --out "$NEW/live_scores.csv" > "$NEW/live_scores_receipt.json"
```

run_id由command_sha256前12位与实际UTC时间生成，记录在所有CSV行及stdout JSON回执。真实编码完成并保存对齐V/Q后才能运行上例；本批仅以下合成输入执行一次CLI。

## 本次CLI合成样例（10行，22列）

本次CLI rc0；run_id=`5794232fd068_20261020T123334092503Z`。上游版本、权重及查询图哈希均为显式合成fixture，不是实际模型记录。

```csv
identity,qid,source,rank,sha256,score_fp32,score_fp32_hex,dtype,tf32_enabled,batch_size,pool_id,k,sort_key_rule,self_match_removed,n_pool_scored,normalize_locus,encoder_weights_sha256,model_revision,query_image_sha256,stack_versions,command_sha256,run_id
a,q1,live,1,0000000000000000000000000000000000000000000000000000000000000002,0.8999999761581421,0x1.cccccc0000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
b,q1,live,2,0000000000000000000000000000000000000000000000000000000000000001,0.8999999761581421,0x1.cccccc0000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c0,q1,live,3,0000000000000000000000000000000000000000000000000000000000000003,0.800000011920929,0x1.99999a0000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c1,q1,live,4,0000000000000000000000000000000000000000000000000000000000000004,0.699999988079071,0x1.6666660000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c2,q1,live,5,0000000000000000000000000000000000000000000000000000000000000005,0.6000000238418579,0x1.3333340000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c3,q1,live,6,0000000000000000000000000000000000000000000000000000000000000006,0.5,0x1.0000000000000p-1,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c4,q1,live,7,0000000000000000000000000000000000000000000000000000000000000007,0.4000000059604645,0x1.99999a0000000p-2,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c5,q1,live,8,0000000000000000000000000000000000000000000000000000000000000008,0.30000001192092896,0x1.3333340000000p-2,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c6,q1,live,9,0000000000000000000000000000000000000000000000000000000000000009,0.20000000298023224,0x1.99999a0000000p-3,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
c7,q1,live,10,000000000000000000000000000000000000000000000000000000000000000a,0.10000000149011612,0x1.99999a0000000p-4,float32,false,16,sha256:57acfcdbf8855bc9880e38890ef4fafe1c2bc586b41adef2f0058e8bbf929229,10,"lexsort(-score, identity) ascending identity on ties",self,12,post_cast_float32,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,synthetic-revision,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,"{""numpy"":""synthetic-fixture"",""similarity_bypass_numpy"":""2.3.5""}",5794232fd0687371693618d4fb8c41d0ebc50c23bbd0506143e8c275b2e50e31,5794232fd068_20261020T123334092503Z
```

## 18955 SHA清单

输出index_18955_sha256.csv，仅sha256一列。来自校验过sha/bytes的归档JSON corpus[*].sha256，逐行保留源顺序；没有用image:*别名后缀代替原始源字节哈希。哈希字段为归档记录，本批未二次打开图像验证其内容。

数据行数：18955；含表头物理行：18956；唯一SHA：18955；bytes：1232082。

SHA256：`67193931a88000926753f338906fe60b75197c726e969c5fe294df22e7746a3d`。

自校验：CSV列名严格等于[sha256]、每行等于归档corpus对应字段、18955条全部为64位hex、文件sha/bytes现算；详见similarity_bypass_v2_validation/index_manifest_receipt.json。

## 本次实际验收

- 主套件132 tests OK，rc0（原129＋新增3）。
- 分析侧54 tests OK，rc0。
- 裸审计rc1：缺显式私有输入，fail-closed；仅R03/R24/R30缺参数，warnings=[]。
- 合成CLI10行×22列，rc0；不声称在真实向量上运行过。
- a-side90个跟踪文件对543de53哈希差异为空；本批新增/改动文件CRLF=0；无*.json.json。
- publish audit实际rc见similarity_bypass_v2_validation/publish_rc.json。

原始命令、rc与输出保存在similarity_bypass_v2_validation/。根因判定与需求状态不变。历史回执不覆盖；此回执是新批次。
