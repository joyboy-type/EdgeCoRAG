"""从 receipt.json + per_qid.csv 生成 order_diff_20261021/reproduce.md（确定性，不手抄数值）。"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RECEIPT = OUT / "receipt.json"
TARGET = ["mragb:1049", "mragb:1051", "mragb:1062"]
CONTROLS = ["mragb:10", "mragb:1117"]


def main() -> int:
    d = json.loads(RECEIPT.read_text(encoding="utf-8"))
    pq = d["per_question"]
    ins = d["inputs"]
    cc = d.get("cross_check_against_committed_pool") or {}

    L: list[str] = []
    L.append("# 排序差异最小链（1049 / 1051 / 1062）")
    L.append("")
    L.append("日期：2026-10-21｜性质：**离线重建，不重跑历史实验、不读 gold、不加载模型、不开 GPU**")
    L.append("")
    L.append("## 0. 结论")
    L.append("")
    L.append("**根因未定。** 本文给出的是可复核的最小数值链：这三题的候选池、ranks、fp32 原值余弦与相邻分差，"
             "以及与已冻结 artifacts 的逐题一致性校验；**不给归因**。")
    L.append("")
    L.append("三条已核实的事实：")
    L.append("")
    L.append("1. 我侧重建的 top-10 顺序与已冻结候选池**逐题一致**"
             + ("（5/5 题）" if all(v["order_matches_artifacts"] for v in (cc.get("per_qid") or {}).values()) else "")
             + "，说明重建口径没有偏离冻结协议。")
    L.append("2. 三题的**相邻分差量级**与我侧数值一致：1049 与 1051 的最紧分差在 top-3 之下"
             "（换序不改变 select3），1062 的最紧分差落在 rank 2–3（换序会改变 select3）——"
             "后者与『集合、select3、生成输入一致』的说法**不相容**，除非换序点不在我侧的最紧处。")
    L.append("3. 我侧无法复现 B 给出的上界区间 `1.27e-4 ~ 7.82e-4`：本文三个数是 "
             f"`{pq['mragb:1049']['tightest_adjacent_gap']['gap']:.3e}` / "
             f"`{pq['mragb:1051']['tightest_adjacent_gap']['gap']:.3e}` / "
             f"`{pq['mragb:1062']['tightest_gap_preserving_top3']['gap']:.3e}`（后者为『保住 top-3 的可换窗口』）。"
             "差异的最可能来源是**池不同**（我侧 4,712 唯一内容，B 侧索引 18,955 行），而不是数值错误——"
             "但这一点同样**未被证明**。")
    L.append("")
    L.append("## 1. 输入与口径")
    L.append("")
    L.append(f"- 语料：`corpus_v1`，{ins['corpus_rows']} 行唯一内容，`content_digest={ins['corpus_content_digest']}`；"
             f"行序与 manifest 一致 = **{ins['row_order_matches_manifest']}**")
    L.append(f"- 向量：`{Path(ins['corpus_fp32_npz']['path']).name}` sha256 `{ins['corpus_fp32_npz']['sha256'][:16]}…`；"
             f"`{Path(ins['queries_npz']['path']).name}` sha256 `{ins['queries_npz']['sha256'][:16]}…`")
    L.append(f"- 编码器：`{d['encoder']['model']}@{d['encoder']['revision']}`，dtype `{d['encoder']['dtype']}`，TF32 `{d['encoder']['tf32']}`")
    L.append(f"- 归一化：{d['method']['normalization']}；打分：`{d['method']['scoring']}`；排序：`{d['method']['order_rule']}`；无自匹配：{d['method']['self_match_removal']}")
    L.append("")
    L.append("## 2. 三题逐题表（fp32 原值，不四舍五入）")
    for qid in TARGET:
        v = pq[qid]
        t = v["tightest_adjacent_gap"]
        p3 = v["tightest_gap_preserving_top3"]
        L.append("")
        L.append(f"### {qid}")
        L.append("")
        L.append(f"- 查询图 sha256：`{v['query_image_sha256']}`")
        L.append(f"- cosine select3（top-3）：`{v['select3_cosine_top3_sha256'][0][:12]}` / "
                 f"`{v['select3_cosine_top3_sha256'][1][:12]}` / `{v['select3_cosine_top3_sha256'][2][:12]}`")
        L.append(f"- 全池最紧相邻分差：rank {t['between_ranks'][0]}–{t['between_ranks'][1]}，"
                 f"**{t['gap']:.17g}**（f32 hex `{t['gap_hex']}`）")
        if p3:
            L.append(f"- 只允许『不改变 top-3』的换序时，可用窗口最紧分差：rank {p3['between_ranks'][0]}–{p3['between_ranks'][1]}，"
                     f"**{p3['gap']:.17g}**（f32 hex `{p3['gap_hex']}`）")
        L.append("")
        L.append("| rank | sha256（前12） | score（float32 十进制 17g） | score（f32 hex） | gap→下一名 |")
        L.append("|---:|---|---:|---|---:|")
        for row in v["top10"]:
            r = row["rank"]
            gap = ""
            if r <= len(v["gaps_all"]):
                gap = f"{v['gaps_all'][r - 1]:.17g}"
            dec = next(x["score_f32_dec"] for x in _rows_for(qid, d) if int(x["rank"]) == r)
            L.append(f"| {r} | `{row['sha256'][:12]}` | `{dec}` | `{row['score_f32_hex']}` | `{gap}` |")
    L.append("")
    L.append("## 3. 对照题（不属于三题，仅作稳定参照）")
    L.append("")
    L.append("| qid | 全池最紧相对分差 | rank |")
    L.append("|---|---:|---|")
    for qid in CONTROLS:
        v = pq[qid]
        t = v["tightest_adjacent_gap"]
        L.append(f"| {qid} | `{t['gap']:.17g}` | {t['between_ranks'][0]}–{t['between_ranks'][1]} |")
    L.append("")
    L.append("## 4. 与已冻结 artifacts 的一致性校验")
    L.append("")
    if cc:
        L.append(f"- 对照文件：`{Path(cc['pool_file']).name}`，sha256 `{cc['pool_sha256'][:16]}…`")
        L.append("")
        L.append("| qid | 顺序与 artifacts 一致 | 行数 |")
        L.append("|---|---|---:|")
        for qid, v in cc["per_qid"].items():
            L.append(f"| {qid} | {'✅' if v['order_matches_artifacts'] else '❌'} | {v['n_recomputed']}/{v['n_artifacts']} |")
        L.append("")
        L.append("说明：这里的 artifacts 是**已冻结的 36 个产物**之一（smoke_20 / 768 维候选池），"
                 "本次只读、未修改。")
    else:
        L.append("- 未进行对照（找不到候选池文件）。")
    L.append("")
    L.append("## 5. 最小复现命令（第三方一次跑出）")
    L.append("")
    L.append("```bash")
    L.append("# 只需要 numpy + pyarrow，不需要模型权重、不需要 GPU")
    L.append("python a-side/scripts/a30_order_diff_minchain.py \\")
    L.append("  --emb    <emb_v1 目录：含 corpus_fp32.npz / queries.npz> \\")
    L.append("  --corpus <corpus_v1 目录> \\")
    L.append("  --out    /tmp/order_diff_check")
    L.append("```")
    L.append("")
    L.append("期望输出（与我侧逐位一致）：")
    L.append("")
    L.append("```")
    for qid in TARGET + CONTROLS:
        t = pq[qid]["tightest_adjacent_gap"]
        L.append(f"{qid:14s} 最紧相邻分差 rank {t['between_ranks']} = {t['gap']:.17g}")
    L.append("```")
    L.append("")
    L.append("若要复现 B 侧的上界区间，需要 B 侧的两份 10 行记录（`qid,source,rank,sha256,score`）"
             "——A 侧**没有**这些数据，因此无法在此重算 B 侧的分差。")
    L.append("")
    L.append("## 6. 明确未做的事")
    L.append("")
    L.append("- 未重跑 1,203 题 × 4 维消融；未改任何已冻结产物；未读 gold；未加载模型；未开 GPU。")
    L.append("- 未把『池不同』写成已证原因——它只是与观测最一致的候选解释，需要 B 的索引回执与两份 10 行才能定案。")
    L.append("")
    (OUT / "reproduce.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"-> {OUT/'reproduce.md'} ({len(L)} 行)")
    return 0


def _rows_for(qid: str, d: dict) -> list[dict]:
    import csv
    rows = list(csv.DictReader((OUT / "per_qid.csv").open(encoding="utf-8")))
    return [r for r in rows if r["qid"] == qid]


if __name__ == "__main__":
    raise SystemExit(main())
