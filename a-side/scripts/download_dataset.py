"""下载并检查 MRAG-Bench 数据集(经 hf-mirror.com)。

**已核对的元数据**(https://hf-mirror.com/api/datasets/uclanlp/MRAG-Bench):
    revision : 43620fde4044bb150e158c67ad7af6b6b11e1da2
    license  : cc-by-4.0
    split    : 只有 test,1353 题  <-- 没有官方 dev/validation split
    features : id, aspect, scenario, image, gt_images, question, A, B, C, D,
               answer_choice, answer, image_type, source, retrieved_images
    storage  : 8,576,331,248 B (约 8.0 GiB)

用法:
    python scripts/download_dataset.py            # 下载 parquet(不含自动解图)
    python scripts/download_dataset.py --inspect  # 检查字段与场景分布
    python scripts/download_dataset.py --materialize --limit 20
                                                  # 把前 20 题的图片落盘 + 建立 ID 映射
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

ROOT = cfg.ROOT
REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"


def parquet_dir() -> Path:
    """数据集 parquet 的本地目录(工作区之外)。"""
    return cfg.store_root() / "datasets" / "mrag_bench" / REVISION


def download() -> Path:
    cfg.apply_env()
    from huggingface_hub import snapshot_download

    dest = parquet_dir()
    print(f"数据集 : {REPO_ID} @ {REVISION[:12]}")
    print(f"目标   : {dest}")
    path = snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        revision=REVISION,
        allow_patterns=["*.parquet", "README.md", ".gitattributes"],
        local_dir=str(dest),
    )
    print(f"✅ 下载完成: {path}")
    return Path(path)


def inspect() -> int:
    """只检查字段、场景分布、图片列形状,不解码全部图片。"""
    cfg.apply_env()
    from datasets import load_dataset

    print(f"加载 {REPO_ID} (streaming 以只读少量样本)\n")
    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)
    it = iter(ds)
    first = next(it)

    print("=== 字段与类型(第一条样本)===")
    for k, v in first.items():
        t = type(v).__name__
        if k in ("gt_images", "retrieved_images"):
            n = len(v) if hasattr(v, "__len__") else "?"
            inner = type(v[0]).__name__ if n and n != "?" else "?"
            print(f"  {k:20s} {t:10s} len={n}  inner={inner}")
        elif k == "image":
            print(f"  {k:20s} {t:10s} {getattr(v, 'size', '')} mode={getattr(v, 'mode', '')}")
        else:
            s = str(v)
            print(f"  {k:20s} {t:10s} {s[:90]!r}")

    print("\n=== 场景与 aspect 分布(流式扫全部 1353 题)===")
    from collections import Counter

    scen = Counter()
    aspect = Counter()
    imgtype = Counter()
    n_gt = Counter()
    n_ret = Counter()
    n = 0
    for ex in ds:
        scen[ex["scenario"]] += 1
        aspect[ex["aspect"]] += 1
        imgtype[ex["image_type"]] += 1
        n_gt[len(ex["gt_images"])] += 1
        n_ret[len(ex["retrieved_images"])] += 1
        n += 1
    print(f"  共 {n} 题")
    print(f"\n  scenario ({len(scen)} 种):")
    for k, v in scen.most_common():
        print(f"    {k:38s} {v:5d}")
    print(f"\n  aspect ({len(aspect)} 种):")
    for k, v in aspect.most_common():
        print(f"    {k:38s} {v:5d}")
    print(f"\n  image_type ({len(imgtype)} 种):")
    for k, v in imgtype.most_common():
        print(f"    {k:38s} {v:5d}")
    print(f"\n  len(gt_images) 分布:")
    for k in sorted(n_gt):
        print(f"    {k:3d} 张 -> {n_gt[k]:5d} 题")
    print(f"\n  len(retrieved_images) 分布:")
    for k in sorted(n_ret):
        print(f"    {k:3d} 张 -> {n_ret[k]:5d} 题")

    outdir = ROOT / "outputs" / "dataset_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "mrag_bench_schema.json").write_text(json.dumps({
        "repo_id": REPO_ID, "revision": REVISION,
        "num_examples": n,
        "scenario": dict(scen), "aspect": dict(aspect), "image_type": dict(imgtype),
        "gt_images_count": {str(k): v for k, v in sorted(n_gt.items())},
        "retrieved_images_count": {str(k): v for k, v in sorted(n_ret.items())},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {outdir / 'mrag_bench_schema.json'}")
    return 0


def materialize(limit: int | None, out_name: str) -> int:
    """把题目与图片落盘,并建立 ID—文件—内容哈希 映射表。

    产出:
        <store>/datasets/mrag_bench/<rev>/materialized/<out_name>/
            images/q_<qid>.png           查询图
            images/gt_<qid>_<i>.png      GT 证据图
            images/ret_<qid>_<i>.png     官方 CLIP 候选图(按返回顺序)
            questions.jsonl              逐题元数据(不含图片二进制)
            evidence_index.csv           evidence_id, qid, role, rank, path, sha256, w, h
    """
    cfg.apply_env()
    from datasets import load_dataset
    from PIL import Image

    base = cfg.store_root() / "datasets" / "mrag_bench" / REVISION / "materialized" / out_name
    imgdir = base / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)
    rows: list[dict] = []
    index_rows: list[dict] = []
    qlines: list[dict] = []

    def save(img, name: str) -> tuple[str, str, int, int]:
        p = imgdir / name
        img.convert("RGB").save(p, format="PNG")
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        return str(p.relative_to(base)).replace("\\", "/"), h, img.width, img.height

    for i, ex in enumerate(ds):
        if limit is not None and i >= limit:
            break
        qid = ex["id"]
        rec = {k: ex[k] for k in
               ("id", "aspect", "scenario", "question", "A", "B", "C", "D",
                "answer_choice", "answer", "image_type", "source")}
        rec["question_image"] = save(ex["image"], f"q_{qid}.png")
        rec["gt_images"] = []
        for j, im in enumerate(ex["gt_images"]):
            path, sha, w, h = save(im, f"gt_{qid}_{j}.png")
            rec["gt_images"].append({"path": path, "sha256": sha, "w": w, "h": h})
            index_rows.append({"evidence_id": f"{qid}#gt{j}", "qid": qid, "role": "gt",
                               "rank": j, "path": path, "sha256": sha, "w": w, "h": h})
        rec["retrieved_images"] = []
        for j, im in enumerate(ex["retrieved_images"]):
            path, sha, w, h = save(im, f"ret_{qid}_{j}.png")
            # 官方未提供相似度分数 -> score 留空,须由我们重算
            rec["retrieved_images"].append({"path": path, "sha256": sha, "w": w, "h": h,
                                            "official_rank": j, "official_score": None})
            index_rows.append({"evidence_id": f"{qid}#ret{j}", "qid": qid, "role": "official_retrieved",
                               "rank": j, "path": path, "sha256": sha, "w": w, "h": h})
        qlines.append(rec)
        rows.append(rec)
        if (i + 1) % 5 == 0:
            print(f"  已处理 {i + 1} 题")

    (base / "questions.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in qlines), encoding="utf-8")
    with (base / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["evidence_id", "qid", "role", "rank",
                                           "path", "sha256", "w", "h"])
        w.writeheader()
        w.writerows(index_rows)

    print(f"\n✅ 已落盘 {len(rows)} 题")
    print(f"   图片目录 : {imgdir}")
    print(f"   题目清单 : {base / 'questions.jsonl'}")
    print(f"   证据索引 : {base / 'evidence_index.csv'}  ({len(index_rows)} 条)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--materialize", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 题")
    ap.add_argument("--out-name", default="smoke20")
    args = ap.parse_args()

    if args.inspect:
        return inspect()
    if args.materialize:
        if not parquet_dir().exists():
            download()
        return materialize(args.limit, args.out_name)
    download()
    return 0


if __name__ == "__main__":
    sys.exit(main())
