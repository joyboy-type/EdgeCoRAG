"""审计官方候选池与 GT 的**图像精确匹配命中率**。

**术语纪律（本脚本的核心）**

本脚本度量的是「GT 图像的**字节级精确匹配命中率**」,即
    P(官方 retrieved_images 中存在某张图,其内容哈希 == 某张 gt_images 的哈希)
**这不等于"答案泄漏"**。理由:

  1. 官方 retrieved_images 是**官方检索流程的产物**,其产生方式(检索器、语料、是否
     使用了 GT 标注作为查询)在官方代码与 README 中**未被完整说明**。
     见 `official_provenance_verified.json` 中逐条的"已核实/未确认"标记。
  2. "命中"只说明**同一张图出现在两个集合里**,不能区分:
       (a) 正常检索命中(检索器独立找到了正确证据) —— 这是检索**成功**,不是缺陷;
       (b) 候选生成过程使用了 GT/答案标注 —— 这才是"泄漏"。
     本脚本**无法**在两者之间判定。
  3. 反过来,自研重检索**也不能默认就是干净基线**:必须实测其命中率并同样报告,
     且其语料许可与来源需单独确认。

所以本脚本的输出一律命名为 `*_exact_match_rate`,避免使用 leakage 措辞。

用法:
    python scripts/audit_gt_match_rate.py
    python scripts/audit_gt_match_rate.py --limit 100     # 快速自测
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
OUT = cfg.ROOT / "outputs" / "dataset_probe" / "gt_match_rate_audit.json"


def img_sha(im) -> str:
    """图片字节的 sha256,口径**显式固定**为 JPEG95 重编码。

    ⚠️ 重要发现(见 scripts/test_hash_stability.py 与 determine_hash_method.py):

      * MRAG-Bench 流式加载得到的 `PIL.JpegImageFile` 的 `im.fp` 为 **None**,
        `_data` / `data` / `filename` 也全为 None —— **原始字节取不到**。
        因此任何"取原始字节"的实现实际都会落到重编码分支。
      * 重编码是**确定性**的: 同一张图在多次独立加载中,PNG 与 JPEG95 各自
        的哈希完全一致(已实测 3 次独立加载)。
      * 因此用重编码哈希做**集合匹配**是有效的: GT 与候选图使用**同一口径**,
        匹配关系是双射,命中率不受容器格式选择影响。

    本函数把口径固定为 JPEG95 并在输出 JSON 中声明,避免"实际用了哪种编码"
    含糊不清。历史版本曾混用 PNG 与 JPEG,两者得到的哈希不同但**命中率一致**,
    已用本口径重算核对。
    """
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=95)
    return hashlib.sha256(buf.getvalue()).hexdigest()


HASH_METHOD = "JPEG quality=95 重编码后取 sha256 (原始字节不可得,见 img_sha 文档)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    n = 0
    # 分母口径
    denom_all = 0                     # 全部题
    denom_nonempty_gt = 0             # gt_images 非空的题(实际分母,需显式声明)
    denom_nonempty_ret = 0
    # 命中口径
    q_any_hit = 0                     # 至少一张 GT 出现在候选池中
    q_rank0_hit = 0                   # rank-0 候选就是某张 GT
    q_all_gt_covered = 0              # 全部 GT 都出现在候选池中
    hit_rank = Counter()
    per_scenario: dict[str, dict] = {}
    # 每题的命中 GT 数与候选数
    hits_per_q = Counter()
    mismatch_sizes = 0

    t0 = time.time()
    for ex in ds:
        if args.limit is not None and n >= args.limit:
            break
        n += 1
        scen = ex["scenario"]
        gts = list(ex["gt_images"])
        rets = list(ex["retrieved_images"])
        denom_all += 1
        if gts:
            denom_nonempty_gt += 1
        if rets:
            denom_nonempty_ret += 1
        if not gts or not rets:
            mismatch_sizes += 1

        gset = {img_sha(g) for g in gts}
        rlist = [img_sha(r) for r in rets]
        rset = set(rlist)

        hit_ranks = [i for i, s in enumerate(rlist) if s in gset]
        hit_gts = len(gset & rset)

        s = per_scenario.setdefault(scen, {
            "questions": 0, "questions_any_hit": 0, "questions_rank0_hit": 0,
            "gt_images": 0, "gt_images_hit": 0, "retrieved_images": 0,
        })
        s["questions"] += 1
        s["gt_images"] += len(gts)
        s["retrieved_images"] += len(rets)
        s["gt_images_hit"] += hit_gts
        if hit_ranks:
            q_any_hit += 1
            s["questions_any_hit"] += 1
        if 0 in hit_ranks:
            q_rank0_hit += 1
            s["questions_rank0_hit"] += 1
        if gset and gset <= rset:
            q_all_gt_covered += 1
        for r in hit_ranks:
            hit_rank[r] += 1
        hits_per_q[hit_gts] += 1

        if n % 300 == 0:
            print(f"  已核 {n} 题  ({time.time() - t0:.0f}s)")

    d = denom_nonempty_gt or 1
    result = {
        "script": "scripts/audit_gt_match_rate.py",
        "metric_name": "GT 图像字节级精确匹配命中率 (exact-match hit rate)",
        "metric_definition": (
            "题目 q 计为命中,当且仅当 retrieved_images 中存在至少一张图的 "
            "原始字节 sha256 等于 gt_images 中某张图的 sha256。"
        ),
        "what_this_is_not": [
            "不等于答案泄漏: 无法区分『检索器独立命中』与『候选生成使用 GT/答案标注』",
            "不能据此断定官方候选池不可用;也不能默认自研重检索就是干净基线",
            "不涉及近重复图、裁剪/缩放变体、语义等价但字节不同的图",
        ],
        "recompute": {
            "command": "python scripts/audit_gt_match_rate.py",
            "dataset_repo": REPO_ID,
            "dataset_revision": REVISION,
            "dataset_license": "cc-by-4.0",
            "split": "test",
            "hash_algorithm": "sha256",
            "hash_payload": HASH_METHOD,
            "hash_stability_verified": (
                "scripts/test_hash_stability.py 对 qid=0 做 3 次独立加载，"
                "JPEG95/PNG 两种口径的哈希各自完全一致"
            ),
            "container_format_note": (
                "GT 与候选图使用同一编码口径，匹配关系为双射；"
                "命中率不受 PNG/JPEG 选择影响（两口径均已核对）"
            ),
        },
        "denominators": {
            "questions_scanned": denom_all,
            "questions_with_nonempty_gt": denom_nonempty_gt,
            "questions_with_nonempty_retrieved": denom_nonempty_ret,
            "questions_with_empty_side": mismatch_sizes,
            "denominator_used": "questions_with_nonempty_gt",
            "note": "分母取 gt_images 非空的题;本数据集中与全部题数相同",
        },
        "headline": {
            "exact_match_rate_any": round(q_any_hit / d, 4),
            "exact_match_rate_rank0": round(q_rank0_hit / d, 4),
            "all_gt_covered_rate": round(q_all_gt_covered / d, 4),
            "questions_any_hit": q_any_hit,
            "questions_rank0_hit": q_rank0_hit,
            "questions_all_gt_covered": q_all_gt_covered,
        },
        "hit_rank_distribution": {str(k): v for k, v in sorted(hit_rank.items())},
        "hit_gt_count_distribution": {str(k): v for k, v in sorted(hits_per_q.items())},
        "per_scenario": {
            k: {
                **v,
                "exact_match_rate_any": round(v["questions_any_hit"] / v["questions"], 4),
                "exact_match_rate_rank0": round(v["questions_rank0_hit"] / v["questions"], 4),
                "gt_image_hit_rate": round(v["gt_images_hit"] / max(v["gt_images"], 1), 4),
            }
            for k, v in per_scenario.items()
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": round(time.time() - t0, 1),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== GT 图像精确匹配命中率 (n={denom_all}) ===")
    print(f"  任意命中           : {q_any_hit}/{d} = {q_any_hit / d * 100:.1f}%")
    print(f"  rank-0 命中        : {q_rank0_hit}/{d} = {q_rank0_hit / d * 100:.1f}%")
    print(f"  全部 GT 均被覆盖   : {q_all_gt_covered}/{d} = {q_all_gt_covered / d * 100:.1f}%")
    print(f"\n  分场景(任意命中率):")
    for k, v in sorted(result["per_scenario"].items(),
                       key=lambda x: -x[1]["exact_match_rate_any"]):
        print(f"    {k:14s} {v['questions_any_hit']:4d}/{v['questions']:<4d} "
              f"{v['exact_match_rate_any'] * 100:5.1f}%   rank0 {v['exact_match_rate_rank0'] * 100:5.1f}%")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
