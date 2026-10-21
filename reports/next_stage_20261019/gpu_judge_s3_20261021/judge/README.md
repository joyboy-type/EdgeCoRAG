# MMDocRAG judge 结果

judge = Qwen/Qwen3-VL-8B-Instruct @ 0c351dd0, bf16, temp=0, max_new_tokens=512

**五维（作者冻结 prompt 原文 evaluation_answer.txt）**：Fluency / Citation Quality / Text-Image Coherence / Reasoning Logic / Factuality，各 0-5。

**self-judge bias**：judge 模型也是被评五模型之一（qwen3vl_8b），该模型的分数存在自评偏差，须人工/外部复核，不可直接当客观语义准确率。

自洽性（50 条重复评）一致率 = 1.0；≥0.8，可引用。

本表为 judge 五维分数，**不与 MCQ 准确率混排**。
