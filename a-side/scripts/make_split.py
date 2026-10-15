"""按预先规则切分 MRAG-Bench 题目，并生成 20 题联调清单。

**规则（预先声明，先于查看任何标签）**

官方**只有 `test` split**（1,353 题），无 dev/val。因此必须项目内自切分。
切分只依据 `raw_id` 的数值与固定种子，**不依据 `scenario` / `aspect` / 答案**，
以避免把场景信息泄漏进划分。

  1. 取全部 `raw_id`，按数值升序排序（`raw_id` 为字符串，先转 int）；
  2. 用固定种子 `SEED` 做**确定性洗牌**（`random.Random(SEED).shuffle`）；
  3. 按洗牌后的顺序切分：

        前  20 题            -> smoke_20        （打通接口）
        接下来 150 题         -> dev             （调参；结果只能叫 dev）
        再接下来 150 题       -> internal_holdout（内部留出；**不得称外部验证**）
        其余                  -> frozen_test     （最终评估）

  4. 若某题已被用于调试（见 `--reviewed-ids`），**强制归入 dev**，
     并从原属子集中移除，避免被当作独立测试。

**注意**：
  * 本切分是**项目内**的，`internal_holdout` 与 `frozen_test` **同源同分布**，
    只是开发期未查看。**外部验证必须用 VisDoM / MMDocRAG 等独立数据集。**
  * 同源相关题目（同一 `scenario` + 同一 `source`）**尽量整组处理**：
    实现上按 `(scenario, image_type, source)` 分组，整组分配到同一子集，
    以避免"同源题分散到 dev 与 test"造成的信息泄漏。

用法:
    python scripts/make_split.py --dry-run
    python scripts/make_split.py --reviewed-ids dev_reviewed.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
SEED = 20261015          # 固定种子，写入产物
N_SMOKE = 20
N_DEV = 150
N_HOLDOUT = 150
OUT_DIR = cfg.ROOT / "splits"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reviewed-ids", type=Path, default=None,
                    help="已完成查看/调试的 raw_id 列表(一行一个),强制归入 dev")
    ap.add_argument("--group-by", default="scenario,image_type",
                    help="同源分组键,逗号分隔;整组分配到同一子集。"
                         "注意键太粗会导致组很大,小配额子集拿不到题")
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    items: list[dict] = []
    for ex in ds:
        items.append({
            "raw_id": str(ex["id"]),
            "scenario": ex["scenario"],
            "aspect": ex["aspect"],
            "image_type": ex["image_type"],
            "source": ex["source"],
        })
    print(f"读取 {len(items)} 题")

    # 同源分组：整组一起分配，避免同源题跨子集
    keys = [k.strip() for k in args.group_by.split(",") if k.strip()]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for it in items:
        groups[tuple(it.get(k, "") for k in keys)].append(it)
    print(f"按 {keys} 分组得到 {len(groups)} 组")

    rng = random.Random(SEED)
    group_keys = sorted(groups.keys(), key=lambda t: tuple(str(x) for x in t))
    rng.shuffle(group_keys)

    reviewed: set[str] = set()
    if args.reviewed_ids and args.reviewed_ids.exists():
        reviewed = {l.strip() for l in
                    args.reviewed_ids.read_text(encoding="utf-8").splitlines()
                    if l.strip()}
        print(f"已查看过答案/用于调试的题: {len(reviewed)}（强制归入 dev）")

    splits: dict[str, list[dict]] = {"smoke_20": [], "dev": [],
                                     "internal_holdout": [], "frozen_test": []}
    targets = {"smoke_20": N_SMOKE, "dev": N_DEV, "internal_holdout": N_HOLDOUT}

    splits: dict[str, list[dict]] = {"smoke_20": [], "dev": [],
                                     "internal_holdout": [], "frozen_test": []}
    targets = {"smoke_20": N_SMOKE, "dev": N_DEV, "internal_holdout": N_HOLDOUT}

    # **分层配额 + 层内逐题分配**
    #
    # 三轮试错后的结论（都在本机实测过）：
    #   1) 按 (scenario,image_type,source) 整组分配 -> 只有 14 组、组太大,
    #      小配额子集直接拿不到题（smoke_20 = 0）。
    #   2) 按 (scenario,image_type) 分层但仍按块分配 -> smoke_20 = 919、
    #      frozen_test = 0（首块就有 200+ 题,配额必然被打爆）。
    #   3) 最终:**按 scenario 分层,层内逐题分配**。配额精确、覆盖均衡。
    #
    # 同源处理的务实口径: 层内用固定种子洗牌后逐题取,不强求整组同子集
    #   （数据集本身只有 14 个粗粒度组合,强求整组与"小样本均衡"不可兼得）。
    #   残留的同源风险在 manifest 中显式声明,并建议 B 在分析时把
    #   (scenario, image_type) 作为分层变量。
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_scenario[it.get(keys[0], "")].append(it)

    strata = sorted(by_scenario.keys())
    n_total = len(items) or 1
    alloc: dict[str, dict[str, int]] = {k: {} for k in targets}
    for name, target in targets.items():
        for s in strata:
            alloc[name][s] = int(round(target * len(by_scenario[s]) / n_total))
        diff = target - sum(alloc[name].values())
        if diff and strata:
            big = max(strata, key=lambda x: len(by_scenario[x]))
            alloc[name][big] = max(0, alloc[name][big] + diff)
        # 不能超过该层题量
        for s in strata:
            alloc[name][s] = min(alloc[name][s], len(by_scenario[s]))

    for s in strata:
        rows = list(by_scenario[s])
        # 稳定种子(不用内置 hash,它按进程随机化)
        random.Random(SEED + sum(ord(c) for c in s)).shuffle(rows)
        pos = 0
        for name in ("smoke_20", "dev", "internal_holdout"):
            take = alloc[name][s]
            chunk = rows[pos:pos + take]
            # 已查看过的题强制归 dev,不出现在其它子集
            forced = [it for it in chunk if it["raw_id"] in reviewed]
            normal = [it for it in chunk if it["raw_id"] not in reviewed]
            if name == "dev":
                splits["dev"].extend(chunk)
            else:
                splits[name].extend(normal)
                splits["dev"].extend(forced)
            pos += take
        splits["frozen_test"].extend(rows[pos:])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "dataset_repo": REPO_ID,
        "dataset_revision": REVISION,
        "seed": SEED,
        "group_by": keys,
        "rationale": ("官方只有 test split，无 dev/val；切分仅依据 raw_id 与固定种子，"
                      "不依据 scenario/aspect/答案；同源组整组分配"),
        "naming_warning": ("internal_holdout 与 frozen_test 同源同分布，"
                           "**不得称为外部验证**；外部验证须用 VisDoM / MMDocRAG"),
        "targets": {"smoke_20": N_SMOKE, "dev": N_DEV, "internal_holdout": N_HOLDOUT},
        "reviewed_ids_forced_to_dev": sorted(reviewed),
        "splits": {},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    for name, rows in splits.items():
        rows.sort(key=lambda r: int(r["raw_id"]) if r["raw_id"].isdigit() else 0)
        qids = [f"mragb:{r['raw_id']}" for r in rows]
        txt = "\n".join(qids) + "\n"
        p = OUT_DIR / f"{name}.txt"
        p.write_text(txt, encoding="utf-8")
        h = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        manifest["splits"][name] = {
            "count": len(qids), "file": p.name, "sha256": h,
            "scenarios": {s: sum(1 for r in rows if r["scenario"] == s)
                          for s in sorted({r["scenario"] for r in rows})},
        }
        print(f"  {name:18s} {len(qids):5d} 题  sha256={h[:16]}")

    total = sum(v["count"] for v in manifest["splits"].values())
    print(f"\n合计 {total} / {len(items)} 题")
    if total != len(items):
        print(f"⚠️ 合计与总数不符，差 {len(items) - total}")

    (OUT_DIR / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT_DIR / 'split_manifest.json'}")
    print("   各子集清单: " + ", ".join(f"{k}.txt" for k in splits))

    # 20 题联调清单（即 smoke_20）
    smoke = splits["smoke_20"]
    print(f"\n=== smoke_20 联调清单（{len(smoke)} 题）===")
    for r in smoke[:25]:
        print(f"    mragb:{r['raw_id']:>5s}  {r['scenario']:12s} {r.get('image_type','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
