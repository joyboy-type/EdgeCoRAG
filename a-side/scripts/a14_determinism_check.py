"""同配置可重复性检查：同一编码条件重复执行是否逐位一致。

同机 smoke 观察到"重复请求间稳定"。本检查确认该性质在我们的复现环境同样成立，
从而把"差异"归因范围收窄到"配置不同"，而不是"随机性"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import project_config as cfg  # noqa: E402

cfg.apply_env()

CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")
OUT = ROOT / "outputs" / "rank_stability"
MODEL_ID = "google/embeddinggemma-2"
REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"


def main() -> int:
    import torch
    from PIL import Image
    from sentence_transformers import SentenceTransformer

    torch.backends.cuda.matmul.allow_tf32 = False
    shas = {}
    for line in (CORPUS / "occurrences.csv").read_text(encoding="utf-8").splitlines()[1:]:
        qid, role, _rank, sha = line.split(",")
        if role == "query" and qid in ("mragb:10", "mragb:1049"):
            shas[qid] = sha
    imgs = []
    for q in ("mragb:10", "mragb:1049"):
        p = CORPUS / "images" / shas[q][:2] / f"{shas[q]}.jpg"
        im = Image.open(p)
        im.load()
        imgs.append(im.convert("RGB"))

    out = {"model": MODEL_ID, "revision": REV, "runs": []}
    for dtype_name, td in (("bf16", torch.bfloat16), ("fp32", torch.float32)):
        m = SentenceTransformer(MODEL_ID, revision=REV, config_kwargs={"audio_config": None},
                                model_kwargs={"torch_dtype": td},
                                device="cuda" if torch.cuda.is_available() else "cpu")
        for bs in (1, 5):
            a = np.asarray(m.encode([{"image": im} for im in imgs], batch_size=bs,
                                    normalize_embeddings=False, show_progress_bar=False), dtype=np.float32)
            b = np.asarray(m.encode([{"image": im} for im in imgs], batch_size=bs,
                                    normalize_embeddings=False, show_progress_bar=False), dtype=np.float32)
            identical = bool(np.array_equal(a, b))
            out["runs"].append({"dtype": dtype_name, "batch": bs, "identical": identical,
                                "max_abs_delta": float(np.abs(a - b).max())})
            print(f"{dtype_name} batch={bs} identical={identical} max|Δ|={float(np.abs(a-b).max()):.3e}")
        del m
        torch.cuda.empty_cache()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "determinism_check.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = all(r["identical"] for r in out["runs"])
    print(f"同配置逐位一致: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
