"""构建「实体/近重复组」映射，供切分做组级隔离。

**要解决什么**

先前切分声称"同源整组分配"，但实际只是按 `scenario`/`image_type` **分层**逐题分配。
用户指出得对：**`scenario`、`image_type`、`source` 是粗粒度属性，不能证明两题
出自同一实体/文档**。真正需要隔离的是「可能共享同一实体或同一源文档的题」——
例如同一动物的不同视角、同一物体多段时序帧、同一文档的多页。

**方法**

没有官方实体/文档映射可用，因此用**图像内容**反推连通性：

  1. **精确重复**：对每题的全部图片（查询图 + GT + 候选）取字节哈希，
     哈希相同的题union 到同一组（跨题出现同一张图 → 强证据）。
  2. **近重复**：对每题**查询图**取 dHash，汉明距离 ≤ 阈值者 union
     （查询图高度相似 → 很可能同一实体）。
  3. 用并查集把所有题聚成连通组。

**为什么只对查询图做 dHash 近重复**

全量 GT+候选约 1.4 万张，两两比对是 O(n²) 不可行。查询图每题 1 张共 1,353 张，
两两比对可接受（约 91 万对，纯位运算），且**查询图相似是最强的同实体信号**。

**已知局限（必须在 manifest 中如实声明）**

  * 这是**代理分组**，不是官方实体标注；可能**漏并**（不同视角差异大时 dHash 不敏感）
    也可能**误并**（同场景不同实体恰好相似）。
  * dHash 对旋转、大幅裁剪、翻转不敏感 → 会**漏检**。
  * 因此结论是"**已按可检测到的重复做隔离**"，**不是**"已消除全部相关性"。

用法:
    python scripts/build_entity_groups.py                # 全量，写 entity_groups.json
    python scripts/build_entity_groups.py --limit 200    # 抽样试跑
"""

from __future__ import annotations

import argparse
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
OUT = cfg.ROOT / "splits" / "entity_groups.json"
DHASH_NEAR = 6      # 汉明距离 <= 该值视为查询图近重复


def sha_jpeg(im) -> str:
    """落盘字节口径(与交付一致): JPEG q95 重编码。"""
    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=95)
    return hashlib.sha256(b.getvalue()).hexdigest()


def dhash(im, size: int = 8) -> int:
    g = im.convert("L").resize((size + 1, size), 1)
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return bits


def ham(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class DSU:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--near", type=int, default=DHASH_NEAR)
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    dsu = DSU()
    qhash: dict[str, str] = {}         # raw_id -> 查询图字节哈希
    qdhash: dict[str, int] = {}        # raw_id -> 查询图 dHash
    img_owner: dict[str, list[str]] = defaultdict(list)  # 图片哈希 -> 拥有它的题
    n = 0
    t0 = time.time()

    for ex in ds:
        if args.limit is not None and n >= args.limit:
            break
        n += 1
        rid = str(ex["id"])
        dsu.find(rid)
        imgs = [ex["image"]] + list(ex["gt_images"]) + list(ex["retrieved_images"])
        for i, im in enumerate(imgs):
            h = sha_jpeg(im)
            img_owner[h].append(rid)
            if i == 0:
                qhash[rid] = h
        qdhash[rid] = dhash(ex["image"])
        if n % 200 == 0:
            print(f"  已处理 {n} 题 ({time.time() - t0:.0f}s)")

    print(f"\n处理 {n} 题，{len(img_owner)} 个唯一图片哈希")

    # 1) 精确重复 union：同一张图出现在多题
    shared_exact = 0
    for h, owners in img_owner.items():
        uniq = sorted(set(owners))
        if len(uniq) > 1:
            shared_exact += 1
            for o in uniq[1:]:
                dsu.union(uniq[0], o)
    print(f"  跨题共享的精确重复图片: {shared_exact} 个")

    # 2) 查询图近重复 union（O(k^2)，k = 题数）
    ids = sorted(qdhash.keys(), key=lambda x: int(x) if x.isdigit() else 0)
    near_pairs = 0
    hashes = [qdhash[i] for i in ids]
    for a in range(len(ids)):
        ha = hashes[a]
        for b in range(a + 1, len(ids)):
            if ham(ha, hashes[b]) <= args.near:
                dsu.union(ids[a], ids[b])
                near_pairs += 1
    print(f"  查询图近重复对(<= {args.near}): {near_pairs}")

    # 汇总组
    groups: dict[str, list[str]] = defaultdict(list)
    for rid in qdhash:
        groups[dsu.find(rid)].append(rid)
    sizes = Counter(len(v) for v in groups.values())

    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"\n连通组总数: {len(groups)}")
    print(f"  单题组: {sizes.get(1, 0)}")
    print(f"  多题组: {len(multi)}，覆盖 {sum(len(v) for v in multi.values())} 题")
    print(f"  组规模分布(前 8): " +
          ", ".join(f"{k}题×{v}组" for k, v in sorted(sizes.items())[:8]))

    payload = {
        "script": "scripts/build_entity_groups.py",
        "method": {
            "exact_repeat": "所有图片(查询图+GT+候选)取 JPEG q95 字节 sha256，跨题同哈希即 union",
            "near_duplicate": f"查询图 dHash(64bit) 汉明距离 <= {args.near} 即 union",
            "union_find": "传递闭包成连通组",
        },
        "limitations": [
            "这是**代理分组**，不是官方实体/文档标注",
            "dHash 对旋转、大幅裁剪、水平翻转不敏感 → 会漏并",
            "同场景不同实体可能因查询图相似而误并",
            "因此只可声明『已按可检测到的重复做隔离』，不可声明『已消除全部相关性』",
        ],
        "dataset_repo": REPO_ID,
        "dataset_revision": REVISION,
        "questions": n,
        "unique_image_hashes": len(img_owner),
        "cross_question_exact_duplicate_images": shared_exact,
        "near_duplicate_query_pairs": near_pairs,
        "near_threshold": args.near,
        "group_count": len(groups),
        "multi_question_groups": len(multi),
        "questions_in_multi_groups": sum(len(v) for v in multi.values()),
        "group_of": {rid: dsu.find(rid) for rid in qdhash},
        "groups": {k: sorted(v, key=lambda x: int(x) if x.isdigit() else 0)
                   for k, v in groups.items()},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
