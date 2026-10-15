"""核验 MRAG-Bench 的三组图片语义,为分工与证据规则提供实证依据。

要回答的问题:
  Q1  `gt_images` 只有 1 张的 102 题,是否与 scenario=='Incomplete' 完全重合?
  Q2  官方 `retrieved_images` 的 top-5 里,是否混入了 GT 正确证据?
      -> 这决定官方 CLIP 候选能否当作"纯检索"基线,还是已经部分泄漏了答案。
  Q3  `image` / `gt_images` / `retrieved_images` 三者是否真的是不同集合?
  Q4  官方是否提供检索相似度分数?(预期: 不提供)

产出: outputs/dataset_probe/evidence_ontology.json
用法: python scripts/analyze_evidence_semantics.py [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"


def img_key(im) -> str:
    """对图片**原始字节**取指纹。

    不要用 `im.save(PNG)` 再哈希: 对约 1.5 万张图重编码 PNG 会慢到不可接受
    (实测全量扫描 >10 分钟未完成)。数据集里的图片对象带 `.filename` 或
    可直接取出原始 JPEG 字节,这里优先用它;取不到时退回 PNG 编码。
    """
    raw = None
    # datasets 的 Image 特征在流式模式下通常保留了原始字节
    for attr in ("_data", "data"):
        blob = getattr(im, attr, None)
        if isinstance(blob, (bytes, bytearray)):
            raw = bytes(blob)
            break
    if raw is None:
        fn = getattr(im, "filename", None)
        if fn and Path(fn).exists():
            raw = Path(fn).read_bytes()
    if raw is None:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=95)
        raw = buf.getvalue()
    return hashlib.sha256(raw).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    single_gt = 0
    incomplete = 0
    both = 0
    gt_single_not_incomplete = 0
    incomplete_not_gt_single = 0

    # per-scenario: 官方 retrieved 中命中 GT 的题数/图片数
    scen_total = Counter()
    scen_hit_q = Counter()       # 至少命中一张 GT 的题数
    scen_hit_imgs = Counter()    # 命中的图片总数
    scen_ret_total = Counter()
    # 命中位置分布
    hit_rank = Counter()
    # 三集合是否互异
    same_q_ret = 0
    gt_in_ret_any = 0
    score_field_present = False
    n = 0

    for ex in ds:
        if args.limit is not None and n >= args.limit:
            break
        n += 1
        scen = ex["scenario"]
        scenario = scen
        gts = ex["gt_images"]
        rets = ex["retrieved_images"]
        scen_total[scenario] += 1
        scen_ret_total[scenario] += len(rets)

        # Q1
        is_inc = (scen == "Incomplete")
        is_single = (len(gts) == 1)
        single_gt += int(is_single)
        incomplete += int(is_inc)
        both += int(is_single and is_inc)
        if is_single and not is_inc:
            gt_single_not_incomplete += 1
        if is_inc and not is_single:
            incomplete_not_gt_single += 1

        # Q2/Q3
        qk = img_key(ex["image"])
        gkeys = [img_key(g) for g in gts]
        rkeys = [img_key(r) for r in rets]
        if qk in rkeys:
            same_q_ret += 1
        hits = 0
        for i, rk in enumerate(rkeys):
            if rk in gkeys:
                hits += 1
                hit_rank[i] += 1
        if hits:
            gt_in_ret_any += 1
        scen_hit_q[scenario] += int(hits > 0)
        scen_hit_imgs[scenario] += hits

        # Q4: 检查是否存在任何分数类字段
        for k, v in ex.items():
            if "score" in k.lower() or "sim" in k.lower() or "rank" in k.lower():
                score_field_present = True

        if n % 200 == 0:
            print(f"  已核 {n} 题")

    print(f"\n{'=' * 74}\nQ1  gt_images 单张 vs Incomplete 场景\n{'=' * 74}")
    print(f"  扫描题数                 : {n}")
    print(f"  gt_images 只有 1 张      : {single_gt}")
    print(f"  scenario == 'Incomplete' : {incomplete}")
    print(f"  两者同时成立             : {both}")
    print(f"  单张但不 Incomplete      : {gt_single_not_incomplete}")
    print(f"  Incomplete 但非单张      : {incomplete_not_gt_single}")
    same = (single_gt == incomplete == both)
    print(f"  => 是否完全重合          : {'✅ 是' if same else '❌ 否'}")

    print(f"\n{'=' * 74}\nQ2  官方 retrieved_images 是否混入 GT 正确证据\n{'=' * 74}")
    print(f"  至少命中 1 张 GT 的题数  : {gt_in_ret_any} / {n} "
          f"({gt_in_ret_any / max(n, 1) * 100:.1f}%)")
    print(f"  query image 出现在 retrieved 中: {same_q_ret}")
    print(f"  命中位置(0-based rank)分布:")
    for k in sorted(hit_rank):
        print(f"    rank {k}: {hit_rank[k]}")
    print(f"\n  分场景命中率:")
    print(f"    {'scenario':16s} {'题数':>6s} {'命中题数':>8s} {'命中率':>8s} {'命中图/候选图':>14s}")
    for s in sorted(scen_total, key=lambda x: -scen_total[x]):
        tot = scen_total[s]
        hq = scen_hit_q[s]
        print(f"    {s:16s} {tot:6d} {hq:8d} {hq / tot * 100:7.1f}% "
              f"{scen_hit_imgs[s]:6d}/{scen_ret_total[s]:<6d}")

    print(f"\n{'=' * 74}\nQ4  官方是否提供检索相似度分数\n{'=' * 74}")
    print(f"  存在 score/sim/rank 类字段: {'是' if score_field_present else '❌ 否'}")

    out = {
        "repo_id": REPO_ID, "revision": REVISION, "scanned": n,
        "q1_gt_single_vs_incomplete": {
            "gt_single": single_gt, "incomplete": incomplete, "both": both,
            "gt_single_not_incomplete": gt_single_not_incomplete,
            "incomplete_not_gt_single": incomplete_not_gt_single,
            "fully_coincide": same,
        },
        "q2_official_retrieved_contains_gt": {
            "questions_with_any_gt_hit": gt_in_ret_any,
            "query_image_in_retrieved": same_q_ret,
            "hit_rank_distribution": {str(k): v for k, v in sorted(hit_rank.items())},
            "per_scenario": {
                s: {"questions": scen_total[s], "questions_with_hit": scen_hit_q[s],
                    "hit_images": scen_hit_imgs[s], "retrieved_images": scen_ret_total[s]}
                for s in scen_total
            },
        },
        "q4_score_field_present": score_field_present,
    }
    p = cfg.ROOT / "outputs" / "dataset_probe" / "evidence_ontology.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
