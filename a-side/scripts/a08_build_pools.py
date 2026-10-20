"""按冻结协议生成候选池与 select3 证据清单（A 侧统一接口的可消费产物）。

协议要点（详见 a-side/reports/next_stage_20261020/interface_freeze.md）：
  * 语料 = corpus_v1，仅唯一内容，行序按 sha256 升序；候选身份 = q95 字节 sha256。
  * 编码器 = google/embeddinggemma-2 @ 固定 revision；图像由 q95 文件解码为 RGB。
  * 归一化 = cast 到 float32 后 L2 重新归一化（点积即 cosine）；口径写入产物。
  * 排序 = (-score, sha256 升序) —— 显式次序键，使并列不依赖排序实现。
  * 无自匹配 = 先剔除与查询图同 sha 的行，再取 top-10（不足则按原序补足并标记 refill）。
  * 维度 = 768 以及 128/256/512 截断后重新归一化（同一编码，仅截断，不重新编码）。
  * select3：cosine=按分数前 3；random=按 qid 派生种子的可复现抽样后按分数序排列；
            utility=外部（B）给分，按分数降序、sha 升序并列打破。

不评估 holdout；不根据 frozen_test 结果选择维度或阈值。

用法:
    python scripts/a08_build_pools.py --dtype fp32 --batch 1 \
        --cohorts smoke_20,dev_150,frozen_test --dims 768,512,256,128
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
EMB = Path(r"E:\EdgeCoRAG-A-store\emb_v1")
OUT = ROOT / "a-side" / "retrieval_if_v1"

COHORT_FILES = {
    "smoke_20": ("splits/smoke_20.v2.txt", "s1"),
    "dev_150": ("splits/dev.v2.txt", "s1"),
    "frozen_test": ("splits/frozen_test.v2.txt", "s1"),
}
TOP_K = 10
SELECT_K = 3
RANDOM_SEED_BASE = 20261017
POOL_ID = "eg2_shared_top10"
RETRIEVER_ID = "embeddinggemma-2@914f7f89142e33e77833254d9c9b90c3cef7303b"


def read_qids(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s if s.startswith("mragb:") else f"mragb:{s}")
    return out


def norm32(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return (v / np.maximum(n, 1e-12)).astype(np.float32)


def trunc_renorm(v: np.ndarray, dim: int) -> np.ndarray:
    return norm32(np.asarray(v[:, :dim], dtype=np.float32))


def seeded_indices(qid: str, k: int, n: int) -> list[int]:
    seed = (int(qid.split(":")[1]) * 1_000_003 + RANDOM_SEED_BASE) % (2**63 - 1)
    rng = np.random.Generator(np.random.PCG64(seed))
    return sorted(int(x) for x in rng.choice(n, size=k, replace=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtype", default="fp32", choices=["fp32", "bf16"])
    ap.add_argument("--batch", default="1", help="查询编码批大小档位（1 或 16）")
    ap.add_argument("--cohorts", default="smoke_20,dev_150,frozen_test")
    ap.add_argument("--dims", default="768,512,256,128")
    args = ap.parse_args()
    cohorts = [c.strip() for c in args.cohorts.split(",") if c.strip()]
    dims = [int(d) for d in args.dims.split(",") if d.strip()]

    # ---------------- 语料与查询向量
    cpath = EMB / f"corpus_{args.dtype}.npz"
    if not cpath.exists():
        print(f"缺少语料向量 {cpath}，先运行 scripts/a07_rank_stability.py --stage corpus", file=sys.stderr)
        return 1
    z = np.load(cpath, allow_pickle=True)
    shas = [str(x) for x in z["sha"]]
    Vfull = norm32(np.asarray(z["V"], dtype=np.float32))

    qz = np.load(EMB / "queries.npz", allow_pickle=True)
    qids_all = [str(x) for x in qz["qid"]]
    qidx = {q: i for i, q in enumerate(qids_all)}
    qsha = {str(q): str(s) for q, s in zip(qz["qid"], qz["sha"])}
    qkey = f"{args.dtype}_b{args.batch}"
    if qkey not in qz.files:
        print(f"缺少查询向量 {qkey}（已有 {sorted(qz.files)}）", file=sys.stderr)
        return 1
    Qfull = norm32(np.asarray(qz[qkey], dtype=np.float32))

    # 语料行序校验
    manifest = (CORPUS / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]
    msha = [r.split(",")[1] for r in manifest]
    if msha != shas:
        print("语料行序与 manifest 不一致，拒绝生成", file=sys.stderr)
        return 1
    meta_of = {}
    for r in manifest:
        f = r.split(",")  # row,sha256,bytes,w,h,occurrences,first_seen
        meta_of[f[1]] = {"bytes": int(f[2]), "w": int(f[3]), "h": int(f[4])}

    sha_pos = {s: i for i, s in enumerate(shas)}
    artifacts: list[dict] = []
    summary: dict = {
        "protocol": "a-side/retrieval-interface-v1",
        "retriever_id": RETRIEVER_ID,
        "pool_id": POOL_ID,
        "encoder_dtype": args.dtype,
        "query_batch": int(args.batch),
        "corpus": {"rows": len(shas), "identity": "sha256(JPEG q95 bytes)",
                   "row_order": "sha256 asc", "unique_contents": len(shas)},
        "top_k": TOP_K, "select_k": SELECT_K,
        "order_rule": "score desc, sha256 asc",
        "self_match_removal": "drop rows with sha256 == query image sha256 before top-k",
        "random_seed_rule": f"pcg64((qid_num*1000003+{RANDOM_SEED_BASE}) % (2**63-1)), sorted indices",
        "cohorts": {},
    }

    for cohort in cohorts:
        split_file, _ = COHORT_FILES[cohort]
        want = [q for q in read_qids(ROOT / split_file) if q in qidx]
        for dim in dims:
            V = trunc_renorm(Vfull, dim)
            Q = trunc_renorm(Qfull, dim)
            pool_rows, sel_rows, quality_rows = [], [], []
            for q in want:
                i = qidx[q]
                s = V @ Q[i]
                order = np.lexsort((np.asarray(shas), -s))  # 主键 -score，次键 sha
                self_sha = qsha[q]
                kept = [int(j) for j in order if shas[int(j)] != self_sha][:TOP_K]
                refill = len(kept) < TOP_K
                if refill:  # 语料不足（理论上不会发生）：如实记录而不是静默补齐
                    quality_rows.append({"qid": q, "dim": dim, "kept": len(kept), "refill_used": True})
                scores = [float(s[j]) for j in kept]
                margins = [scores[k] - scores[k + 1] for k in range(len(scores) - 1)]
                quality_rows.append({
                    "qid": q, "pool_id": POOL_ID, "embed_dim": dim,
                    "top1_score": round(scores[0], 9),
                    "top2_score": round(scores[1], 9) if len(scores) > 1 else "",
                    "top3_score": round(scores[2], 9) if len(scores) > 2 else "",
                    "gap_top1_top2": round(scores[0] - scores[1], 9) if len(scores) > 1 else "",
                    "gap_top1_top3": round(scores[0] - scores[2], 9) if len(scores) > 2 else "",
                    "mean_top10": round(sum(scores) / len(scores), 9),
                    "min_adjacent_margin": round(min(margins), 9) if margins else "",
                    "max_cosine": round(scores[0], 9),
                    "n_candidates": len(kept),
                    "self_removed": 1,
                    "refill_used": False,
                    "query_sha256": self_sha,
                    "query_w": meta_of.get(self_sha, {}).get("w", ""),
                    "query_h": meta_of.get(self_sha, {}).get("h", ""),
                })
                for r, (j, sc) in enumerate(zip(kept, scores), 1):
                    pool_rows.append({
                        "qid": q, "pool_id": POOL_ID, "retriever_id": RETRIEVER_ID,
                        "embed_dim": dim, "rank": r, "sha256": shas[j],
                        "score": round(sc, 9), "is_self_removed": 0, "refill_used": 0,
                    })
                # cosine select3（前 3，顺序即分数序）
                for slot, (j, sc) in enumerate(zip(kept[:SELECT_K], scores[:SELECT_K]), 1):
                    sel_rows.append({"qid": q, "strategy": "cosine", "embed_dim": dim,
                                     "slot": slot, "sha256": shas[j], "score": round(sc, 9),
                                     "selection_seed": "", "order_rule": "score desc"})
                # random select3：题目内派生种子抽样，再按分数序排列
                pick = seeded_indices(q, SELECT_K, len(kept))
                for slot, k in enumerate(pick, 1):
                    j = kept[k]
                    sel_rows.append({"qid": q, "strategy": "random", "embed_dim": dim,
                                     "slot": slot, "sha256": shas[j], "score": round(scores[k], 9),
                                     "selection_seed": RANDOM_SEED_BASE,
                                     "order_rule": "score desc within sampled set"})

            def dump(rel: str, rows: list[dict], note: str) -> None:
                p = OUT / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                artifacts.append({"path": rel, "sha256": h, "bytes": p.stat().st_size,
                                  "rows": len(rows), "note": note})

            dump(f"pools/{cohort}__dim{dim}__top10.csv", pool_rows,
                 f"{cohort} / {dim} 维 / 无自匹配 top10（含分数与身份）")
            dump(f"select3/{cohort}__dim{dim}__cosine+random.csv", sel_rows,
                 f"{cohort} / {dim} 维 / cosine 与 random 各 3 张")
            dump(f"pool_quality/{cohort}__dim{dim}__margins.csv", quality_rows,
                 f"{cohort} / {dim} 维 / 排序稳健性指标（最小相邻分差）")
            summary["cohorts"].setdefault(cohort, {})[str(dim)] = {
                "questions": len(want), "pool_rows": len(pool_rows), "select_rows": len(sel_rows)}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "artifacts.json").write_text(
        json.dumps({"summary": summary, "artifacts": artifacts}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["cohorts"], indent=2, ensure_ascii=False))
    print(f"{len(artifacts)} 个产物 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
