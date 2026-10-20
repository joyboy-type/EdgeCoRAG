# B18955 pixel表交付

文件pixel_identity_18955.csv：18955行（表头另计），43583388字节；SHA256 `8039a0c40a2bcbe14ec5e2b18a6b45f14bf47bbdbc03f9e6913618214d35eafc`。unique_pixel_sha=18955。10列顺序与A规格一致：sha256_q95,sha256_raw,pixel_sha,ahash,gray32,w,h,pillow,libjpeg,source。本文件含gray32派生图像内容且超过5MiB，只作本地交付，不入Git。

使用A只读提交f59765069e4f069e8b84974adb33e2fb5188efb3（a-pixel-20261021）算法；pixel_sha为RGB行优先字节后拼|wxh，aHash为LANCZOS8x8、严格大于均值、行优先低位先，gray32为LANCZOS32x32灰度1024字节hex。无EXIF旋转、无ICC变换；MPO默认第一帧。没有用向量反推。

**来源偏差必须交A确认**：B是独立语料ZIP直接成员原始字节，不是A规格写明的parquet struct<bytes>。ZIP成员CRC与每张原始字节SHA均在本次核验18955/18955；没有读q95重编码缓存。sha256_q95沿用历史别名，逐条核对历史jpeg95_rgb_sha256，未新生成q95文件。不能把ZIP来源写成parquet或称已满足A全部来源条件。

Pillow12.3.0，libjpeg6.2，libjpeg-turbo3.1.4.1；A记录libjpeg8.0，跨版本同图校准未做。因此**尚不能跨版本求交或报告N_common**，本次没有计算A/B交集。有损重编码也不能保证pixel_sha不变。A规格原文另附，源SHA见receipt。

逐图内存解码后只落一行特征，flush+fsync；未写任何RGB图像文件。计算段实际85.321944秒（不含ZIP哈希/预检），末尾空闲约5.22GiB。5条palette透明度UserWarning保留在warnings.jsonl，没有擅改RGBA/合成规则。CSV结构/行序/哈希复验rc0，未再次解码全量图像。

本次命令rc0；测试144 OK rc0（141+新增3），分析54 OK rc0；裸需求审计rc1是缺显式输入的设计。代码与小回执可入库；pixel大表留本地，未推送、未用GPU。
