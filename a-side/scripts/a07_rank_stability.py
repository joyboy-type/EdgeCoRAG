"""检索排序一致性定位实验：量化"同一语料、同一模型"下 top10 内部排序的可变性。

对应本轮任务 1。回答的问题不是"哪个排序对"，而是：
  给定同一份规范化语料（corpus_v1，4,712 个唯一内容）与同一个模型 revision，
  改变**查询侧编码条件**（batch 组成、dtype、归一化位置）会不会改变 top10 内部顺序，
  同时保持 top10 集合与 cosine top3 不变——以及相邻分差要多小才会发生。

设计要点：
  * 索引侧向量固定（同一语料编码），只有查询侧变化 → 与同机 smoke 的实际情况一致
    （smoke 复用历史索引，只现场编码查询图，batch=1）。
  * 归一化分两种"位置"：
      model_norm  —— 与 sentence-transformers 默认一致，在模型 dtype(bf16) 内归一化；
                     向量范数不等于 1（实测 0.999~1.004），因此点积并非严格 cosine；
      fp32_renorm —— cast 到 float32 后重新归一化，点积即 cosine。
  * 排序一律用 numpy float32 BLAS，固定 argsort(kind="stable")。

用法:
    python scripts/a07_rank_stability.py --stage all
    python scripts/a07_rank_stability.py --stage corpus     # 只编码语料并缓存
    python scripts/a07_rank_stability.py --stage rank       # 只做排序复算
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import project_config as cfg  # noqa: E402

cfg.apply_env()

MODEL_ID = "google/embeddinggemma-2"
REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
EMB = Path(r"E:\EdgeCoRAG-A-store\emb_v1")
OUT = ROOT / "outputs" / "rank_stability"

SMOKE5 = ["mragb:10", "mragb:1049", "mragb:1051", "mragb:1062", "mragb:1117"]
COHORTS = {
    "smoke_20": ROOT / "splits" / "smoke_20.v2.txt",
    "dev_150": ROOT / "splits" / "dev.v2.txt",
    "frozen_test": ROOT / "splits" / "frozen_test.v2.txt",
}
TOP_K = 10
SELF_REMOVE_K = TOP_K + 1
BATCH = 16


# ---------------------------------------------------------------- helpers
def read_qids(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s if s.startswith("mragb:") else f"mragb:{s}")
    return out


def cohort_of() -> dict[str, str]:
    m: dict[str, str] = {}
    for name, p in COHORTS.items():
        for q in read_qids(p):
            m.setdefault(q, name)
    return m


def manifest() -> tuple[list[str], np.ndarray]:
    rows = (CORPUS / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]
    shas, w = [], []
    for r in rows:
        f = r.split(",")
        shas.append(f[1])
        w.append([float(f[3]), float(f[4])])
    return shas, np.asarray(w, dtype=np.float32)


def load_model(dtype_name: str):
    import torch
    from sentence_transformers import SentenceTransformer

    if dtype_name == "fp32":
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        dtype = torch.float32
    else:
        dtype = torch.bfloat16
    m = SentenceTransformer(
        MODEL_ID,
        revision=REV,
        config_kwargs={"audio_config": None},
        model_kwargs={"torch_dtype": dtype},
        device="cuda" if torch.cuda.is_available() else "cpu",
    )
    return m


def encode_images(model, images, batch_size: int) -> np.ndarray:
    """返回 float32 的 pooled 向量（未做我们的归一化）。"""
    v = model.encode(
        [{"image": im} for im in images],
        batch_size=batch_size,
        normalize_embeddings=False,   # 归一化位置由本脚本显式控制
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return np.asarray(v, dtype=np.float32)


def norm_views(v: np.ndarray) -> dict[str, np.ndarray]:
    """两种归一化口径。"""
    import torch

    out = {}
    # (a) 模型 dtype 内归一化：用 bf16 算术模拟 sentence-transformers 的 Normalize
    t = torch.from_numpy(v).to(torch.bfloat16)
    t = t / t.norm(dim=1, keepdim=True)
    out["model_norm"] = t.float().numpy()
    # (b) float32 重新归一化：点积即 cosine
    n = np.linalg.norm(v, axis=1, keepdims=True)
    out["fp32_renorm"] = v / np.maximum(n, 1e-12)
    return out


# ---------------------------------------------------------------- corpus images
def corpus_images(shas: list[str]):
    from PIL import Image

    for sha in shas:
        p = CORPUS / "images" / sha[:2] / f"{sha}.jpg"
        im = Image.open(p)
        im.load()
        yield im.convert("RGB")


def query_images(qids: list[str]) -> list:
    from PIL import Image

    # 从 occurrences.csv 找 query 行的 sha，再读语料文件
    want = set(qids)
    sha_of: dict[str, str] = {}
    for line in (CORPUS / "occurrences.csv").read_text(encoding="utf-8").splitlines()[1:]:
        qid, role, _rank, sha = line.split(",")
        if role == "query" and qid in want:
            sha_of[qid] = sha
    missing = want - set(sha_of)
    if missing:
        raise RuntimeError(f"缺 query 图: {sorted(missing)[:5]}")
    out = []
    for q in qids:
        p = CORPUS / "images" / sha_of[q][:2] / f"{sha_of[q]}.jpg"
        im = Image.open(p)
        im.load()
        out.append(im.convert("RGB"))
    return out, sha_of


# ---------------------------------------------------------------- ranking
def rank_pool(q: np.ndarray, V: np.ndarray, shas: list[str], self_sha: str) -> tuple[list[int], np.ndarray]:
    scores = V @ q  # float32 BLAS
    order = np.argsort(-scores, kind="stable")
    keep = [int(i) for i in order if shas[int(i)] != self_sha][:SELF_REMOVE_K]
    return keep, scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all", "corpus", "rank"], default="all")
    ap.add_argument("--batch", type=int, default=BATCH)
    args = ap.parse_args()
    EMB.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    shas, dims = manifest()
    print(f"语料 {len(shas)} 行")

    # ------------------------------------------------------------ 1) 语料编码
    if args.stage in ("all", "corpus"):
        for dt in ("bf16", "fp32"):
            npz = EMB / f"corpus_{dt}.npz"
            if npz.exists():
                print(f"[跳过] {npz.name} 已存在")
                continue
            t0 = time.time()
            model = load_model(dt)
            vecs = []
            batch_imgs = []
            n = 0
            for im in corpus_images(shas):
                batch_imgs.append(im)
                if len(batch_imgs) == args.batch:
                    vecs.append(encode_images(model, batch_imgs, args.batch))
                    n += len(batch_imgs)
                    batch_imgs = []
                    if n % (args.batch * 20) == 0:
                        print(f"  {dt} {n}/{len(shas)}  {time.time() - t0:.0f}s", flush=True)
            if batch_imgs:
                vecs.append(encode_images(model, batch_imgs, args.batch))
            V = np.concatenate(vecs, axis=0)
            assert V.shape == (len(shas), 768), V.shape
            np.savez_compressed(npz, V=V, sha=np.array(shas))
            print(f"[语料] {dt} {V.shape} {time.time() - t0:.0f}s -> {npz.name}")
            del model
            import torch

            torch.cuda.empty_cache()
    if args.stage == "corpus":
        return 0

    # ------------------------------------------------------------ 2) 查询编码
    coh = cohort_of()
    qids = sorted(coh, key=lambda s: int(s.split(":")[1]))
    print(f"查询 {len(qids)} 题（smoke20+dev150+frozen1033）")
    qimgs, qsha = query_images(qids)

    qvec_path = EMB / "queries.npz"
    if not qvec_path.exists():
        store: dict[str, np.ndarray] = {}
        for dt in ("bf16", "fp32"):
            model = load_model(dt)
            store[f"{dt}_b1"] = encode_images(model, qimgs, 1)
            store[f"{dt}_b{args.batch}"] = encode_images(model, qimgs, args.batch)
            print(f"[查询] {dt} 完成")
            del model
            import torch

            torch.cuda.empty_cache()
        np.savez_compressed(qvec_path, qid=np.array(qids), sha=np.array([qsha[q] for q in qids]), **store)
    qz = np.load(qvec_path, allow_pickle=True)
    qvec = {k: qz[k] for k in qz.files if k not in ("qid", "sha")}
    print(f"查询编码键: {sorted(qvec)}")

    # ------------------------------------------------------------ 3) 排序复算
    corpus = {}
    for dt in ("bf16", "fp32"):
        z = np.load(EMB / f"corpus_{dt}.npz", allow_pickle=True)
        corpus[dt] = norm_views(z["V"])
        assert list(z["sha"]) == shas

    variants: dict[str, tuple[str, str, str]] = {}
    for cdt in ("bf16", "fp32"):
        for cnv in ("model_norm", "fp32_renorm"):
            for qk in (["bf16_b1", "bf16_b16", "fp32_b1", "fp32_b16"] if cdt == "fp32" else ["bf16_b1", "bf16_b16"]):
                for qnv in ("model_norm", "fp32_renorm"):
                    name = f"idx{cdt}.{cnv}|q{qk}.{qnv}"
                    variants[name] = (cdt, f"{qk}|{qnv}", cnv)

    ref_name = "idxbf16.model_norm|qbf16_b16.model_norm"   # 历史缓存形态（批量编码、模型内归一化）
    if ref_name not in variants:
        raise RuntimeError(f"参考变体不存在: {ref_name}")

    # 参考排序
    ref_top: dict[str, list[str]] = {}
    Vref = corpus["bf16"]["model_norm"]
    qref = qvec["bf16_b16"]
    for i, q in enumerate(qids):
        keep, _ = rank_pool(qref[i], Vref, shas, qsha[q])
        ref_top[q] = [shas[j] for j in keep[:TOP_K]]
    print(f"参考变体完成: {ref_name}")

    rows = []
    detail = []
    for vname, (cdt, qkey, cnv) in variants.items():
        qk, qnv = qkey.split("|")
        V = corpus[cdt][cnv]
        qfull = norm_views(qvec[qk])[qnv]
        order_diff = member_diff = top3_diff = 0
        for i, q in enumerate(qids):
            keep, scores = rank_pool(qfull[i], V, shas, qsha[q])
            top = [shas[j] for j in keep[:TOP_K]]
            s = [float(scores[j]) for j in keep[:TOP_K]]
            ref = ref_top[q]
            eq = top == ref
            mem = set(top) == set(ref)
            t3 = top[:3] == ref[:3]
            if not eq:
                order_diff += 1
            if not mem:
                member_diff += 1
            if not t3:
                top3_diff += 1
            margins = [s[k] - s[k + 1] for k in range(len(s) - 1)]
            pos_common = [top.index(x) for x in ref if x in top]
            rows.append({
                "variant": vname, "qid": q, "cohort": coh[q],
                "order_equal": eq, "membership_equal": mem, "top3_equal": t3,
                "n_positions_changed": sum(1 for a, b in zip(top, ref) if a != b),
                "min_adjacent_margin": round(min(margins), 8) if margins else "",
                "max_abs_adjacent_margin": round(max(margins), 8) if margins else "",
                "top1": top[0], "ref_top1": ref[0],
                "self_sha_removed": qsha[q],
            })
            if q in SMOKE5:
                for rnk, (sha, sc) in enumerate(zip(top, s), 1):
                    detail.append({"qid": q, "variant": vname, "rank": rnk, "sha256": sha,
                                   "score": round(sc, 9), "in_ref_top10": sha in ref,
                                   "ref_rank": (ref.index(sha) + 1) if sha in ref else ""})
        print(f"{vname:46s} order_diff={order_diff:4d}/{len(qids)}  member_diff={member_diff:3d}  top3_diff={top3_diff:3d}")

    import csv

    def write_csv(path: Path, records: list[dict]) -> None:
        if not records:
            return
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)

    write_csv(OUT / "rank_stability_by_qid.csv", rows)
    write_csv(OUT / "smoke5_rank_detail.csv", detail)

    summary = {"reference_variant": ref_name, "corpus_rows": len(shas), "queries": len(qids),
               "batch": args.batch, "variants": {}}
    for vname in variants:
        sub = [r for r in rows if r["variant"] == vname]
        s5 = [r for r in sub if r["qid"] in SMOKE5]
        s20 = [r for r in sub if r["cohort"] == "smoke_20"]
        summary["variants"][vname] = {
            "order_diff_all": sum(not r["order_equal"] for r in sub),
            "order_diff_smoke5": sum(not r["order_equal"] for r in s5),
            "order_diff_smoke20": sum(not r["order_equal"] for r in s20),
            "membership_diff_all": sum(not r["membership_equal"] for r in sub),
            "top3_diff_all": sum(not r["top3_equal"] for r in sub),
            "smoke5_qids_with_order_diff": [r["qid"] for r in s5 if not r["order_equal"]],
        }
    (OUT / "rank_stability_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
