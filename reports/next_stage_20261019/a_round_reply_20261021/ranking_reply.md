# 排序差异回应

B3_history_live_top10.csv共100行；history的50行分数全部为空，status=archived_order_score_not_saved；live仅20行有分数，30行为missing_live_pending_GPU。“history/live各10行含分数”这份材料在本栈不存在，不是拒绝提供。

替代材料history_order_without_scores.csv为5题各10行“有序无分”候选身份、rank与status，逐行保留归档顺序。sha256列为image:*身份后缀，不能当原JPEG字节哈希。历史/live均为bf16，不称fp32。

1.27e-4／7.82e-4是相似度变化量的下界／上界（翻转给下界、不越界给上界），不是相邻分差。A的2.89e-4／8.81e-5／3.84e-3是相邻分差，两种量不可直接对撞。这些数值来自本轮交来的裁定，本批未重新评分。

1049那对间隔B池2.54e-4、A池2.89e-4；以B为分母差13.78%（约14%；以A为分母12.11%）。与“池不同”一致，但未证明，不能写成“已解释”。

## A可自跑的替代方案（待获批GPU阶段，本批不执行）

原生a18采用全语料fp32、TF32关闭、batch16与1。固定同一语料及行序、五题清单、同一候选池CSV并绑定sha256；先对齐两栈候选身份，不把B的image:*后缀当A的q95字节sha。两batch共享同一语料向量V，分别得到Q；用float32落盘同一冻结池各项相似度，旁路字段为qid,batch,rank,candidate_identity,similarity。旁路只读冻结池，不重排/重建池；A即可对被换对两行求分差，附池sha与dtype/TF32/归一化证据。

```sh
python "$A_REPO/a-side/scripts/a18_batch_sensitivity.py" --corpus "$CORPUS" --qids-file "$FIVE_QIDS" --dtype fp32 --batches 16,1 --weights-sha256 "$WEIGHTS_SHA256" --out "$NEW_OUT/receipt_a18_five.json"
```

这条是A可直接执行的原生回执命令，但原生CLI不导出逐候选相似度，单跑它不足以交出分差。**分数旁路导出器/完整落盘命令待A提供**；本批不改a-side，不冒称已有该能力。方案与未执行项分开记录。根因未定，等a18复跑的同池分数落地。
