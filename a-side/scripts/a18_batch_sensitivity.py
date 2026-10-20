"""跨栈批大小敏感性复核：让 B 在自己的栈上重跑"batch 16 → 1 是否改变排序"。

为什么需要：A 侧测得的 `0/1203` 绑定在 A 的栈上
（torch 2.11.0 / torchvision 0.26.0 / transformers 5.19.0 / Pillow 12.3.0 / numpy 2.5.2）。
B 的服务器与 round-1 是 torch 2.8.0 / torchvision 0.23.0 / Pillow 11.3.0，
同一协议在不同栈上是否仍逐条一致，必须由 B 用自己的环境产出回执，不能由 A 的数值代替。

本脚本只做一件事：
  1) 用固定协议把语料编码一遍（batch=BIG）；
  2) 把同一批查询分别按 batch=BIG 与 batch=1 编码；
  3) 在同一份语料向量上排序、剔除查询图自身、取 top-k；
  4) 输出 {changed_order, changed_set, changed_top3, total}。

协议（与 a-side/retrieval-interface-v1 一致，不可改）：
  * 解码 = PIL 打开语料目录里的 q95 字节 → RGB
  * dtype 默认 fp32；TF32 关闭；`normalize_embeddings=False` 后由本脚本在 float32 层 L2 归一化
  * 排序 = lexsort(-score, sha256) ；无自匹配 = 先剔除查询图 sha 再取 top-k
  * 查询批只做"16 个一组"与"逐个"两档，其余完全相同

用法：
    python a18_batch_sensitivity.py --schema              # 只打印回执 schema
    python a18_batch_sensitivity.py --self-check          # 只跑纯逻辑自检（不需要模型/GPU）
    export EDGECORAG_CORPUS=$HOME/edgecorag/corpus_v1
    python a18_batch_sensitivity.py --qids-file splits/smoke_20.v2.txt --out receipt_a18.json

    # 快速联调（只取前 200 张语料，结果不可作为回执）
    python a18_batch_sensitivity.py --corpus-limit 200 --out receipt_quick.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a00_paths  # noqa: E402

ROOT = a00_paths.side_root()
MODEL_ID = "google/embeddinggemma-2"
REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"
ENV_CORPUS = "EDGECORAG_CORPUS"

RECEIPT_SCHEMA = {
    "schema": "a18_batch_sensitivity_receipt/v1",
    "required": ["schema", "generated_at", "stack", "model", "corpus", "queries", "params", "results", "verdict"],
    "fields": {
        "schema": "固定字符串 a18_batch_sensitivity_receipt/v1",
        "generated_at": "UTC ISO8601",
        "stack": {"torch": "", "torchvision": "", "transformers": "",
                  "sentence_transformers": "", "pillow": "", "numpy": "",
                  "cuda": "", "device": "", "cpu_thread_env": "生效值或 unfixed"},
        "model": {"id": MODEL_ID, "revision": REV, "dtype": "fp32|bf16",
                  "tf32": False, "weights_sha256": "可选，给出则用于绑定权重"},
        "corpus": {"rows": "int", "content_digest_sha256": "取自 corpus_meta.json",
                   "limit_applied": "int|null"},
        "queries": {"file": "题单路径或 occurrences", "n": "int"},
        "params": {"batch_pair": [16, 1], "topk": 10,
                   "normalize": "float32_l2_renorm", "order_rule": "score desc, sha256 asc"},
        "results": {"changed_order": "int", "changed_set": "int", "changed_top3": "int",
                    "total": "int", "flip_rate": "float"},
        "verdict": "stack_invariant（changed_order==0）| stack_sensitive",
    },
}


# ---------------------------------------------------------------- 纯逻辑
def norm32(v):
    import numpy as np
    a = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(a, axis=1, keepdims=True)
    return a / np.maximum(n, 1e-12)


def rank_topk(scores, shas, self_sha, k: int) -> list[str]:
    import numpy as np
    order = np.lexsort((np.asarray(shas), -np.asarray(scores)))
    return [shas[int(j)] for j in order if shas[int(j)] != self_sha][:k]


def compare(V, Q_big, Q_small, shas, qshas, k: int) -> dict:
    """同一语料向量下，两种查询编码的排序差异。"""
    import numpy as np
    changed_order = changed_set = changed_top3 = 0
    for i, q_sha in enumerate(qshas):
        a = rank_topk(V @ Q_big[i], shas, q_sha, k)
        b = rank_topk(V @ Q_small[i], shas, q_sha, k)
        if a != b:
            changed_order += 1
        if set(a) != set(b):
            changed_set += 1
        if a[:3] != b[:3]:
            changed_top3 += 1
    n = len(qshas)
    return {"changed_order": changed_order, "changed_set": changed_set,
            "changed_top3": changed_top3, "total": n,
            "flip_rate": round(changed_order / n, 6) if n else None}


def self_check() -> int:
    """不需要模型：验证比较逻辑本身。"""
    import numpy as np
    rng = np.random.default_rng(7)
    n_corpus, dim, n_q = 64, 16, 8
    V = norm32(rng.normal(size=(n_corpus, dim)))
    Q = norm32(rng.normal(size=(n_q, dim)))
    shas = [f"{i:064x}" for i in range(n_corpus)]
    qshas = [shas[i] for i in range(n_q)]
    same = compare(V, Q, Q.copy(), shas, qshas, 10)
    ok1 = same["changed_order"] == 0 and same["total"] == n_q
    perturbed = Q.copy()
    for i in range(n_q):  # 加 ~1e-2 扰动，足以在同分附近改序
        perturbed[i] = norm32((perturbed[i] + rng.normal(scale=1e-2, size=dim))[None, :])[0]
    moved = compare(V, Q, perturbed, shas, qshas, 10)
    ok2 = moved["changed_order"] > 0
    checks = [
        {"check": "identical_inputs_zero_change", "pass": bool(ok1), "detail": json.dumps(same)},
        {"check": "perturbed_inputs_detected", "pass": bool(ok2), "detail": json.dumps(moved)},
    ]
    passed = sum(c["pass"] for c in checks)
    print(json.dumps({"passed": passed, "total": len(checks), "checks": checks},
                     indent=2, ensure_ascii=False))
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------- 环境
def resolve_corpus(cli_value: str | None) -> Path:
    raw = cli_value or os.environ.get(ENV_CORPUS)
    if not raw:
        raise SystemExit(
            f"缺少语料目录：用 --corpus <dir> 或环境变量 {ENV_CORPUS}=<dir>。\n"
            "该目录由 a06_build_corpus.py 生成（含 corpus_manifest.csv / corpus_meta.json / images/）。"
        )
    p = Path(raw).expanduser().resolve()
    for n in ("corpus_manifest.csv", "corpus_meta.json", "images"):
        if not (p / n).exists():
            raise SystemExit(f"语料目录 {p} 缺少 {n}；请先运行 a06_build_corpus.py --store {p}")
    return p


def read_qids(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s if s.startswith("mragb:") else f"mragb:{s}")
    return out


def query_sha_map(corpus: Path, qids: list[str]) -> dict[str, str]:
    want = set(qids)
    m: dict[str, str] = {}
    for line in (corpus / "occurrences.csv").read_text(encoding="utf-8").splitlines()[1:]:
        qid, role, _rank, sha = line.split(",")
        if role == "query" and qid in want:
            m[qid] = sha
    missing = want - set(m)
    if missing:
        raise SystemExit(f"occurrences.csv 里缺少这些查询图的 query 行：{sorted(missing)[:5]}")
    return m


def stack_info() -> dict:
    import importlib.metadata as md

    def ver(name: str) -> str:
        try:
            return md.version(name)
        except Exception:  # noqa: BLE001
            return "missing"

    import torch

    info = {
        "torch": torch.__version__,
        "torchvision": ver("torchvision"),
        "transformers": ver("transformers"),
        "sentence_transformers": ver("sentence-transformers"),
        "pillow": ver("Pillow"),
        "numpy": ver("numpy"),
        "cuda": getattr(torch.version, "cuda", None),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else platform.processor() or "cpu",
        "cpu_thread_env": os.environ.get("OMP_NUM_THREADS", "unfixed"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }
    return info


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true", help="打印回执 schema 后退出")
    ap.add_argument("--self-check", action="store_true", help="只跑纯逻辑自检（不需要模型/GPU）")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--qids-file", type=Path, default=a00_paths.splits_dir() / "smoke_20.v2.txt")
    ap.add_argument("--dtype", default="fp32", choices=["fp32", "bf16"])
    ap.add_argument("--batches", default="16,1", help="两个批大小，默认 16,1")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--corpus-limit", type=int, default=None, help="只取前 N 张语料（仅联调，非回执）")
    ap.add_argument("--weights-sha256", default=None, help="可选：编码器权重文件 sha256")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.schema:
        print(json.dumps(RECEIPT_SCHEMA, indent=2, ensure_ascii=False))
        return 0
    if args.self_check:
        return self_check()

    corpus = resolve_corpus(args.corpus)
    qids = read_qids(args.qids_file)
    qsha = query_sha_map(corpus, qids)
    b_big, b_small = (int(x) for x in args.batches.split(","))

    manifest = (corpus / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]
    shas = [r.split(",")[1] for r in manifest]
    if args.corpus_limit:
        shas = shas[: args.corpus_limit]
    meta = json.loads((corpus / "corpus_meta.json").read_text(encoding="utf-8"))
    print(f"语料 {len(shas)} 行；查询 {len(qids)} 题；batch {b_big} vs {b_small}；dtype {args.dtype}")

    import torch
    from PIL import Image
    from sentence_transformers import SentenceTransformer

    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    dtype = torch.float32 if args.dtype == "fp32" else torch.bfloat16
    model = SentenceTransformer(
        MODEL_ID, revision=REV,
        config_kwargs={"audio_config": None},
        model_kwargs={"torch_dtype": dtype},
        device="cuda" if torch.cuda.is_available() else "cpu",
    )

    def encode(images: list, bs: int):
        v = model.encode([{"image": im} for im in images], batch_size=bs,
                         normalize_embeddings=False, show_progress_bar=False,
                         convert_to_numpy=True)
        return norm32(v)

    def load(sha: str):
        im = Image.open(corpus / "images" / sha[:2] / f"{sha}.jpg")
        im.load()
        return im.convert("RGB")

    V = encode([load(s) for s in shas], b_big)
    q_imgs = [load(qsha[q]) for q in qids]
    Q_big = encode(q_imgs, b_big)
    Q_small = encode(q_imgs, b_small)

    res = compare(V, Q_big, Q_small, shas, [qsha[q] for q in qids], args.topk)
    receipt = {
        "schema": "a18_batch_sensitivity_receipt/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stack": stack_info(),
        "model": {"id": MODEL_ID, "revision": REV, "dtype": args.dtype,
                  "tf32": False, "weights_sha256": args.weights_sha256},
        "corpus": {"rows": len(shas),
                   "content_digest_sha256": meta.get("content_digest_sha256"),
                   "limit_applied": args.corpus_limit},
        "queries": {"file": str(args.qids_file), "n": len(qids)},
        "params": {"batch_pair": [b_big, b_small], "topk": args.topk,
                   "normalize": "float32_l2_renorm", "order_rule": "score desc, sha256 asc"},
        "results": res,
        "verdict": "stack_invariant" if res["changed_order"] == 0 else "stack_sensitive",
    }
    out = args.out or Path("receipt_a18.json")
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"results": res, "verdict": receipt["verdict"]}, ensure_ascii=False, indent=2))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
