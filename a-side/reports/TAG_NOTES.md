# 标签补记（TAG_NOTES）

标签一旦推送就不移动、不删除；说明漏写的内容在此补记，不改标签对象本身。

## `a-iface-20261021-fix` → `89ddb29`

A1–A6 工具层修复 + A7–A9（索引回执契约 / 最佳固定 RAG 规则 / utility-mrag 可行性）。
**该标签下的 `a17` 仅在 Windows CRLF 工作树成立**；干净检出 `fail_count=72`（清单按 CRLF 记哈希）。

## `a-iface-20261021-fix2` → `fc67c40`

标签说明为「只修清单行尾口径；36 个产物内容与数值未变；a17 在干净检出下 0 失败」。
**补记两点**：

1. **P0 的实际内容**（标签说明漏写）：`.gitattributes` 增加 `a-side/retrieval_if_v1/** text eol=lf`；`artifacts.json` 按 **LF 字节**重算 36 个 sha256/bytes 并写 `summary.hash_normalization="LF"`；`a17` 比对前做 `\r\n→\n` 归一化并新增 `--strict-lf`；新增 `a23`（幂等重算清单）与 `a22`（8 用例锁 CRLF）。
2. **该提交里 `a19`/`a22` 存在执行缺陷**（`a19` 的 `_scrub` 正则导致无法编译；`a22` 的 `run()` 未指定 encoding，在 cp936 下 stdout 变 None）。这些在 `fix3` 修复。**需要"全绿状态"请用 `fix3`。**

## `a-iface-20261021-fix3` → `c77e91c`

**补记**：修复 `fix2` 中两个校验脚本的执行缺陷，并给六个校验/工具脚本加 utf-8 输出健壮化；
自检改为**只看 rc**（不再读旧回执判断通过）。产物与清单零变更。

## `a-iface-20261021-fix4` → 本轮

**内容**：

- `a17` 增 `--out`（干净检出重跑不弄脏工作树）；`verify.json` 的 `files_with_crlf` 语义改写为
  "**本次运行需要归一化的文件数**"（CRLF 树 36 / LF 树 0），并新增 `line_ending_note` 字段；
  仓库内提交的是**干净 LF 检出生成的那份**（`files_with_crlf=0`）。
- `contracts/index_receipt_field_mapping.md`（新）：逐字段映射，解除"字段未知"误判；
  `reconciliation` 增 `notes`（`verdict=pending` 时必填，`a20` 强制检查，自检 10→12 项）。
- `reports/next_stage_20261020/index_receipt_adjudication.md`：升级为**判定矩阵**（三假设 × 字段 → 期望值 → 排除条件），
  明确"按映射表填值时 H1/H2 被**条件性**排除、只剩 H3，但 H3 仍需 `sources[]` 支撑"，**不下结论**。
- `reports/next_stage_20261020/A4_attribution_dryrun.md`（新）：a21 空表 dry-run（5 题全 `insufficient_data`）+
  "1049 是否落在批大小签名内"的复现结论（**不在**：5 题无一被批大小翻转；24 变体中无任何变体恰好翻转 `{1049,1051,1062}`）。
- `B_handoff_prompt.md`：G1 改为"附本次 rc"；B2/B3 的字段与缺失标记写全（② 的表头、
  ③④ 的 JSON 键与 `null` 标记）。
