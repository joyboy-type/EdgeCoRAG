# EdgeCoRAG §8：离线复算与工程前置

范围：本批未下载、安装、升级、连接服务器或加载模型。以下命令均在本批实际执行；原始rc见 `reports/next_stage_20261019/offline_gate_20261021/command_rc.json`。统计为描述性、未预注册；Oracle是post hoc上界，S2使用GT证据，仅为评估条件，不是可部署路径。本指南不宣称复现GPU质量/成本实验。

## 环境、权重与数据

`requirements.lock` 来自已记录回执与registry，未重新安装验证。B round2记录Python3.12.3、torch2.8.0+cu128、torchvision0.23.0+cu128、transformers5.19.0、Pillow11.3.0、CUDA runtime12.8、驱动595.71.05；驱动支持上限CUDA13.2不等于运行时版本。sentence-transformers6.1.0来自独立检索器import回执。NumPy2.5.4来自B metadata-only锁，缺运行时安装证据。不是在一套新环境中已验证的完整传递依赖锁；不得把A栈版本混入B运行时。

权重与版本：生成模型精确revision及各分片SHA256在 `b-side/configs/model_registry.json`，本次提取在 `reports/next_stage_20261019/offline_gate_20261021/environment_sources.json`。EG2固定 `google/embeddinggemma-2@914f7f89142e33e77833254d9c9b90c3cef7303b`；所选历史回执未记EG2权重文件SHA，未来运行必须提供实际本地文件SHA，不得使用示例或unknown代替。所有模型权重均不入库；本批没有重新取得或验证权重。

数据获取步骤：
1. 取得对应提交的公开仓库；Gate/错误派生只用仓库里的 `logs/B_predictions.jsonl.gz`、`logs/results_20261020/no_self_scored_outcomes.jsonl.gz`、匿名564分量表、R03及P5归档CSV。
2. 若要执行需要私有输入的需求审计，依 `source_manifest.csv` 中MRAG-Bench官方链接与许可取得原始数据及合法历史回执。所需四输入目录定义在 `docs/portable_requirement_audit.md`。原始QA/gold/预测、图片、向量、计划与租约不入库。不将公开聚合产物冒充原始数据。
3. 纯公开检出缺私有归档时，裸审计必须rc1。缺精确历史输入不能重造回执；本批未运行任何数据下载命令，因此不提供未经执行核验的下载/重建命令。完整GPU重建仍后置。
4. A依赖为另行取得的只读 `a-iface-20261021-fix7`，完整pin为 `4a60d758a7247d5922b03dd3f05bd8fa641d6b69`；不可替换交付分支中的a-side脚本。设置 `A_REPO` 后先核对pin，以下self-check是纯NumPy逻辑，不加载模型。

## 实际执行的离线命令

`PY` 指向已有NumPy/Pillow解释器；从仓库根执行。路径变量须显式指向合法已存在输入，不得把本机绝对路径写进登记命令。

```sh
$PY -m unittest discover -s tests
$PY -m unittest discover -s analysis/next_stage_20261019 -p 'test_*.py'
$PY analysis/next_stage_20261019/gate_error_analysis.py --verify --out reports/next_stage_20261019
$PY analysis/next_stage_20261019/audit_requirement_evidence.py
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
$PY "$A_REPO/a-side/scripts/a18_batch_sensitivity.py" --self-check
```

对应本次结果：138 tests OK/rc0；54 tests OK/rc0；逐文件复验rc0；裸审计rc1（缺参设计）；四输入审计rc0/errors=[]；A18 self-check rc0。四输入审计只复算/验证已归档证据，没有推理或重parse。

以下为本批实际运行的环境清单生成命令，两个JSON都是显式只读历史回执；输出必须是新目录。不要拿本机当前pip环境替代历史记录：

```sh
$PY analysis/next_stage_20261019/freeze_reproduction_environment.py --runtime-json "$ROUND2_SETUP" --preflight-json "$HISTORICAL_PREFLIGHT" --out "$NEW_LOCK_DIR"
```

## 编码前置的合成dry-run（实际运行，无图像/模型）

先用已入库的合成说明创建新fixture目录（`FIXTURE`必须不存在）：

```sh
$PY - <<'PY'
import os,json,csv
from pathlib import Path
spec=json.loads(Path('reports/next_stage_20261019/offline_gate_20261021/synthetic_fixture_spec.json').read_text())
p=Path(os.environ['FIXTURE']);p.mkdir();(p/'snapshot').mkdir()
(p/'snapshot/model.safetensors').write_bytes(b'synthetic-fixture-not-model-weights')
for name,rows in [('corpus.csv',spec['corpus']),('queries.csv',spec['queries'])]:
    with (p/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
PY
$PY b-side/encode_pool.py --corpus-manifest "$FIXTURE/corpus.csv" --queries-manifest "$FIXTURE/queries.csv" --encoder-dir "$FIXTURE/snapshot" --weights-file "$FIXTURE/snapshot/model.safetensors" --weights-sha256 7807e9375d4e292c8b66439cfee0d43f8d3d6f0f087bba24a9980dc8a174aedb --revision 914f7f89142e33e77833254d9c9b90c3cef7303b --out "$FIXTURE/never-created" --dry-run
```

实际结果：rc0；V_shape=[2,768]、Q_shape=[1,768]、dtype=float32、tf32_enabled=false、batch_size=16、model_loaded=false，未创建编码输出。上述合成权重文件不是可用模型，不得用于GPU计划。真实GPU命令仅作为未执行示例保存在工具docstring，不列为本指南已执行复现命令。初次手抄SHA错误的调用rc1已单列记录，修正为文件实算SHA后rc0，未修改校验或加载模型。

## 产物清单与校验

- `reports/next_stage_20261019/gate_a1_20261021/`：verdict.md、numbers.json、互补率CSV、逐文件manifest；三量来源筛选条件及SHA在numbers.json。
- `reports/next_stage_20261019/error_partition_20261021/`：五类操作分区、25格配对分量区间、21927行压缩标签表与error_type派生表、旧四类映射、缺口说明。未知GT关联不填推断；已识别0不表示真实发生率0。能力替代只为模型级未成立属性。
- `b-side/encode_pool.py`：未来fp32/TF32关闭/batch16向量包入口；本批仅假编码器测试与dry-run，不等同a18跨批回执。
- `requirements.lock`、本指南、`offline_gate_20261021/environment_sources.json`：记录来源与限制。
- `a_round_reply_20261021/reconciliation.json`：追加18955 SHA清单交A求交状态。异常低交集先核对raw SHA与alias口径，不能直接断言语料无关。

Gate/分区 `--verify` 重建到临时目录并逐字节比较所有文件；测试检查形状、fp32、TF32、归一化、缺revision/权重SHA拒绝。验收回执manifest含新增文件SHA256/bytes，目录不含权重、向量、原始图片或答案。预检参数/环境不全时必须明确失败。
