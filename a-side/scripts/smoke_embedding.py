"""A-P0-2 起点: EmbeddingGemma 2 图文向量检索 + 维度截断实验。

对应任务书实验 A-P0-2:
    输出文件: retrieval_by_dim.csv
    指标: R@1 / R@5 / MRR; 维度 128/256/512/768

严格遵循任务书第 3 节的精度与使用规则:
  * 常规 PyTorch 激活不要 FP16;CUDA 可 BF16 则 BF16,否则 FP32
  * 仅图文时 config_kwargs={"audio_config": None} 禁用音频
  * 文本 query 加检索任务前缀,图像不加文本前缀
  * 截断嵌入后必须重新归一化,查询与库用相同维度

用法:
    # 自检(不需要数据): 验证模型可加载、嵌入有限、维度截断与排序自洽
    python scripts/smoke_embedding.py --self-test

    # 真实检索评测(需要图片与标注)
    python scripts/smoke_embedding.py --images-dir data/images --manifest manifest.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "google/embeddinggemma-2"
# EmbeddingGemma 2 的检索任务前缀(任务书要求: 文本 query 加前缀, 图像不加)
QUERY_PREFIX = "task: search result | query: "
DIMS = (128, 256, 512, 768)


def setup_env() -> None:
    """必须在导入 sentence_transformers / huggingface_hub 之前设置。

    缓存位置由 scripts/project_config.py 决定(工作区之外)。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import project_config as cfg
    cfg.apply_env()


def load_model():
    import torch
    from sentence_transformers import SentenceTransformer

    # 精度规则: 不用 FP16;BF16 可用则 BF16,否则 FP32
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        dtype = torch.bfloat16
        dtype_name = "bfloat16"
    else:
        dtype = torch.float32
        dtype_name = "float32"
    print(f"[模型] {MODEL_ID}")
    print(f"[精度] {dtype_name} (cuda_available={torch.cuda.is_available()})")

    t0 = time.time()
    model = SentenceTransformer(
        MODEL_ID,
        config_kwargs={"audio_config": None},   # text + vision, 禁用音频
        model_kwargs={"torch_dtype": dtype},
    )
    print(f"[模型] 加载完成,用时 {time.time() - t0:.1f}s")
    if torch.cuda.is_available():
        print(f"[显存] 已分配 {torch.cuda.memory_allocated() / 1024 ** 3:.2f} GiB")
    return model


def truncate_and_renorm(vec, dim: int):
    """截断到 dim 维并重新归一化(任务书硬性要求)。"""
    import numpy as np

    v = np.asarray(vec, dtype=np.float32)
    v = v[..., :dim]
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def self_test(model) -> int:
    """不依赖外部数据的自检: 验证接口、数值健全性、维度截断自洽性。"""
    import numpy as np

    print("\n" + "=" * 72)
    print("自检模式: 使用合成图像验证接口与数值健全性")
    print("=" * 72)

    # 造三张可区分的合成图: 纯红 / 纯绿 / 红绿棋盘
    from PIL import Image

    size = 256
    red = Image.new("RGB", (size, size), (220, 30, 30))
    green = Image.new("RGB", (size, size), (30, 200, 60))
    checker = Image.new("RGB", (size, size), (255, 255, 255))
    px = checker.load()
    for y in range(size):
        for x in range(size):
            if (x // 16 + y // 16) % 2 == 0:
                px[x, y] = (220, 30, 30)
            else:
                px[x, y] = (30, 200, 60)
    images = {"red": red, "green": green, "checker": checker}
    names = list(images)

    queries = {
        "红": "a solid red image",
        "绿": "a solid green image",
        "棋盘": "a checkerboard pattern alternating red and green squares",
    }

    # 1) query 编码(带检索前缀)
    print("\n[1] query 编码(带前缀)")
    q_times = []
    qvecs = {}
    for k, q in queries.items():
        t0 = time.time()
        v = model.encode(QUERY_PREFIX + q, normalize_embeddings=True)
        q_times.append(time.time() - t0)
        qvecs[k] = np.asarray(v, dtype=np.float32)
        print(f"    {k:4s} dim={qvecs[k].shape} finite={np.isfinite(qvecs[k]).all()}")
    print(f"    编码耗时中位数 {np.median(q_times) * 1000:.1f} ms")

    # 2) 图像编码(不加文本前缀)
    print("\n[2] 图像编码(不加文本前缀)")
    t0 = time.time()
    dvecs = model.encode([{"image": images[n]} for n in names], normalize_embeddings=True)
    img_time = time.time() - t0
    dvecs = np.asarray(dvecs, dtype=np.float32)
    print(f"    shape={dvecs.shape} finite={np.isfinite(dvecs).all()}")
    print(f"    3 张图编码耗时 {img_time * 1000:.1f} ms")

    # 3) 原始嵌入必须有限
    print("\n[3] 数值健全性")
    assert np.isfinite(dvecs).all(), "图像嵌入出现 NaN/Inf"
    for k, v in qvecs.items():
        assert np.isfinite(v).all(), f"query '{k}' 嵌入出现 NaN/Inf"
    print("    ✅ 无 NaN/Inf")

    # 4) 维度截断 + 重新归一化,检查单位范数与排序稳定性
    print("\n[4] 维度截断与重新归一化")
    rows = []
    for dim in DIMS:
        qd = truncate_and_renorm(qvecs["棋盘"], dim)
        xd = truncate_and_renorm(dvecs, dim)
        norms = np.linalg.norm(xd, axis=1)
        sims = xd @ qd
        order = np.argsort(-sims)
        ranked = [(names[i], float(sims[i])) for i in order]
        rows.append({"dim": dim, "top1": ranked[0][0], "ranked": ranked,
                     "norm_ok": bool(np.allclose(norms, 1.0, atol=1e-5))})
        print(f"    dim={dim:4d}  范数归一={rows[-1]['norm_ok']}  "
              f"排序={[r[0] for r in ranked]}  top1 相似度={ranked[0][1]:.4f}")
        assert rows[-1]["norm_ok"], f"dim={dim} 重新归一化失败"

    # 5) 合理性: "棋盘" query 的 top1 应当是棋盘图而非纯色图
    print("\n[5] 语义合理性检查")
    top1 = rows[-1]["top1"]
    ok = top1 == "checker"
    print(f"    dim=768 时 '棋盘' query 的 top1 = {top1}  "
          f"{'✅ 符合预期' if ok else '⚠️ 未命中棋盘图(合成图较极端,需用真实数据复核)'}")
    if not ok:
        print("    注意: 这不一定说明模型有问题,合成纯色图与真实图文分布差距很大。")

    # 6) 输出 csv
    out = ROOT / "outputs" / "retrieval" / "retrieval_self_test.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["query", "dim", "rank", "image", "cosine"])
        for qk, _ in queries.items():
            for r in rows:
                qd = truncate_and_renorm(qvecs[qk], r["dim"])
                xd = truncate_and_renorm(dvecs, r["dim"])
                sims = xd @ qd
                for rank, i in enumerate(np.argsort(-sims), 1):
                    w.writerow([qk, r["dim"], rank, names[i], f"{float(sims[i]):.6f}"])
    print(f"\n[输出] {out}")
    return 0


def main() -> int:
    setup_env()

    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                    help="用合成图自检,不需要外部数据")
    ap.add_argument("--images-dir", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=None)
    args = ap.parse_args()

    if not args.self_test and not args.images_dir:
        ap.error("请指定 --self-test 或 --images-dir")

    model = load_model()
    if args.self_test:
        return self_test(model)
    print("真实检索评测待接入 MRAG-Bench manifest 后实现(A-P0-2 主体)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
