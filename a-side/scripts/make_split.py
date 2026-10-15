"""按预先规则切分 MRAG-Bench 题目（v2 —— 修正三处已确认缺陷）。

## 本版修正的缺陷（v1 的问题，已在实测中复现）

| # | v1 的问题 | v2 的处理 |
|---|---|---|
| 1 | 已调试题只在 smoke/dev/internal_holdout 分配期间被过滤；最后 `rows[pos:]` **直接进 frozen_test**，导致已调试题**漏进冻结集**（实测 `mragb:3/4/43` 泄漏，而题数相加仍等于 1353，纯对数查不出） | 已调试题在**任何**分配之前先单独摘出，只允许进 `smoke_20`/`dev`；不参与后续任何切片 |
| 2 | 文档与 manifest 声称"同源组整组分配"，代码实际是**按场景分层逐题分配**（名实不符） | 不再用自由文本描述规则；manifest 写入**机器可校验的 `assignment_rule` 字段**，并由 `verify_split.py` 断言 |
| 3 | `--dry-run` 仍写文件 | dry-run 只计算、只打印与校验，**不写任何文件** |

## 规则

  1. 已调试题（`--reviewed-ids`，默认 `splits/reviewed_ids.txt`，**支持 `#` 注释**）
     优先级最高，只进 `dev`（可配置）。
  2. **组级隔离**：以 `splits/entity_groups.json`（由
     `build_entity_groups.py` 从图片重复反推）为单位整体分配，
     避免同实体/同源文档的题跨子集。无该文件时退化为逐题分配，
     并**如实声明** `entity_isolation.mode`。
  3. **场景分层**只作为**均衡手段**（保证 9 个场景在各子集都有覆盖），
     **不是**同源分组依据——`scenario`/`image_type`/`source` 不能证明同实体。
  4. `raw_id` **始终保持字符串原样**，不做整数化。
  5. 分配顺序 `smoke_20` → `dev` → `internal_holdout` → `frozen_test`；
     前三个有配额（20/150/150），放不下的整组进 `frozen_test`。
  6. 实际数量与目标不符时**报告实际值与原因**，不拆组、不丢题凑数。

用法:
    python scripts/make_split.py --dry-run          # 只检查，不写文件
    python scripts/make_split.py                    # 生成 splits/
    python scripts/make_split.py --version v2       # 指定版本号（写入 manifest）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
SEED = 20261015
N_SMOKE, N_DEV, N_HOLDOUT = 20, 150, 150
OUT_DIR = cfg.ROOT / "splits"
DEFAULT_REVIEWED = OUT_DIR / "reviewed_ids.txt"
ENTITY_FILE = OUT_DIR / "entity_groups.json"

ASSIGNMENT_RULE = "scenario_stratified_group_atomic_v2"


def read_id_list(p: Path) -> list[str]:
    """读 ID 清单，**跳过空行与 `#` 注释**（v1 缺这个，把注释当成了 ID）。"""
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def load_entity_groups(reviewed: set[str]) -> tuple[dict[str, str], dict]:
    """返回 (raw_id -> group_key, 元信息)。

    没有 entity_groups.json 时退化为每题自成一组的"逐题"模式，
    并在元信息里如实标注 —— 不假装做了组隔离。
    """
    if ENTITY_FILE.exists():
        d = json.loads(ENTITY_FILE.read_text(encoding="utf-8"))
        gof = d.get("group_of") or {}
        if gof:
            return gof, {
                "mode": "entity_groups_atomic",
                "source": ENTITY_FILE.name,
                "method": d.get("method"),
                "limitations": d.get("limitations", []),
                "group_count": d.get("group_count"),
                "multi_question_groups": d.get("multi_question_groups"),
                "questions_in_multi_groups": d.get("questions_in_multi_groups"),
                "cross_question_exact_duplicate_images":
                    d.get("cross_question_exact_duplicate_images"),
                "near_duplicate_query_pairs": d.get("near_duplicate_query_pairs"),
                "caveat": ("已按**可检测到的**图片重复/近重复做隔离；"
                           "这是代理分组，非官方实体标注，**不能声称已消除全部相关性**"),
            }
    return {}, {
        "mode": "per_question_fallback",
        "source": None,
        "caveat": ("未提供 entity_groups.json，退化为逐题分配；"
                   "**同实体/同源文档的相关性未做隔离**。"
                   "运行 build_entity_groups.py 可生成实体分组。"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="只计算与校验，**不写任何文件**")
    ap.add_argument("--reviewed-ids", type=Path, default=DEFAULT_REVIEWED)
    ap.add_argument("--reviewed-target", default="dev",
                    choices=["dev", "smoke_20"],
                    help="已调试题放入哪个子集（默认 dev；smoke_20 也可接受，"
                         "但会占用冒烟名额）")
    ap.add_argument("--version", default="v2",
                    help="切分版本号，写入 manifest 与文件名前缀（用于保留旧版本）")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--no-entity-groups", action="store_true",
                    help="忽略 entity_groups.json，强制逐题分配")
    ap.add_argument("--max-group-fraction", type=float, default=0.25,
                    help=("单个实体组的规模上限（占总题数比例）。超过则视为"
                          "『巨型连通组』，禁用组原子分配并退化为逐题，"
                          "同时在 manifest 中记录原因。"
                          "实测本数据集仅精确重复就把 1338/1353 题连成一组，"
                          "故默认会触发退化。"))
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)
    items: list[dict] = []
    for ex in ds:
        items.append({
            "raw_id": str(ex["id"]),          # 保持字符串，绝不 int()
            "scenario": ex["scenario"],
            "aspect": ex["aspect"],
            "image_type": ex["image_type"],
            "source": ex["source"],
        })
    print(f"读取 {len(items)} 题")

    reviewed: set[str] = set()
    if args.reviewed_ids and args.reviewed_ids.exists():
        reviewed = set(read_id_list(args.reviewed_ids))
    print(f"已调试题: {len(reviewed)} 题（来自 {args.reviewed_ids.name}）")

    gof, ent_meta = ({}, {"mode": "disabled_by_flag", "source": None,
                          "caveat": "显式禁用实体分组"}) if args.no_entity_groups \
        else load_entity_groups(reviewed)
    print(f"实体分组模式: {ent_meta['mode']}")

    # ---------------- 巨型连通组检测 ----------------
    # 实测: 本数据集仅精确重复(跨题共享 gt/ret 图片)就把 1338/1353 题连成一组。
    # 若硬做组原子分配，会出现 smoke_20=8、holdout=0 这种荒谬结果。
    # 因此在分配前先探测: 最大组超过阈值 -> 禁用组隔离，退化为逐题，
    # 并**如实记录原因**（这不是"已消除相关性"，而是"无法隔离"）。
    group_sizes: Counter = Counter()
    for it in items:
        rid = it["raw_id"]
        if rid in reviewed:
            continue
        group_sizes[gof.get(rid, rid)] += 1
    max_g = max(group_sizes.values()) if group_sizes else 0
    threshold = int(len(items) * args.max_group_fraction)
    if gof and max_g > threshold:
        print(f"⚠️ 检测到巨型连通组: 最大 {max_g} 题 > 阈值 {threshold}"
              f"（{args.max_group_fraction:.0%}）")
        print("   -> 组原子分配不可行，退化为逐题分配（原因记入 manifest）")
        ent_meta = {
            **{k: v for k, v in ent_meta.items() if k != "mode"},
            "mode": "per_question_fallback_giant_component",
            "giant_component_detected": True,
            "largest_group_size": max_g,
            "threshold": threshold,
            "max_group_fraction": args.max_group_fraction,
            "fallback_reason": (
                "数据集上按图片共享关系做连通后，最大组达 "
                f"{max_g}/{len(items)} 题；组原子分配会把几乎所有题绑到同一子集"
                "（实测会得到 smoke_20=8、internal_holdout=0）。"
                "因此**放弃组隔离，改为逐题分配**，"
                "并如实声明跨子集的图片相关性**未能隔离**。"),
            "why_infeasible": (
                "本数据集存在大量跨题复用的图片：实测 2688 个图片哈希被多题共享"
                "（gt<->ret 1423、gt<->gt 1091、query<->query 162 等），"
                "仅精确重复就足以把 1338 题连成一组；每题平均与约 9 道其它题共享图片。"
                "见 a-side/data/entity_connectivity.json。"),
        }
        gof = {}

    print(f"实体分组模式: {ent_meta['mode']}")

    # ---------------- 构造「分配单元」 ----------------
    # 已调试题自己成组（必须能被单独放到 dev），其余按实体组聚
    by_gid: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        rid = it["raw_id"]
        gid = ("REVIEWED:" + rid) if rid in reviewed else ("G:" + gof.get(rid, rid))
        by_gid[gid].append(it)

    units: list[dict] = []
    for gid, rows in by_gid.items():
        units.append({
            "gid": gid,
            "rows": rows,
            "size": len(rows),
            "reviewed": any(r["raw_id"] in reviewed for r in rows),
            "stratum": rows[0]["scenario"],
        })
    n_multi = sum(1 for u in units if u["size"] > 1)
    print(f"分配单元: {len(units)} 个（多题单元 {n_multi} 个，"
          f"最大 {max((u['size'] for u in units), default=0)} 题）")

    # ---------------- 先摘出已调试题 ----------------
    # v1 的 bug 就在这里：已调试题在最后 rows[pos:] 时漏进 frozen_test。
    # v2 在**任何**分配之前就摘出，后续流程看不到它们。
    reviewed_units = [u for u in units if u["reviewed"]]
    normal_units = [u for u in units if not u["reviewed"]]
    n_rev_items = sum(u["size"] for u in reviewed_units)
    print(f"先摘出已调试题: {n_rev_items} 题（{len(reviewed_units)} 个单元）")

    splits: dict[str, list[dict]] = {k: [] for k in
                                     ("smoke_20", "dev", "internal_holdout", "frozen_test")}
    # 已调试题只进目标子集
    for u in reviewed_units:
        splits[args.reviewed_target].extend(u["rows"])
    print(f"  已调试题 -> {args.reviewed_target}")

    # ---------------- 分层 + 组原子分配 ----------------
    # 容量: 前三个子集有配额; frozen_test 无上限(吸收剩余)。
    # 目标配额先扣掉已调试题占用的份额。
    caps = {"smoke_20": N_SMOKE, "dev": N_DEV, "internal_holdout": N_HOLDOUT}
    caps[args.reviewed_target] = max(0, caps[args.reviewed_target] - n_rev_items)

    strata = sorted({u["stratum"] for u in normal_units})
    total_normal = sum(u["size"] for u in normal_units) or 1
    # 每个子集在每个场景层的配额（按该层规模比例）
    alloc: dict[str, dict[str, int]] = {k: {} for k in caps}
    for name, target in caps.items():
        for s in strata:
            layer = sum(u["size"] for u in normal_units if u["stratum"] == s)
            alloc[name][s] = int(round(target * layer / total_normal))
        # 修正舍入误差: 补给最大的层
        diff = target - sum(alloc[name].values())
        if diff:
            big = max(strata, key=lambda x: sum(u["size"] for u in normal_units
                                                if u["stratum"] == x))
            alloc[name][big] = max(0, alloc[name][big] + diff)

    skipped: list[dict] = []
    for s in strata:
        layer_units = [u for u in normal_units if u["stratum"] == s]
        # 稳定性: 用固定种子（不用内置 hash，它按进程随机化）
        random.Random(SEED + sum(ord(c) for c in s)).shuffle(layer_units)
        # 大单元优先，减少"大块放不下"的浪费
        layer_units.sort(key=lambda u: -u["size"])
        rem = {k: alloc[k][s] for k in caps}
        for u in layer_units:
            placed = False
            for name in ("smoke_20", "dev", "internal_holdout"):
                if u["size"] <= rem[name]:
                    splits[name].extend(u["rows"])
                    rem[name] -= u["size"]
                    placed = True
                    break
            if not placed:
                splits["frozen_test"].extend(u["rows"])
                skipped.append({"gid": u["gid"], "size": u["size"], "stratum": s,
                                "reason": "layer_quota_full_for_this_unit_size"})

    # ---------------- 汇总检查 ----------------
    counts = {k: len(v) for k, v in splits.items()}
    total = sum(counts.values())
    print(f"\n计数: " + "  ".join(f"{k}={counts[k]}" for k in counts))
    print(f"合计 {total} / {len(items)}")

    problems: list[str] = []
    if total != len(items):
        problems.append(f"总覆盖 {total} != {len(items)}")
    all_ids = [r["raw_id"] for v in splits.values() for r in v]
    if len(all_ids) != len(set(all_ids)):
        problems.append("存在跨子集重复的 raw_id")
    # 关键断言: 已调试题不得出现在 holdout / frozen
    for bad in ("internal_holdout", "frozen_test"):
        leak = reviewed & {r["raw_id"] for r in splits[bad]}
        if leak:
            problems.append(f"已调试题泄漏进 {bad}: {sorted(leak)[:5]}")
    if problems:
        print("\n❌ 自检未通过:")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("✅ 自检通过（互斥 / 覆盖完整 / 已调试题未泄漏）")

    # ---------------- dry-run: 到此为止，不写文件 ----------------
    if args.dry_run:
        print("\n=== --dry-run: 不写任何文件 ===")
        print(f"  plans to write: {args.out}/<split>.{args.version}.txt, "
              f"split_manifest.{args.version}.json")
        return 0

    # ---------------- 写文件 ----------------
    args.out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "split_version": args.version,
        "assignment_rule": ASSIGNMENT_RULE,
        "dataset_repo": REPO_ID,
        "dataset_revision": REVISION,
        "seed": SEED,
        "reviewed_ids_source": str(args.reviewed_ids.name),
        "reviewed_ids": sorted(reviewed, key=lambda x: int(x) if x.isdigit() else 0),
        "reviewed_target": args.reviewed_target,
        "reviewed_count": len(reviewed),
        "entity_isolation": ent_meta,
        "stratification": {
            "variable": "scenario",
            "role": "仅用于均衡覆盖；**不是**同源分组依据",
            "note": ("scenario / image_type / source 是粗粒度属性，"
                     "不能证明两题出自同一实体或同一源文档"),
        },
        "targets": {"smoke_20": N_SMOKE, "dev": N_DEV, "internal_holdout": N_HOLDOUT},
        "actual_counts": counts,
        "target_deviations": {
            k: {"target": caps[k], "actual": counts[k],
                "delta": counts[k] - caps[k]}
            for k in caps
        },
        "skipped_due_to_quota": len(skipped),
        "skipped_examples": skipped[:20],
        "naming_warning": ("internal_holdout 与 frozen_test 同源同分布，"
                           "**不得称为外部验证**；外部验证须用 VisDoM / MMDocRAG"),
        "label_exposure_note": (
            "A 侧曾在**全部 1353 题**上计算过与 GT 相关的**聚合统计**"
            "（audit_gt_match_rate.py 等）。这些统计**未用于挑题**，"
            "切分规则只依赖 raw_id 与固定种子；但作为已发生的标签接触，如实声明。"
            "逐题具名的接触见 reviewed_ids。"),
        "splits": {},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    for name, rows in splits.items():
        # 排序保持 raw_id 字符串语义（按数值排，但不改写 raw_id 本身）
        rows_sorted = sorted(rows, key=lambda r: int(r["raw_id"])
                             if r["raw_id"].isdigit() else 0)
        qids = [f"mragb:{r['raw_id']}" for r in rows_sorted]
        txt = "\n".join(qids) + "\n"
        fname = f"{name}.{args.version}.txt"
        (args.out / fname).write_text(txt, encoding="utf-8")
        h = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        manifest["splits"][name] = {
            "file": fname, "count": len(qids), "sha256": h,
            "scenarios": dict(sorted(Counter(r["scenario"] for r in rows_sorted).items())),
        }
        print(f"  {name:18s} {len(qids):5d} 题  sha256={h[:16]}  -> {fname}")

    # ⚠️ 可重现性: 不能用墙上时钟做 generated_at。
    #    实测踩过: 时间戳使 manifest 每次都变 -> 内容看似"有更新" ->
    #    重跑会造出一个与远程分叉的提交,推送被拒(non-fast-forward)。
    #    改为**由输入派生**的确定性 digest，重跑得到完全相同的字节。
    input_digest = hashlib.sha256()
    input_digest.update(ASSIGNMENT_RULE.encode("utf-8"))
    input_digest.update(str(SEED).encode("utf-8"))
    input_digest.update(str(args.version).encode("utf-8"))
    input_digest.update(args.reviewed_target.encode("utf-8"))
    for s in sorted(manifest["splits"]):
        input_digest.update(manifest["splits"][s]["sha256"].encode("utf-8"))
    for r in manifest["reviewed_ids"]:
        input_digest.update(r.encode("utf-8"))
    manifest["input_digest"] = input_digest.hexdigest()
    manifest["deterministic"] = True
    manifest["generated_at"] = None
    manifest["generated_at_note"] = (
        "故意不写墙上时钟：时间戳会让重跑产生不同字节，破坏可重现性并造成"
        "无意义的提交分叉。用 input_digest 标识本次生成。")

    mpath = args.out / f"split_manifest.{args.version}.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  input_digest = {manifest['input_digest'][:16]}")
    print(f"-> {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
