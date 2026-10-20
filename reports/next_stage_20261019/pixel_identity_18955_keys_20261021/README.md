# B18955瘦身键表

仅pixel_identity_18955_keys.csv入库，三列严格为sha256_raw,sha256_q95,l1b；18955行，3696251字节（小于5MiB）。SHA256：`7d51cf8e6b18e038cf7eeac0a88bf1cd8114a56af0fe529e8b687079fcdd4208`。

l1b：从已有gray32逐字节计算round(v/255*11)，12级0..11；uint8输入没有恰好半整数的舍入歧义。按行序，每两个q各取低4位，首q放高4位、次q放低4位，1024像素打包为512字节，再SHA256。A须使用同一位序。实现用精确整数(22*v+255)//510；全部256取值与字面round公式一致；另用独立实现核验实际主表前20行。

sha256_raw来自ZIP原始成员字节，与A parquet原字节是否同源：**未验证**。sha256_q95逐行复制历史JPEG95身份，未重新编码。两列与主表18955/18955行原顺序一致。

B Pillow12.3.0 / libjpeg6.2(turbo3.1.4.1)，A libjpeg8.0。“差异只影响pixel_sha、不影响三列”不能当作已证实事实：本次raw/q95只是复制，所以导出不受解码器影响；l1b依赖上游gray32，量化降低敏感性但不保证跨版本不变。q95若由另一端重新编码，字节一致性也不能仅凭哈希算法不变保证。l1b是粗粒度候选键，不能替代pixel_sha精确内容判据或语义等价证明。本批没有做A/B求交。

主表43583388字节留本地，未入库/未推送：
`/Users/joyboy/Documents/Codex/2026-10-19/edgecorag-context-recovery/outputs/pixel_identity_18955_20261021/pixel_identity_18955.csv`
SHA256：`8039a0c40a2bcbe14ec5e2b18a6b45f14bf47bbdbc03f9e6913618214d35eafc`。

复算（显式本地主表与新输出，不能覆盖）：
```sh
$PY analysis/next_stage_20261019/export_pixel_keys.py --source "$LOCAL_PIXEL_TABLE" --source-sha256 8039a0c40a2bcbe14ec5e2b18a6b45f14bf47bbdbc03f9e6913618214d35eafc --out "$NEW_KEYS_CSV" --receipt "$NEW_RECEIPT_JSON"
```

未读取图像或向量、未重算像素、未调用Pillow或GPU、未改a-side。按用户末尾“验完再推”保留本地提交，不执行推送。真实命令rc与结构/发布检查见validation/。
