"""EG2（EmbeddingGemma-2）多模态编码接口自检：确认本机可离线加载与逐图编码。

只做接口与确定性探测，不产出实验结果：
  - 能否用 SentenceTransformer 加载 revision 固定的本地快照
  - 图像输入形式（{"image": PIL}）是否被支持
  - batch=1 与 batch=N 的向量是否逐位一致（这是检索排序差异定位的前置事实）

用法: python scripts/_smoke_eg2_api.py
"""

from __future__ import annotations

import io
import sys
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


def load_images(n: int = 4):
    from PIL import Image

    sh = sorted(DATA.glob("test-*.parquet"))[0]
    tbl = pq.ParquetFile(sh).read_row_group(0, columns=["id", "image", "retrieved_images"])
    row = tbl.to_pylist()[0]
    out = [(f"q{row['id']}", Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB"))]
    for j, r in enumerate(row["retrieved_images"][:n]):
        out.append((f"r{j}", Image.open(io.BytesIO(r["bytes"])).convert("RGB")))
    return out


def main() -> int:
    import torch
    from sentence_transformers import SentenceTransformer

    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()} bf16={torch.cuda.is_bf16_supported()}")
    dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float32
    print(f"dtype={dtype}")
    m = SentenceTransformer(
        MODEL_ID,
        revision=REV,
        config_kwargs={"audio_config": None},
        model_kwargs={"torch_dtype": dtype},
        device="cuda" if torch.cuda.is_available() else "cpu",
    )
    print(f"max_seq_length={m.max_seq_length} dim={m.get_sentence_embedding_dimension()}")

    imgs = load_images(4)
    print(f"images={len(imgs)} sizes={[im.size for _, im in imgs]}")

    # 单图逐个编码
    singles = np.stack([np.asarray(m.encode([{"image": im}], normalize_embeddings=True), dtype=np.float32)[0][None, :][0] for _, im in imgs])
    print(f"singles shape={singles.shape} norms={np.linalg.norm(singles, axis=1)}")

    # 批量编码
    batched = np.asarray(m.encode([{"image": im} for _, im in imgs], normalize_embeddings=True), dtype=np.float32)
    print(f"batched shape={batched.shape}")

    d = np.abs(singles - batched)
    cos = (singles * batched).sum(axis=1)
    print(f"max|Δ|={d.max():.3e}  per-row max|Δ|={[f'{x:.2e}' for x in d.max(axis=1)]}")
    print(f"cos(single,batch)={[f'{x:.9f}' for x in cos]}")
    print(f"bitwise equal rows={int((d.max(axis=1) == 0).sum())}/{len(imgs)}")

    # 单图在不同 batch 位置的影响（同图放在 batch 首位 vs 末位 vs 单独）
    solo = np.asarray(m.encode([{"image": imgs[0][1]}], normalize_embeddings=True), dtype=np.float32)
    padded = np.asarray(m.encode([{"image": imgs[0][1]}, {"image": imgs[1][1]}], normalize_embeddings=True), dtype=np.float32)
    print(f"solo vs in-batch cos={float((solo * padded[0]).sum()):.9f} max|Δ|={float(np.abs(solo[0] - padded[0]).max()):.3e}")

    print("\n[内存/显存]")
    if torch.cuda.is_available():
        print(f"allocated={torch.cuda.memory_allocated() / 1024 ** 2:.1f} MiB reserved={torch.cuda.memory_reserved() / 1024 ** 2:.1f} MiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
