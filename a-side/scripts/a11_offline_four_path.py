"""四路径离线矩阵与 Oracle 路由上界（只用已归档的真实逐题结果，不跑模型）。

对应本轮任务 5 的前半部分。四条路径按任务书定义：
    A0 = E2B 直接（S0）        A1 = 检索 + E2B（S1）
    A2 = E4B 直接（S0）        A3 = 检索 + E4B（S1）

关键边界：
  * 这里的 S1 是**已发布官方候选 top3**（pool_id=official_retrieved_top3），
    不是自主 EmbeddingGemma 检索；所以本文件给出的是"历史证据条件下的四路径"，
    自主检索四路径必须在冻结接口后另行执行。
  * Oracle 路由 = 逐题在四条已执行路径里取最优，是**上界**，不可部署；
    与 S2（GT 证据 Oracle）不是同一概念，二者分开报告。
  * 评分复用 strict_choice_v1 语义：parse_status!='ok' 一律计错，不重解析、不改分母。

先做保真校验：用本地 gold 重算的 (model, split, condition) 聚合必须与已发布
reports/v1.10.1/quality.csv 逐格一致，否则本脚本拒绝产出四路径表。

用法: python scripts/a11_offline_four_path.py
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
REMOTE = ROOT / "outputs" / "_remote" / "data"
OUT = ROOT / "outputs" / "four_path"

PATHS = {
    "A0": ("google/gemma-4-E2B-it", "S0"),
    "A1": ("google/gemma-4-E2B-it", "S1"),
    "A2": ("google/gemma-4-E4B-it", "S0"),
    "A3": ("google/gemma-4-E4B-it", "S1"),
}


def gold() -> dict[str, str]:
    g: dict[str, str] = {}
    for sh in sorted(DATA.glob("test-*.parquet")):
        pf = pq.ParquetFile(sh)
        for rg in range(pf.num_row_groups):
            t = pf.read_row_group(rg, columns=["id", "answer_choice"])
            for row in t.to_pylist():
                g[f"mragb:{row['id']}"] = str(row["answer_choice"]).strip()
    return g


def splits() -> dict[str, set[str]]:
    def rd(name: str) -> set[str]:
        out = set()
        for line in (ROOT / "splits" / name).read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.add(s if s.startswith("mragb:") else f"mragb:{s}")
        return out

    return {
        "smoke_20": rd("smoke_20.v2.txt"),
        "dev_150": rd("dev.v2.txt"),
        "internal_holdout_150": rd("internal_holdout.v2.txt"),
        "frozen_test_1033": rd("frozen_test.v2.txt"),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    g = gold()
    sp = splits()

    # ---------------- 逐题结果（同一 (model,condition,qid) 保留唯一主批次记录）
    rows: dict[tuple[str, str, str], dict] = {}
    dup = 0
    with gzip.open(REMOTE / "logs" / "B_predictions.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("run_batch_id") != "v1.10.1" or r.get("repeat_index") != 0:
                continue
            if r["condition"] not in ("S0", "S1", "S2"):
                continue
            k = (r["model_id"], r["condition"], r["qid"])
            if k in rows:
                dup += 1
                continue
            rows[k] = r
    print(f"主条件记录 {len(rows)} 条（重复跳过 {dup}）")

    # ---------------- 保真校验：与已发布 quality.csv 逐格比对
    pub_path = REMOTE / "reports" / "v1.10.1" / "quality.csv"
    pub_rows = pub_path.read_text(encoding="utf-8").splitlines()[1:]
    keymap = {
        "qwen3vl_4b": "Qwen/Qwen3-VL-4B-Instruct",
        "qwen3vl_8b": "Qwen/Qwen3-VL-8B-Instruct",
        "gemma4_e2b": "google/gemma-4-E2B-it",
        "gemma4_e4b": "google/gemma-4-E4B-it",
        "qwen35_4b": "Qwen/Qwen3.5-4B",
    }
    splitmap = {"internal_holdout": "internal_holdout_150", "frozen_test": "frozen_test_1033"}
    mine: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for (model, cond, qid), r in rows.items():
        for sname, qset in sp.items():
            if qid in qset:
                ok = 1 if (r.get("parse_status") == "ok" and str(r.get("parsed_choice")).strip() == g.get(qid)) else 0
                mine[(model, sname, cond)][0] += ok
                mine[(model, sname, cond)][1] += 1
                break

    checks, bad = [], 0
    skipped_s3 = 0
    for line in pub_rows:
        f = line.split(",")
        mk, split, cond, n, correct = f[0], f[2], f[3], int(f[4]), int(f[5])
        if cond == "S3-pure":
            # S3 只在 Gemma 批准子集上执行，本脚本主条件只取 S0/S1/S2；如实跳过而非当作通过
            skipped_s3 += 1
            continue
        model = keymap[mk]
        s = splitmap[split]
        c, tot = mine[(model, s, cond)]
        match = (c == correct and tot == n)
        if not match:
            bad += 1
        checks.append({"model_key": mk, "split": split, "condition": cond,
                       "published_n": n, "published_correct": correct,
                       "recomputed_n": tot, "recomputed_correct": c, "match": match})
    print(f"保真校验：{len(checks)} 格（主条件 S0/S1/S2），不一致 {bad}；另有 {skipped_s3} 行 S3 按范围跳过")
    (OUT / "fidelity_check.json").write_text(
        json.dumps({"checked_cells": checks, "mismatches": bad, "s3_pure_rows_skipped": skipped_s3},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    if bad:
        print("❌ 与已发布质量表不一致，拒绝产出四路径表", file=sys.stderr)
        for c in checks:
            if not c["match"]:
                print(f"  {c}", file=sys.stderr)
        return 1

    # ---------------- 四路径矩阵
    qsel = {q for s in ("internal_holdout_150", "frozen_test_1033") for q in sp[s]}
    cohort = {}
    for sname in ("internal_holdout_150", "frozen_test_1033"):
        for q in sp[sname]:
            cohort[q] = sname
    matrix = []
    missing = 0
    for q in sorted(qsel, key=lambda s: int(s.split(":")[1])):
        row = {"qid": q, "cohort": cohort[q]}
        for pname, (model, cond) in PATHS.items():
            r = rows.get((model, cond, q))
            if r is None:
                missing += 1
                row[pname] = ""
                continue
            row[pname] = 1 if (r.get("parse_status") == "ok" and str(r.get("parsed_choice")).strip() == g.get(q)) else 0
        matrix.append(row)
    print(f"四路径矩阵 {len(matrix)} 题（缺失单元 {missing}）")

    with (OUT / "four_path_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("qid,cohort,A0,A1,A2,A3\n")
        for r in matrix:
            f.write(f"{r['qid']},{r['cohort']},{r['A0']},{r['A1']},{r['A2']},{r['A3']}\n")

    # ---------------- 汇总：路径准确率 / Oracle 上界 / 固定最优 / 互补性
    summary: dict = {"pool_id": "official_retrieved_top3", "paths": {k: {"model": v[0], "condition": v[1]} for k, v in PATHS.items()},
                     "note": "S1=已发布官方候选top3；S0=无外部证据。Oracle 路由为逐题取四路径最优，仅上界。",
                     "cohorts": {}}
    for cname in ("internal_holdout_150", "frozen_test_1033"):
        sub = [r for r in matrix if r["cohort"] == cname and all(r[p] != "" for p in PATHS)]
        n = len(sub)
        acc = {p: sum(r[p] for r in sub) / n for p in PATHS}
        oracle = sum(max(r[p] for p in PATHS) for r in sub) / n
        best_fixed = max(acc, key=acc.get)
        # 互补性：任何一条路径都不对、或只有个别路径对的题数
        only_one = {p: sum(1 for r in sub if r[p] == 1 and sum(r[q] for q in PATHS) == 1) for p in PATHS}
        allwrong = sum(1 for r in sub if sum(r[q] for q in PATHS) == 0)
        allright = sum(1 for r in sub if sum(r[q] for q in PATHS) == len(PATHS))
        summary["cohorts"][cname] = {
            "n": n,
            "path_accuracy": {p: round(v, 6) for p, v in acc.items()},
            "path_correct": {p: sum(r[p] for r in sub) for p in PATHS},
            "fixed_best_path": best_fixed,
            "fixed_best_accuracy": round(acc[best_fixed], 6),
            "oracle_accuracy": round(oracle, 6),
            "oracle_gain_over_fixed_best_pp": round((oracle - acc[best_fixed]) * 100, 4),
            "path_unique_correct": only_one,
            "questions_all_paths_wrong": allwrong,
            "questions_all_paths_right": allright,
            "e2b_retrieval_gain_pp": round((acc["A1"] - acc["A0"]) * 100, 4),
            "e4b_retrieval_gain_pp": round((acc["A3"] - acc["A2"]) * 100, 4),
            "e4b_vs_e2b_no_evidence_pp": round((acc["A2"] - acc["A0"]) * 100, 4),
            "e4b_vs_e2b_with_evidence_pp": round((acc["A3"] - acc["A1"]) * 100, 4),
        }
    (OUT / "four_path_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["cohorts"], indent=2, ensure_ascii=False))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
