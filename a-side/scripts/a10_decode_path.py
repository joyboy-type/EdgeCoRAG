"""解码路径（原始 parquet 字节 vs JPEG q95 重编码字节）对检索排序的影响。

任务 1 的第三个变量组，只针对 5 道 smoke 题（图像少，可快速穷举）。
历史缓存与现场编码可能分别从"原始字节"和"落盘 q95 文件"解码，需要量化这个差异。

用法: python scripts/a10_decode_path.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import project_config as cfg  # noqa: E402

cfg.apply_env()

CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
EMB = Path(r"E:\EdgeCoRAG-A-store\emb_v1")
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
OUT = ROOT / "outputs" / "rank_stability"
SMOKE5 = ["mragb:10", "mragb:1049", "mragb:1051", "mragb:1062", "mragb:1117"]
MODEL_ID = "google/embeddinggemma-2"
REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"
TOP_K = 10


def model_norm(v: np.ndarray) -> np.ndarray:
    import torch

    t = torch.from_numpy(np.asarray(v, dtype=np.float32)).to(torch.bfloat16)
    t = t / t.norm(dim=1, keepdim=True)
    return t.float().numpy()


def raw_query_images(want: dict[str, str]):
    from PIL import Image

    out = {}
    for sh in sorted(DATA.glob("test-*.parquet")):
        pf = pq.ParquetFile(sh)
        for rg in range(pf.num_row_groups):
            for row in pf.read_row_group(rg, columns=["id", "image"]).to_pylist():
                q = f"mragb:{row['id']}"
                if q in want and q not in out:
                    im = Image.open(io.BytesIO(row["image"]["bytes"]))
                    im.load()
                    out[q] = im.convert("RGB")
        if len(out) == len(want):
            break
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import torch
    from sentence_transformers import SentenceTransformer

    torch.backends.cuda.matmul.allow_tf32 = False
    z = np.load(EMB / "corpus_bf16.npz", allow_pickle=True)
    shas = [str(x) for x in z["sha"]]
    V = model_norm(z["V"])

    qz = np.load(EMB / "queries.npz", allow_pickle=True)
    qsha = {str(q): str(s) for q, s in zip(qz["qid"], qz["sha"])}
    qpos = {str(q): i for i, q in enumerate(qz["qid"])}

    from PIL import Image

    q95_imgs = {}
    for q in SMOKE5:
        p = CORPUS / "images" / qsha[q][:2] / f"{qsha[q]}.jpg"
        im = Image.open(p)
        im.load()
        q95_imgs[q] = im.convert("RGB")
    raw_imgs = raw_query_images({q: qsha[q] for q in SMOKE5})
    print(f"载入 q95={len(q95_imgs)} raw={len(raw_imgs)}")

    m = SentenceTransformer(MODEL_ID, revision=REV, config_kwargs={"audio_config": None},
                            model_kwargs={"torch_dtype": torch.bfloat16},
                            device="cuda" if torch.cuda.is_available() else "cpu")

    def enc(imgs: list, bs: int) -> np.ndarray:
        v = m.encode([{"image": im} for im in imgs], batch_size=bs,
                     normalize_embeddings=False, show_progress_bar=False, convert_to_numpy=True)
        return model_norm(np.asarray(v, dtype=np.float32))

    order = SMOKE5
    variants = {
        "q95_b1": enc([q95_imgs[q] for q in order], 1),
        "q95_b5": enc([q95_imgs[q] for q in order], 5),
        "raw_b1": enc([raw_imgs[q] for q in order], 1),
        "raw_b5": enc([raw_imgs[q] for q in order], 5),
    }

    def rank(q: str, vec: np.ndarray) -> list[str]:
        s = V @ vec
        o = np.lexsort((np.asarray(shas), -s))
        return [shas[int(j)] for j in o if shas[int(j)] != qsha[q]][:TOP_K]

    ref = {q: rank(q, variants["q95_b5"][i]) for i, q in enumerate(order)}
    res: dict = {"queries": order, "variants": {}, "score_delta": {}}
    for name, vecs in variants.items():
        per_q = {}
        for i, q in enumerate(order):
            top = rank(q, vecs[i])
            per_q[q] = {"order_equal": top == ref[q],
                        "membership_equal": set(top) == set(ref[q]),
                        "top3_equal": top[:3] == ref[q][:3],
                        "top5": [t[:8] for t in top[:5]]}
        res["variants"][name] = per_q
        # 与 q95_b5 的余弦差（同题同维度）
        d = np.abs(vecs - variants["q95_b5"]).max(axis=1)
        res["score_delta"][name] = {q: float(d[i]) for i, q in enumerate(order)}

    print(json.dumps({k: {q: (v["order_equal"], v["top3_equal"], v["membership_equal"]) for q, v in vv.items()}
                      for k, vv in res["variants"].items()}, indent=2, ensure_ascii=False))
    print(json.dumps(res["score_delta"], indent=2, ensure_ascii=False))
    (OUT / "decode_path.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {OUT/'decode_path.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
