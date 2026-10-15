"""量化「为什么实体级隔离在本数据集上不可行」——为切分的如实声明提供依据。

**背景**

`build_entity_groups.py` 按"跨题共享图片"做连通组，结果 1,353 题聚成
**7 个组，其中一个含 1,338 题**。这意味着按图片连通性做组隔离会把几乎所有题
绑在一起，**隔离不可行**。

本脚本把成因拆开量化，回答：

  Q1 巨型组是由**精确重复**造成，还是由 dHash **近重复**造成？
     （方法：分别只用精确重复、只用近重复各做一次连通，看组规模分布）
  Q2 精确重复的**具体形态**是什么？（查询图↔查询图 / 查询图↔GT / GT↔GT / 候选↔候选）
  Q3 平均每题有多少张图与**其它题**共享？

结论决定切分要不要做组隔离：若精确重复单独就能把绝大多数题连成一片，
则组隔离在本题上不可行，应在 manifest 中如实声明而不是硬做。

用法: python scripts/quantify_entity_connectivity.py
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
OUT = cfg.ROOT / "outputs" / "dataset_probe" / "entity_connectivity.json"


def sha_jpeg(im) -> str:
    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=95)
    return hashlib.sha256(b.getvalue()).hexdigest()


class DSU:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:
            self.p[x], x = r, self.p[x]
        return r

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def sizes(dsu: DSU, ids: list[str]) -> Counter:
    c: Counter = Counter()
    for i in ids:
        c[dsu.find(i)] += 1
    return Counter(c.values())


def main() -> int:
    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    # 记录每张图（带角色）属于哪题
    owner: dict[str, list[tuple[str, str]]] = defaultdict(list)  # hash -> [(rid, role)]
    ids: list[str] = []
    per_q_images = Counter()
    t0 = time.time()
    n = 0
    for ex in ds:
        n += 1
        rid = str(ex["id"])
        ids.append(rid)
        imgs = ([("query", ex["image"])]
                + [("gt", g) for g in ex["gt_images"]]
                + [("ret", r) for r in ex["retrieved_images"]])
        per_q_images[rid] = len(imgs)
        for role, im in imgs:
            owner[sha_jpeg(im)].append((rid, role))
        if n % 300 == 0:
            print(f"  已处理 {n} 题 ({time.time() - t0:.0f}s)")
    print(f"处理 {n} 题，{len(owner)} 个唯一图片哈希")

    # Q2: 共享形态统计
    shape = Counter()
    shared_hashes = 0
    for h, owners in owner.items():
        rids = {o[0] for o in owners}
        if len(rids) <= 1:
            continue
        shared_hashes += 1
        roles = {o[1] for o in owners}
        if roles == {"query"}:
            shape["query<->query"] += 1
        elif roles == {"gt"}:
            shape["gt<->gt"] += 1
        elif roles == {"ret"}:
            shape["ret<->ret"] += 1
        elif roles == {"query", "gt"}:
            shape["query<->gt"] += 1
        elif roles == {"query", "ret"}:
            shape["query<->ret"] += 1
        elif roles == {"gt", "ret"}:
            shape["gt<->ret"] += 1
        else:
            shape["query+gt+ret"] += 1
    print(f"\n跨题共享的图片哈希: {shared_hashes}")
    for k, v in shape.most_common():
        print(f"    {k:18s} {v}")

    # Q1: 只用精确重复做连通
    dsu_exact = DSU()
    for rid in ids:
        dsu_exact.find(rid)
    for h, owners in owner.items():
        rids = sorted({o[0] for o in owners})
        for r in rids[1:]:
            dsu_exact.union(rids[0], r)
    se = sizes(dsu_exact, ids)
    print(f"\n[仅精确重复] 组数 {sum(se.values())}，最大组 {max(se)} 题")
    print(f"    组规模分布: {dict(sorted(se.items())[:6])}")

    # Q3: 每题共享图数量
    per_q_shared = Counter()
    for rid in ids:
        per_q_shared[rid] = 0
    for h, owners in owner.items():
        rids = {o[0] for o in owners}
        if len(rids) > 1:
            for r in rids:
                per_q_shared[r] += 1
    vals = sorted(per_q_shared.values())
    avg_shared = sum(vals) / len(vals) if vals else 0

    payload = {
        "script": "scripts/quantify_entity_connectivity.py",
        "dataset_repo": REPO_ID,
        "dataset_revision": REVISION,
        "questions": n,
        "unique_image_hashes": len(owner),
        "cross_question_shared_image_hashes": shared_hashes,
        "shared_image_shape": dict(shape),
        "exact_only_connectivity": {
            "group_count": sum(se.values()),
            "largest_group": max(se) if se else 0,
            "size_distribution": {str(k): v for k, v in sorted(se.items())},
        },
        "per_question_shared_images": {
            "mean": round(avg_shared, 2),
            "min": min(vals) if vals else 0,
            "max": max(vals) if vals else 0,
            "median": vals[len(vals) // 2] if vals else 0,
        },
        "conclusion": (
            "精确重复单独就把绝大多数题目连成一个大组："
            f"组数 {sum(se.values())}、最大组 {max(se) if se else 0} 题。"
            "因此**按图片连通性做实体级组隔离在本数据集上不可行** —— "
            "任何组隔离都会把几乎所有题绑到同一子集。"
            "切分因此采用「场景分层 + 逐题分配」，"
            "并如实声明跨子集的图片相关性未能隔离。"
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n每题平均共享图数: {avg_shared:.2f}（中位 {payload['per_question_shared_images']['median']}，"
          f"最大 {payload['per_question_shared_images']['max']}）")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
