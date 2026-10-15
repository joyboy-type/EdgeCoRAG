"""近重复检查: 精确哈希相同只能证明"字节相同",不能证明"没有近重复图"。

**为什么需要**

S3 干扰集的硬约束是"不含正确证据"。若只用 sha256 判等,以下情况会漏过:
  * 同一张图被官方以不同质量/尺寸重新编码(字节不同,视觉相同);
  * 裁剪、轻微缩放、水印差分;
  * 同一场景的相邻帧。

这些图若出现在"纯干扰"集里,实际仍可能提供支持答案的信息。

**方法**

用**感知哈希 dHash**(64 位)度量视觉近重复,配合汉明距离阈值:

    dHash: 转灰度 -> 缩到 9x8 -> 逐行比较相邻像素 -> 64 位

阈值说明(经验值,需人工抽查确认):
    <= 2   极可能同图(重编码/微调)
    3..6   近重复,需人工看
    >= 10  基本不同

**本脚本不宣称**能判定"语义是否支撑答案"——那只证明视觉相似。
语义层面的判定必须在 `--semantic-sample` 抽出的样本上人工完成,
并记录无法确定的情况,不得默认通过。

用法:
    python scripts/near_duplicate_check.py --limit 200        # 全量配对统计
    python scripts/near_duplicate_check.py --limit 200 --pairs gt_vs_ret
    python scripts/near_duplicate_check.py --samples <目录>    # 检查样例包内部
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
OUT = cfg.ROOT / "outputs" / "dataset_probe" / "near_duplicate_report.json"

# 汉明距离分档
BANDS = [(0, "identical_bits"), (1, 2, "very_likely_same"), (3, 6, "near_duplicate"),
         (7, 9, "weak_similarity")]


def dhash(im, size: int = 8) -> int:
    """64 位 dHash。转灰度、缩到 (size+1) x size、逐行相邻比较。"""
    g = im.convert("L").resize((size + 1, size), 1)  # 1 = LANCZOS
    px = list(g.getdata())
    bits = 0
    i = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
            i += 1
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def band_of(d: int) -> str:
    if d == 0:
        return "identical_bits"
    if d <= 2:
        return "very_likely_same"
    if d <= 6:
        return "near_duplicate"
    if d <= 9:
        return "weak_similarity"
    return "distinct"


def check_dataset(limit: int | None, which: str) -> dict:
    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)
    bands = Counter()
    worst: list[dict] = []
    n_q = 0
    n_pairs = 0
    t0 = time.time()

    for ex in ds:
        if limit is not None and n_q >= limit:
            break
        n_q += 1
        qid = ex["id"]
        gts = list(ex["gt_images"])
        rets = list(ex["retrieved_images"])

        # 每个对象只算一次 dHash，键统一为 "gt<i>" / "ret<j>"
        hashes: dict[str, int] = {}
        for i, g in enumerate(gts):
            hashes[f"gt{i}"] = dhash(g)
        for j, r in enumerate(rets):
            hashes[f"ret{j}"] = dhash(r)

        if which == "gt_vs_ret":
            keys = [(f"gt{i}", f"ret{j}")
                    for i in range(len(gts)) for j in range(len(rets))]
        elif which == "gt_vs_gt":
            keys = [(f"gt{i}", f"gt{j}")
                    for i in range(len(gts)) for j in range(i + 1, len(gts))]
        else:
            keys = [(f"ret{i}", f"ret{j}")
                    for i in range(len(rets)) for j in range(i + 1, len(rets))]

        for ka, kb in keys:
            d = hamming(hashes[ka], hashes[kb])
            n_pairs += 1
            b = band_of(d)
            bands[b] += 1
            if d <= 6:
                worst.append({"qid": qid, "a": ka, "b": kb, "hamming": d, "band": b,
                              "scenario": ex["scenario"]})
        if n_q % 100 == 0:
            print(f"  已核 {n_q} 题, {n_pairs} 对 ({time.time() - t0:.0f}s)")

    return {
        "which": which, "questions": n_q, "pairs_compared": n_pairs,
        "bands": dict(bands),
        "high_similarity_examples": sorted(worst, key=lambda x: x["hamming"])[:40],
    }


def check_samples_dir(d: Path) -> dict:
    """检查样例包内部: 同一题内 GT/候选/查询图之间的近重复。"""
    from PIL import Image

    idx = d / "evidence_index.csv"
    rows = list(csv.DictReader(idx.open(encoding="utf-8-sig", newline="")))
    by_q: dict[str, list[dict]] = {}
    for r in rows:
        by_q.setdefault(r["qid"], []).append(r)

    findings = []
    for qid, items in sorted(by_q.items()):
        hs = []
        for r in items:
            p = d / r["path"]
            if not p.exists():
                continue
            hs.append((r["evidence_id"], r["role"], dhash(Image.open(p))))
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                dd = hamming(hs[i][2], hs[j][2])
                if dd <= 6:
                    findings.append({"qid": qid, "a": hs[i][0], "b": hs[j][0],
                                     "hamming": dd, "band": band_of(dd)})
    return {"dir": str(d), "questions": len(by_q), "findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pairs", default="gt_vs_ret",
                    choices=["gt_vs_ret", "gt_vs_gt", "ret_vs_ret"])
    ap.add_argument("--samples", type=Path, default=None,
                    help="改为检查样例包目录内部")
    args = ap.parse_args()

    if args.samples:
        res = check_samples_dir(args.samples)
        print(f"样例目录: {res['dir']}")
        print(f"题数: {res['questions']}, 近重复发现: {len(res['findings'])}")
        for f in res["findings"]:
            print(f"  {f['qid']}  {f['a']} <-> {f['b']}  hamming={f['hamming']} ({f['band']})")
        if not res["findings"]:
            print("  ✅ 样例包内部无 hamming<=6 的视觉近重复对")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"script": "scripts/near_duplicate_check.py",
                                   "mode": "samples_dir", **res},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> {OUT}")
        return 0

    res = check_dataset(args.limit, args.pairs)
    print(f"\n=== 近重复检查: {args.pairs} ===")
    print(f"  题数 {res['questions']}, 配对数 {res['pairs_compared']}")
    for k, v in sorted(res["bands"].items(), key=lambda x: -x[1]):
        print(f"    {k:18s} {v}")
    print(f"\n  hamming<=6 的样例(前 10):")
    for e in res["high_similarity_examples"][:10]:
        print(f"    {e['qid']:>5s} {e['scenario']:12s} {e['a']}~{e['b']}  "
              f"hamming={e['hamming']} ({e['band']})")
    if not res["high_similarity_examples"]:
        print("    (无)")

    payload = {
        "script": "scripts/near_duplicate_check.py",
        "method": "dHash 64-bit, PIL LANCZOS 缩放到 9x8 灰度",
        "thresholds": {"identical_bits": 0, "very_likely_same": "1-2",
                       "near_duplicate": "3-6", "weak_similarity": "7-9"},
        "limitations": [
            "只度量视觉近重复,不能判定语义是否支持答案",
            "dHash 对旋转、大幅裁剪、翻转不敏感(会漏检)",
            "阈值 1-6 需人工抽查确认,不得直接当结论",
            "无法确定的情况必须标记,不得默认视为干净",
        ],
        "dataset_repo": REPO_ID, "dataset_revision": REVISION,
        **res,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
