# 第二数据集可行性：优先MMDocRAG，当前尚不进入执行

核验日期：2026年10月17日（Asia/Shanghai）。本轮只读公开项目说明、摘要／四篇学术论文全文、仓库／HF元数据和少量评分源码；没有读取外部QA数据文件、作者逐题预测、图片包、PDF语料或权重，没有推理或judge API调用。[逐来源URL、时间与哈希](B_public_source_checks.json)保留了核验范围。

## 结论

建议继续将MMDocRAG作为任务书P0第二验证集的优先候选，VisDoM为备选。MMDocRAG官方入口可访问，发布者明确列出数据与评分工具，但许可表述冲突、评分入口依赖及真实schema核验仍需解决。这里的“可行性准备”不是外部验证结果，也不是数据使用／再分发权利已确认。

## 1 MMDocRAG的已核实入口与规模口径

- [官方项目](https://mmdocrag.github.io/MMDocRAG/)、[论文摘要](https://arxiv.org/abs/2505.16470)、[代码仓库](https://github.com/MMDocRAG/MMDocRAG)和[HF数据页](https://huggingface.co/datasets/MMDocIR/MMDocRAG)均返回成功响应。
- 仓库核验提交为`2fd7505c6a576376b4a92aafaff6d87494765bb7`；HF元数据revision为`04b58dbc5c6c4955291124eed411b09114728061`，gated=false。可访问元数据不证明全部大文件已可完整下载。
- 项目页／摘要声明4055个专家QA；项目overview声明222份文档。这是已核对的发布者声明，尚未本地逐行计数或核验文档分组。
- 文件清单有`train.jsonl`、`dev_15.jsonl`／`dev_20.jsonl`、`evaluation_15.jsonl`／`evaluation_20.jsonl`、`images.zip`和`doc_pdfs.zip`。15／20对应候选quote设置，不应直接相加成独立题目数；真实qid重叠尚未核验。

HF文件元数据声明`images.zip`为2232606409字节、`doc_pdfs.zip`为1051966358字节，二者压缩体积合计3284572767字节，约3.06GiB。`evaluation_20.jsonl`为31610492字节。它们不是已下载大小或解压需求；图片解压空间、缓存、模型与中间产物仍未知，不能用3.06GiB作为完整磁盘预算。

## 2 许可存在具体冲突

| 来源 | 当前读到的内容 | 可以与不可以推断的范围 |
| --- | --- | --- |
| GitHub仓库API | `license=null` | API未识别许可证，不等于资源没有任何许可说明 |
| 仓库README License段 | Code License标识Apache_2.0；Data License标识CC By NC 4.0；同时写data and code intended and licensed for research use only | 有数据非商业／研究用途声明；还需核对适用对象与上游来源 |
| HF卡片YAML | `license: apache-2.0` | 与仓库的数据声明冲突，不能只选更宽松的一条 |
| 项目网页页脚 | CC-BY-SA 4.0网页许可 | 不自动覆盖数据集、原PDF、图像或代码 |

因此，将“数据许可未确认”细化为“**已有公开声明但冲突未解决、上游权利未核验**”。本轮不发布新数据副本，不向作者发消息。后续需取得一致的官方说明，明确研究使用、公开发布派生结果和再分发各自范围；若无明确依据，保留限制或更换候选。

## 3 评分源码已静态审阅，但未验证可运行

[eval_all.py](https://github.com/MMDocRAG/MMDocRAG/blob/2fd7505c6a576376b4a92aafaff6d87494765bb7/eval_all.py)显示：gold侧读取`q_id`、`gold_quotes`、`answer_interleaved`，预测读取`q_id`、`response`；通过文本`[数字]`与图片`(image数字)`标记抽取引用，计算quote选择F1、BLEU、ROUGE-L，并处理judge结果。这是从代码推定的必需字段，不是完整数据schema已验证。

已发现三处执行前必须处理的接口差异：

1. README称judge可选，但当前`get_jsonl_path()`在模型模式要求judge文件，自带路径模式要求同时给`--path`与`--path_judge`。不能声称不使用付费judge时原入口已开箱可用；后续若作无judge投影，应单独命名、记录代码差异并核验与原纯指标计算一致。
2. [eval_llm_judge.py](https://github.com/MMDocRAG/MMDocRAG/blob/2fd7505c6a576376b4a92aafaff6d87494765bb7/eval_llm_judge.py)的`setting`是位置参数，README示例使用`--setting`。本轮只记录差异，没有执行或调用API。
3. `calculate_all()`遍历`zip(gold_data,eval_data)`，会检查配对到的qid是否一致，却未在此前检查两表等长。未来适配必须先验证完整qid集合、唯一性、顺序和缺失状态，避免较短预测文件静默缩小分母。

MRAG的A/B/C/D严格解析与64token输出预算不能直接沿用为开放文档问答的有效测量协议。新任务需要明确答案／引文格式、生成预算、截断和空输出评分；新协议不能覆盖v1.10.1。若使用judge，还需固定judge身份、版本、提示、费用与不确定性，不以judge替代可复核的引用指标。

## 4 VisDoM备选

[论文页](https://aclanthology.org/2025.naacl-long.310/)及[仓库](https://github.com/MananSuri27/VisDoM)可访问，核验提交`2d809ac87360d54b0765e9be1cab75808d37642a`。README声明五个组成数据集、合计2271 queries和1277 docs，树清单存在`visdomrag.py`与`eval.py`。规模仍是发布者声明，不是下载后核验。

GitHub API仍为license=null，文件清单未见独立LICENSE；其PaperTab、FeTaTab、SciGraphQA、SPIQA、SlideVQA的上游权利需逐项核对。论文许可不自动授予仓库代码和数据再分发权。README涉及视觉与文本检索及模型API，需要新的依赖／输入／评分适配。本轮未读取QA内容或运行它。

## 5 进入下一步的顺序

1. 先解决MMDocRAG许可适用范围和上游来源，并固定代码与数据revision。
2. 后续数据使用范围明确后，先做最小数据／schema核验，确认qid、来源文档键、15／20版本重叠与各split规模；先于查看测试答案制定开发、审计暴露和最终评测规则。
3. 再处理评分适配，先用构造的非研究题输入验证重复qid、缺失预测、顺序错位、空答案、引用缺失和不等长文件；不执行生成。
4. 形成新预算、条件、模型与样本范围，再安排最小模型可运行性检查和正式外部评估。

本轮已完成四篇论文选定主表的[36行数值与设置核验](B_paper_table_evidence.csv)，以及[评分合同草案](B_mmdocrag_scoring_contract.md)。MMDocRAG原文声明dev2055/eval2000；15／20设置引用索引会重排，不能混用gold。固定候选池含gold，Table7把70.2/4.14列为perfect，与BGE原query54.4/3.53分开。

评分静态审查另发现Overall F1的论文描述与源码聚合不同、token缺失除零／缩分母、judge未做qid对齐及import时NLTK下载，详见[10项发现](B_mmdocrag_static_audit.json)。此前15项合成规格仅有草案；当前增量已实现独立适配器，云端T01–T14通过，Mac T01–T14通过，T15依赖未齐，详见下一节。原论文全部表格复现、真实schema、依赖可运行性、磁盘解压需求与外部结果仍未完成。R05保持部分完成，R06保持待补。

## 2026-10-17适配器与A交付增量

以上公开来源与许可结论保留。独立评分身份b_mmdocrag_nojudge_metrics_v1现已实现；云端仅虚构qid／quote／响应通过T01–T14，T15因nltk与rouge-score缺失未完整验证，Mac T01–T14实测通过，T15仍有依赖缺口。不import作者完整eval_all，只提取SHA固定缓存中两个无副作用函数AST对照；未调用顶层下载或judge。具体接口、源码身份和逐项回执见评分合同、static_audit中的adapter_increment及B_mmdocrag_synthetic_validation.cloud.json。

A@4dbeab85a0cef2cab8fc2fae928392bf14bc7994的语料与分组结论已读取：它们解除的是等待回执本身，不解除独立语料许可／版本阻塞；MMDocRAG可能存在文档分组仍是待真实schema核验的假设。真实QA、图片／PDF、研究答案与新模型均未读取／下载／运行；第二数据集验证未完成。


Mac实际合成回执：[B_mmdocrag_synthetic_validation.mac.json](B_mmdocrag_synthetic_validation.mac.json)，SHA-256：`c36348ae0c005908b89bf6d21b723f16830a060c67c7cd5f1b2dd332594bef28`。darwin／Python 3.12.14；T01–T14通过，T15因nltk与rouge-score缺失未完整验证；未自动安装或下载资源。
