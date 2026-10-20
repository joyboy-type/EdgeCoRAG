"""打分实现与算术设置对 top-10 顺序的影响（不重新编码，纯离线复算）。

任务 1 的第二个变量组。上一支实验只改了"编码 batch"，本实验改"打分/排序实现"：
  * numpy 逐题向量乘（V @ q）
  * numpy 整批 GEMM（Q @ V.T，等价于一次性算 1203×4712 分数矩阵）
  * torch float32 GEMM（TF32 关闭），整批与逐题
  * argsort(stable) 与 torch.topk(sorted=True) 的次序差异
并给出"翻转发生在多小的相邻分差内"的实测阈值 τ，用于给冻结接口一个可执行的
`order_fragile` 判据。

用法: python scripts/a09_score_arith.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
EMB = Path(r"E:\EdgeCoRAG-A-store\emb_v1")
OUT = ROOT / "outputs" / "rank_stability"
TOP_K = 10


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


def model_norm(v: np.ndarray) -> np.ndarray:
    import torch

    t = torch.from_numpy(np.asarray(v, dtype=np.float32)).to(torch.bfloat16)
    t = t / t.norm(dim=1, keepdim=True)
    return t.float().numpy()


def topk_from_scores(s: np.ndarray, shas: list[str], self_sha: str, k: int) -> list[int]:
    order = np.lexsort((np.asarray(shas), -s))
    return [int(j) for j in order if shas[int(j)] != self_sha][:k]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import torch

    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False

    z = np.load(EMB / "corpus_bf16.npz", allow_pickle=True)
    shas = [str(x) for x in z["sha"]]
    Vmodel = model_norm(z["V"])
    Vfp32 = norm32(z["V"])

    qz = np.load(EMB / "queries.npz", allow_pickle=True)
    qids = [str(x) for x in qz["qid"]]
    qsha = {str(q): str(s) for q, s in zip(qz["qid"], qz["sha"])}
    Qmodel = model_norm(qz["bf16_b16"])
    Qfp32 = norm32(qz["bf16_b16"])

    # 语料行序校验
    msha = [r.split(",")[1] for r in (CORPUS / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]]
    assert msha == shas

    # ---------------- 参考：numpy 逐题、模型内归一化、stable argsort
    scores_ref = np.stack([Vmodel @ Qmodel[i] for i in range(len(qids))])
    ref = [topk_from_scores(scores_ref[i], shas, qsha[q], TOP_K + 1)[:TOP_K] for i, q in enumerate(qids)]
    ref_shas = [[shas[j] for j in top] for top in ref]

    # ---------------- 变体
    variants: dict[str, np.ndarray] = {}

    # (a) numpy 整批 GEMM
    variants["numpy_full_gemm"] = (Qmodel @ Vmodel.T).astype(np.float32)
    # (b) numpy 分块 32
    chunks = []
    for i in range(0, len(qids), 32):
        chunks.append((Qmodel[i:i + 32] @ Vmodel.T).astype(np.float32))
    variants["numpy_chunk32"] = np.concatenate(chunks, axis=0)
    # (c)(d) torch float32 GEMM（TF32 关闭），整批与逐题
    Vt = torch.from_numpy(Vfp32)
    Qt = torch.from_numpy(Qfp32)
    variants["torch_fp32_full_gemm"] = (Qt @ Vt.T).numpy()
    variants["torch_fp32_per_query"] = np.stack([(Vt @ Qt[i]).numpy() for i in range(len(qids))])
    # (e) 语料侧用 fp32_renorm 的 numpy 整批（归一化位置差异，作对照）
    variants["numpy_full_gemm_fp32_norm"] = (Qfp32 @ Vfp32.T).astype(np.float32)

    summary: dict = {"reference": "numpy_per_query + model_norm + lexsort(-score, sha)",
                     "queries": len(qids), "corpus_rows": len(shas), "variants": {}}

    # 参考自身的相邻分差（用于阈值）
    ref_min_margin = []
    for i in range(len(qids)):
        s = scores_ref[i]
        top = ref[i]
        sc = [float(s[j]) for j in top]
        gaps = [sc[k] - sc[k + 1] for k in range(len(sc) - 1)]
        ref_min_margin.append(min(gaps) if gaps else float("nan"))

    qid_meta = {q: {"cohort_idx": i, "min_margin": ref_min_margin[i]} for i, q in enumerate(qids)}

    for name, S in variants.items():
        od = md = t3 = 0
        max_ds = 0.0
        flipped_min_margins = []
        for i, q in enumerate(qids):
            top = topk_from_scores(S[i], shas, qsha[q], TOP_K)
            cur = [shas[j] for j in top]
            same = cur == ref_shas[i]
            if not same:
                od += 1
                flipped_min_margins.append(ref_min_margin[i])
            if set(cur) != set(ref_shas[i]):
                md += 1
            if cur[:3] != ref_shas[i][:3]:
                t3 += 1
            max_ds = max(max_ds, float(np.abs(S[i] - scores_ref[i]).max()))
        flips = sorted(flipped_min_margins)
        summary["variants"][name] = {
            "order_diff": od, "order_diff_rate": round(od / len(qids), 4),
            "membership_diff": md, "top3_diff": t3,
            "max_abs_score_delta": max_ds,
            "flipped_min_margin_max": (round(flips[-1], 9) if flips else None),
            "flipped_min_margin_p95": (round(flips[int(0.95 * (len(flips) - 1))], 9) if flips else None),
        }
        print(f"{name:32s} order_diff={od:5d} ({od/len(qids):6.2%})  membership_diff={md:4d}  top3_diff={t3:4d}  max|Δscore|={max_ds:.3e}")

    # ---------------- 阈值：在 batch 变体上做同样的 τ 估计
    Qb1 = norm32(qz["bf16_b1"])
    # 查询侧归一化对顺序无影响（正标量缩放），因此直接与参考的逐题分数比较
    od_b = 0
    flipped_margins_b = []
    for i, q in enumerate(qids):
        s = Vmodel @ Qb1[i] if False else None  # 占位，避免误用 fp32/mo
    # 用 model_norm 的 b1 查询重算（与查询侧归一化无关）
    Qb1m = model_norm(qz["bf16_b1"])
    for i, q in enumerate(qids):
        s = Vmodel @ Qb1m[i]
        top = [shas[j] for j in topk_from_scores(s, shas, qsha[q], TOP_K)]
        if top != ref_shas[i]:
            od_b += 1
            flipped_margins_b.append(ref_min_margin[i])
    fb = sorted(flipped_margins_b)
    summary["query_encode_batch_b1_vs_b16"] = {
        "order_diff": od_b, "order_diff_rate": round(od_b / len(qids), 4),
        "flipped_min_margin_max": (round(fb[-1], 9) if fb else None),
        "flipped_min_margin_p50": (round(fb[len(fb) // 2], 9) if fb else None),
    }
    print(f"query_batch_b1_vs_b16          order_diff={od_b:5d} ({od_b/len(qids):6.2%})")

    # ---------------- 分差分布与翻转率（batch 变体）
    edges = [(0, 1e-6), (1e-6, 1e-5), (1e-5, 1e-4), (1e-4, 1e-3), (1e-3, 1e-2), (1e-2, 1.0)]
    buckets = []
    for lo, hi in edges:
        idx = [i for i in range(len(qids)) if lo <= ref_min_margin[i] < hi]
        if not idx:
            buckets.append({"lo": lo, "hi": hi, "n": 0, "flip": 0})
            continue
        flip = 0
        for i in idx:
            q = qids[i]
            s = Vmodel @ Qb1m[i]
            if [shas[j] for j in topk_from_scores(s, shas, qsha[q], TOP_K)] != ref_shas[i]:
                flip += 1
        buckets.append({"lo": lo, "hi": hi, "n": len(idx), "flip": flip,
                        "flip_rate": round(flip / len(idx), 4)})
    summary["flip_rate_by_min_margin_bucket"] = buckets
    for b in buckets:
        print(f"  margin [{b['lo']:.0e},{b['hi']:.0e}) n={b['n']:5d} flip={b['flip']:4d} rate={b.get('flip_rate','-')}")

    (OUT / "arith_variants.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {OUT/'arith_variants.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
