# B 批可移植复算

从任意干净检出根目录运行；PY 为有 NumPy/Pillow 的 Python。四个目录/文件变量必须由调用者显式提供，并先核实合法取得且确实存在。脚本不猜工作树布局，不读取 EDGECORAG_* 环境变量作为私有路径，不加载模型，不重解析回答。

```sh
$PY analysis/next_stage_20261019/audit_requirement_evidence.py --work-dir "$WORK_DIR" --metadata-dir "$METADATA_DIR" --export-dir "$EXPORT_DIR" --official-source "$OFFICIAL_SOURCE"
```

- `--work-dir`：原样私有 no-self 归档根，含 `continuous-complete-backup/`、`prepared/`、`corrected-protocol-scoring/`；其同级需有 `instance394-preflight/` 检索归档。复算逐份校验已钉住的哈希，不生成预测。
- `--metadata-dir`：已钉住官方元数据页缓存，含 `official-full-field-projection-v3/receipt.json` 和 `official-metadata-pages/`；这些私有 QA/gold 不入库。
- `--export-dir`：私有导出目录，含 `export_receipt.json` 与其 75 份成员。可由下列一条命令从私有元数据及公开已归档源重新导出到新目录。不是要求第三方拥有本机旧临时目录。
- `--official-source`：固定公开版本 `eval/score.py` 的本地文本文件。只读 AST 字段，不执行官方评分器。

```sh
$PY analysis/next_stage_20261019/export_official.py --metadata-dir "$METADATA_DIR" --out "$NEW_EXPORT_DIR"
$PY analysis/next_stage_20261019/fetch_official_source.py --out "$NEW_OFFICIAL_SOURCE"
```

官方源：https://raw.githubusercontent.com/mragbench/MRAG-Bench/4ae2241fdc5a9505f63dbae230e50a3097296af0/eval/score.py

SHA256：`06cf633e01af2504e791926eb86ddf6ff10c7050279ad184ed7c9889e96eb905`。获取脚本先校验字节再保存，已有缓存只核验、不覆盖；网络不可用且无合法缓存则标阻塞。不得拿其他版本替代。登记命令只含仓库相对路径及受支持的占位符，私有绝对路径只由命令行参数传入；缺参、路径不存在或类型不符会明确失败。

R30 完成范围是原样导出与固定官方 schema 的静态独立核验，**未执行官方 score.py**；不能引用官方评分复核或排行榜结论。公开仓库没有私有元数据/导出/原始输出，缺这些输入的第三方不能完成数值复算；此时审计必须失败，不能因哈希库存校验成功而冒称完成新分析复算。R03/R24 也需要上述合法私有归档。

完成度只取 status 列：已完成/已交付/已披露/已执行归完成，部分前缀归部分，后置及“未测或不适用本轮”归后置，待/未前缀归待补。R26“已执行”是执行交付事实，R18“不适用本轮”不属于本轮缺项；不读取 limit 改分组。
