# 逐题结果与输入上下文

`B_predictions.jsonl.gz` 含全部 21927 条唯一 question-run，包括原始回答、严格抽取、错误计分、模型 revision、硬件、时延与显存。每条增加 task_id、split、gold、correct 和 context_key；原始生成字段保留。132 次格式失败全部计错。质量与 performance 由 stage 区分，后者不得计入准确率。

`B_input_contexts.jsonl.gz` 保存去重后的结构化输入、共享文本及图像相对路径与哈希。不含图像像素。它不是处理器实际渲染的完整 chat-template 字符串，后者当时未落盘，不能事后伪造为原始日志。

本地解压可得到任务书要求的 `logs/B_predictions.jsonl`。例如在仓库根目录运行 `python -c "import gzip,pathlib; pathlib.Path('logs/B_predictions.jsonl').write_bytes(gzip.decompress(pathlib.Path('logs/B_predictions.jsonl.gz').read_bytes()))"`。解压件已被忽略，避免重复提交。

数据来源 MRAG-Bench，revision 43620fde4044bb150e158c67ad7af6b6b11e1da2；数据集卡标注 CC-BY-4.0。请引用 Hu 等人的 MRAG-Bench。上游图像各自的许可不由此推定，图像未随本轮新增材料分发。完整原始 archive、attempts、旧版本失败记录在本地校验备份保留。
