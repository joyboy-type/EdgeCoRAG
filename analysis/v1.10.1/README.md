# 本地统计复算

所有入口只做离线读取和统计，不下载、不推理、不连接服务器。`reproduce_public.py`仅用公开JSONL即可检查全部主键、严格抽取、计分、质量分母、跨模型配对差距、转移与质量成本表。

在仓库根目录，用已有Python运行：

```bash
python -B analysis/v1.10.1/reproduce_public.py --output-dir /path/to/new-empty-output
# 已有matplotlib时追加 --figures；只复算CSV无需第三方依赖
```

保有完整已验证本地archive者，可复核原始代码/矩阵/输入哈希并重算76份评分、所有批准的同模型区间、SQL与原图：

```bash
python -B analysis/v1.10.1/analyze_results.py --backup-root /path/to/verified/edgecorag-v1101-backup --output-dir /path/to/new-empty-output
```

依赖版本见requirements.txt。新输出必须在备份外且为空，原始备份不改。SQL文件用于该步骤生成的analysis.sqlite；数据库不重复上传。`results_analysis.template.ipynb`是清空输出的可运行模板，在环境中设置`EDGECORAG_BACKUP_ROOT`后执行；原来已执行且无错误的本地笔记本保存在原分析包，本模板不冒称已执行。

统计扩展是结果后的描述性分析，不改原计划/生成参数。跨模型比较显式按同条件、同split、同qid与版本配对，不绕过原analyze_batch.py的同模型安全限制。场景分层题级bootstrap2000次seed42，无来源聚类、多重校正、预注册等价或非劣效界值。
