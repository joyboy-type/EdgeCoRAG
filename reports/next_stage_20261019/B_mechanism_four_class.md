# 四类机制：原定义保留，验收阻塞
复验：`$PY analysis/next_stage_20261019/b_offline_closure.py --verify`

源B_predictions.jsonl.gz为21927行，按原stage选择S0/S1主记录，smoke20/dev150/frozen1033固定分母，失败计错，未重parse。c类检索伤害只是S0正确、S1错误的关联差异，不是因果。

a为top10不含GT，b为top10含GT且错误，c为S0对S1错，d为小模型共享检索与大模型质量区间跨零且成本更低。原定义不是互斥分区：c可与a或b重叠，d为模型对质量/成本属性，不是单题补集。不能自定优先级把冲突隐藏。当前工作树无A pools/ranks和可用公开GT身份联接；a/b留空，未知不填0。c可算，d留空。CSV的60格不是已验收的四类分区，不能宣称回加1033通过；固定分母1033、公开564关联组只作题目身份边界。

D1的B_source_cluster_ci.csv/B_holm_summary.json是明确引用：15策略Holm兼容矩形均跨零，仅能写“不能排除无差异”；5个预定模型P3比较不跨零，且P3可能不同策略，不保证相同选入证据。它们不满足共享证据、配对同负载成本、等价/非劣效或因果判据。原S1候选与no-self D1也不是同一条件，禁止拼成替代论证。正式成本待GPU、接口待A。R21保持部分；不要新增Oracle可达收益。
