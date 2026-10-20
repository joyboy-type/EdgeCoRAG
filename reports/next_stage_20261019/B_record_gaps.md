# 新运行记录政策与历史缺口
复验：`$PY -m unittest discover -s tests -p 'test_b_offline_batch.py'`

历史round1没有processor-rendered字符串、整卡峰值、系统RAM或能耗时间序列，不可回溯。既有结构化messages不冒充最终字符串；分配器峰值不冒充整卡；process RSS不冒充系统RAM；少量请求不能补造P95。旧输出/配置/预测和旧pins不回写，本批只追加source_archive定位历史源码。

后续e2e_smoke与e2e_cost成功请求增加recording对象。HFBackend实际调用processor tokenize=False生成字符串，删除所有message文本与图片位置后保存rendered_prompt.text；保存原字符串UTF-8 sha256，脱敏文本不能直接重建原始私有输入。后端不提供则status=not_recorded，绝不推断历史prompt。

原生运行以20ms周期与请求边界通过CUDA mem_get_info读整卡used_bytes；peak_vram_gb.value单位GiB，是最大观测样本、真实峰值下界，status=sampled，不是精确峰值。独立内存字段仍保留CUDA allocator。系统内存读/proc/meminfo的MemTotal−MemAvailable，含同主机其它进程与cache策略影响，非容器专有/RSS。energy.status=not_measured、value=null仅明确表示缺测，不可作为0或有效测量通过验收；无可用设备/系统观测时不填numeric value并给原因。

新增instrumentation和rendered调用会产生开销，只有新运行带字段；采样启动/收尾在既有end_to_end计时外、请求内采样开销在内，不能与round1成本直接混比。synthetic runtime不采真实机器资源。本批8项新增CPU测试覆盖实际脱敏、指纹、缺测、整卡采样与只追加；未验证GPU采样稳定性、真实渲染或开销。正式同机P50/P95、整卡和RAM仍待GPU。R20保持部分。
