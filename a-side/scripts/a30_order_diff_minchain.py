"""任务2：三题（1049/1051/1062）排序差异的最小链重建 + 精确 fp32 余弦。

不重跑历史实验、不读 gold、不加载模型：
  * 语料向量与查询向量取自已缓存的 emb_v1（fp32），按冻结协议做 float32 层归一化后点积；
  * 排序 = lexsort((-score, sha256))，剔除查询图自身身份后取 top-10（与 artifacts 同口径）；
  * 输出不四舍五入的 float32 原值（十进制全精度 + 十六进制位模式）与相邻分差。

用法：
    python a30_order_diff_minchain.py --emb E:/EdgeCoRAG-A-store/emb_v1 \
        --corpus E:/EdgeCoRAG-A-store/corpus_v1 --out <目录>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

DEFAULT_QIDS = ["mragb:1049", "mragb:1051", "mragb:1062", "mragb:10", "mragb:1117"]


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm32(v: np.ndarray) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(a, axis=1, keepdims=True)
    return (a / np.maximum(n, np.float32(1e-12))).astype(np.float32)


def f32_repr(x: np.float32) -> str:
    """float32 值 → 能无歧义还原的十进制（17 位有效数字）。"""
    return format(float(x), ".17g")


def f32_hex(x: np.float32) -> str:
    return float(x).hex()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emb", default=r"E:\EdgeCoRAG-A-store\emb_v1")
    ap.add_argument("--corpus", default=r"E:\EdgeCoRAG-A-store\corpus_v1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--qids", default=",".join(DEFAULT_QIDS))
    args = ap.parse_args()

    emb = Path(args.emb)
    corpus = Path(args.corpus)
    out = Path(args.out) if args.out else Path("order_diff_20261021")
    out.mkdir(parents=True, exist_ok=True)

    cz = np.load(emb / "corpus_fp32.npz", allow_pickle=True)
    shas = [str(x) for x in cz["sha"]]
    V = norm32(cz["V"])
    qz = np.load(emb / "queries.npz", allow_pickle=True)
    qids_all = [str(x) for x in qz["qid"]]
    pos = {q: i for i, q in enumerate(qids_all)}
    qsha = {str(q): str(s) for q, s in zip(qz["qid"], qz["sha"])}
    Q = norm32(qz["fp32_b1"])

    # 语料行序与 manifest 一致性（防止用错缓存）
    man = [r.split(",")[1] for r in (corpus / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]]
    row_order_ok = man == shas

    meta = json.loads((corpus / "corpus_meta.json").read_text(encoding="utf-8"))

    rows = []
    per_q = {}
    for qid in [q.strip() for q in args.qids.split(",") if q.strip()]:
        if qid not in pos:
            print(f"[skip] {qid} 不在 queries.npz", file=sys.stderr)
            continue
        i = pos[qid]
        q = Q[i]
        s = V @ q  # float32 逐题点积（与冻结协议一致）
        order = np.lexsort((np.asarray(shas), -s))
        kept = [int(j) for j in order if shas[int(j)] != qsha[qid]][: args.topk]
        scores = [s[j] for j in kept]
        gaps = [float(scores[k]) - float(scores[k + 1]) for k in range(len(scores) - 1)]
        for r, (j, sc) in enumerate(zip(kept, scores), 1):
            rows.append({
                "qid": qid, "rank": r, "sha256": shas[j],
                "score_f32_dec": f32_repr(sc), "score_f32_hex": f32_hex(sc),
                "gap_to_next_dec": (f32_repr(np.float32(gaps[r - 1])) if r - 1 < len(gaps) else ""),
                "gap_to_next_float64_exact": ("%.17g" % gaps[r - 1] if r - 1 < len(gaps) else ""),
            })
        tight = min(range(len(gaps)), key=lambda k: abs(gaps[k])) if gaps else None
        per_q[qid] = {
            "query_image_sha256": qsha[qid],
            "top10": [{"rank": r, "sha256": shas[j], "score_f32_hex": f32_hex(sc)}
                      for r, (j, sc) in enumerate(zip(kept, scores), 1)],
            "tightest_adjacent_gap": None if tight is None else {
                "between_ranks": [tight + 1, tight + 2],
                "gap": gaps[tight],
                "gap_hex": f32_hex(np.float32(gaps[tight])),
                "score_at_upper_hex": f32_hex(scores[tight]),
                "score_at_lower_hex": f32_hex(scores[tight + 1]),
            },
            "select3_cosine_top3_sha256": [shas[j] for j in kept[:3]],
            "gaps_all": gaps,
            # 若只允许"不改变 top-3"的一次相邻交换，可用窗口（0-based 分差下标 >= 3）的最紧分差
            "tightest_gap_preserving_top3": (None if len(gaps) <= 3 else {
                "between_ranks": [min(range(3, len(gaps)), key=lambda k: abs(gaps[k])) + 1,
                                  min(range(3, len(gaps)), key=lambda k: abs(gaps[k])) + 2],
                "gap": min(gaps[3:], key=abs),
                "gap_hex": f32_hex(np.float32(min(gaps[3:], key=abs))),
            }),
        }

    import csv
    csv_p = out / "per_qid.csv"
    with csv_p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    receipt = {
        "task": "order_diff_20261021 / 三题排序差异最小链",
        "method": {
            "protocol": "a-side/retrieval-interface-v1",
            "normalization": "float32 L2 (norm32)，与 artifacts 生成时一致",
            "scoring": "score = V32 @ q32（numpy float32 逐题点积）",
            "order_rule": "lexsort(keys=(-score, sha256))",
            "self_match_removal": "剔除 image_id == 查询图 image_id 后取 top-10",
            "query_vector": "queries.npz 的 fp32_b1（批量 1，即当前冻结现场编码口径）",
            "no_gold": True, "no_model": True, "no_gpu": True,
        },
        "inputs": {
            "corpus_fp32_npz": {"path": str(emb / "corpus_fp32.npz"), "sha256": sha_file(emb / "corpus_fp32.npz")},
            "queries_npz": {"path": str(emb / "queries.npz"), "sha256": sha_file(emb / "queries.npz")},
            "corpus_manifest": {"path": str(corpus / "corpus_manifest.csv"),
                                "sha256": sha_file(corpus / "corpus_manifest.csv")},
            "corpus_content_digest": meta.get("content_digest_sha256"),
            "corpus_rows": len(shas),
            "row_order_matches_manifest": bool(row_order_ok),
        },
        "encoder": {"model": "google/embeddinggemma-2",
                    "revision": "914f7f89142e33e77833254d9c9b90c3cef7303b",
                    "dtype": "float32", "tf32": False},
        "per_question": per_q,
        "cross_check_against_committed_pool": None,
        "root_cause": "未定（本文件只给可复核的数值链，不给归因）",
    }

    # 与已冻结候选池（smoke_20 dim768）对照：排名必须一致，score 应在其 9 位小数内
    pool = Path(r"E:\EdgeCoRAG-A-store\_next_stage\a-side\retrieval_if_v1\pools\smoke_20__dim768__top10.csv")
    if pool.exists():
        import csv as _csv
        pool_rows = list(_csv.DictReader(pool.open(encoding="utf-8")))
        check = {}
        for qid in per_q:
            want = [r["sha256"] for r in pool_rows if r["qid"] == qid]
            got = [t["sha256"] for t in per_q[qid]["top10"]]
            check[qid] = {"order_matches_artifacts": want == got,
                          "n_artifacts": len(want), "n_recomputed": len(got)}
        receipt["cross_check_against_committed_pool"] = {
            "pool_file": str(pool), "pool_sha256": sha_file(pool), "per_qid": check,
        }

    (out / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"语料 {len(shas)} 行；row_order_ok={row_order_ok}")
    for qid, v in per_q.items():
        t = v["tightest_adjacent_gap"]
        print(f"{qid:14s} 最紧相邻分差 rank {t['between_ranks']} = {t['gap']:.17g}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
