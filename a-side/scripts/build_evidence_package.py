"""按题单生成 S1 / S2 证据包（租卡前正式口径）。

## 本轮的实验口径（用户指定）

| 条件 | 证据 | 图片数 | 提示占位符 |
|---|---|---|---|
| **S0** | 无外部证据 | 0 | 1（仅查询图） |
| **S1** | **MRAG-Bench 随附的已发布候选**，按既有排名取 **top-3**，**Incomplete 也用 3 张** | 3 | **4** |
| **S2** | **真实 GT**，保留真实数量（常规 5、Incomplete 1），**不补齐也不截断成 top-3** | 5 / 1 | 6 / 2 |

⚠️ **S1 必须称为「已发布候选基线」**，不得称为我方独立重检索结果。
   本包 `pool_id = official_retrieved_top3`，`is_oracle = false`，
   `retriever_id = null`，并在 `provenance` 中写明来源。

⚠️ **占位符必须随图片数同步改**（官方模板写死 6/2）：
   `prompt_image_slots = 1 + 证据数`。已在每行显式记录，并由校验器断言。

## 与 S2 的一处口径不一致（**需确认，不擅自决定**）

S1 在 Incomplete 上取 3 张（占位符 4），而 S2 在 Incomplete 上只有 1 张
（占位符 2）。同一场景下 S1/S2 的**图片数量不同**，
因此 Incomplete 的 S1–S2 差距**不能纯归因于证据质量**。
详见 `a-side/plans/` 中的口径说明。

用法:
    python scripts/build_evidence_package.py --list splits/smoke_20.v2.txt \
        --name smoke_20_s1 --condition S1
    python scripts/build_evidence_package.py --list splits/frozen_test.v2.txt \
        --name frozen_test_s2 --condition S2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
LICENSE = "cc-by-4.0"
PKG_ROOT = cfg.ROOT / "packages"
ENCODE = {"format": "JPEG", "quality": 95,
          "note": ("原始字节不可得（im.fp/_data/data/filename 均为 None），"
                   "故落盘字节为 JPEG q95 重编码；哈希与落盘字节同源。")}

# 条件定义：证据来源 + 每场景图片数
CONDITIONS = {
    "S0": {"pool_id": None, "is_oracle": False,
           "desc": "无外部证据（仅查询图）"},
    "S1": {"pool_id": "official_retrieved_top3", "is_oracle": False,
           "desc": ("MRAG-Bench 随附的已发布候选，按既有排名取 top-3；"
                    "**已发布候选基线**，非我方独立重检索")},
    "S2": {"pool_id": "gt_evidence", "is_oracle": True,
           "desc": "真实 GT 证据，保留真实数量（常规 5、Incomplete 1）"},
    "S3": {"pool_id": "pure_distractor_d1", "is_oracle": False,
           "desc": "D1 纯干扰（同类不同实例），数量与 S1 一致"},
}


def enc(im) -> bytes:
    b = io.BytesIO()
    im.convert("RGB").save(b, format=ENCODE["format"], quality=ENCODE["quality"])
    return b.getvalue()


def read_qids(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s[6:] if s.startswith("mragb:") else s)
    return out


def select_s1(ex) -> list[tuple[int, object]]:
    """S1: 已发布候选按既有排名取 top-3（Incomplete 同样取 3 张）。"""
    return [(j, im) for j, im in enumerate(ex["retrieved_images"][:3])]


def select_s2(ex) -> list[tuple[int, object]]:
    """S2: 真实 GT，保留真实数量，不补齐不截断。"""
    return [(k, g) for k, g in enumerate(ex["gt_images"])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--condition", required=True, choices=list(CONDITIONS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--evidence-version", default=None)
    args = ap.parse_args()

    cond = CONDITIONS[args.condition]
    out = args.out or (PKG_ROOT / args.name)
    ev_ver = args.evidence_version or f"{args.name}_{args.condition}"
    want = read_qids(args.list)
    if args.limit:
        want = want[: args.limit]
    want_set = set(want)
    print(f"条件 {args.condition}: {cond['desc']}")
    print(f"题单 {args.list.name}  {len(want)} 题   ->  {out}")

    if out.exists():
        shutil.rmtree(out)
    imgroot = out / "images"
    imgroot.mkdir(parents=True, exist_ok=True)

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    rows: list[dict] = []
    index_rows: list[dict] = []
    issues: list[dict] = []
    t0 = time.time()

    def dump(im, stem: str, raw_id: str, qid: str, role: str, rank, **extra) -> dict:
        b = enc(im)
        sub = imgroot / raw_id
        sub.mkdir(parents=True, exist_ok=True)
        p = sub / f"{stem}.jpg"
        p.write_bytes(b)
        sha = hashlib.sha256(b).hexdigest()
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            issues.append({"qid": qid, "kind": "hash_mismatch",
                           "detail": f"{role}{rank}"})
        ref = {"evidence_id": f"{qid}#{role}{'' if rank is None else rank}",
               "role": role, "rank": rank,
               "path": str(p.relative_to(out)).replace("\\", "/"),
               "sha256": sha, "w": im.width, "h": im.height}
        ref.update(extra)
        index_rows.append({"evidence_id": ref["evidence_id"], "raw_id": raw_id,
                           "qid": qid, "role": role,
                           "rank": "" if rank is None else rank,
                           "path": ref["path"], "sha256": sha,
                           "w": im.width, "h": im.height})
        return ref

    found: set[str] = set()
    for ex in ds:
        rid = str(ex["id"])
        if rid not in want_set:
            continue
        found.add(rid)
        qid = f"mragb:{rid}"
        scenario = ex["scenario"]
        is_inc = scenario == "Incomplete"

        q_ref = dump(ex["image"], f"query_{rid}", rid, qid, "q", None)

        if args.condition == "S0":
            pairs, role = [], "none"
        elif args.condition == "S1":
            pairs, role = select_s1(ex), "official_retrieved"
        elif args.condition == "S2":
            pairs, role = select_s2(ex), "gt"
        else:
            raise SystemExit("S3 由 build_distractor_package.py 生成，请勿用本脚本")

        ev = [dump(im, f"{role}_{rid}_{k}", rid, qid, role, k,
                   retrieval_rank=(k if args.condition == "S1" else None),
                   retrieval_score=None,
                   used_in_prompt=True)
              for k, im in pairs] if pairs else []

        # 数量与占位符
        n_ev = len(ev)
        slots = 1 + n_ev
        if args.condition == "S2" and not is_inc:
            assert n_ev == 5, f"{qid}: S2 常规场景应为 5 张，实为 {n_ev}"
        if args.condition == "S2" and is_inc:
            assert n_ev == 1, f"{qid}: S2 Incomplete 应为 1 张，实为 {n_ev}"
        if args.condition == "S1":
            assert n_ev == 3, f"{qid}: S1 应为 3 张，实为 {n_ev}"

        # S1 的 GT 命中位点（仅分析）
        ret_shas = [e["sha256"] for e in ev]
        gt_hit = []
        if args.condition == "S1":
            gts = [hashlib.sha256(enc(g)).hexdigest() for g in ex["gt_images"]]
            gt_hit = [ret_shas.index(s) for s in gts if s in ret_shas]

        rows.append({
            "qid": qid, "raw_id": rid, "split": args.name,
            "scenario": scenario, "aspect": ex["aspect"],
            "question_image": q_ref,
            "evidence_order": ev,
            "num_evidence": n_ev,
            "pool_id": cond["pool_id"],
            "pool_gt_exact_match_rate": None,
            "is_oracle": cond["is_oracle"],
            "retriever_id": None,
            "retrieval_scores": [None] * n_ev,
            "retrieval_ranks": [e.get("retrieval_rank") for e in ev],
            "protocol_version": (f"proto_{args.condition.lower()}_top3_v1"
                                 if args.condition == "S1"
                                 else f"proto_{args.condition.lower()}_realk_v1"),
            "prompt_image_slots": slots,
            "scenario_rule_applied": (
                "published_top3_including_incomplete" if args.condition == "S1"
                else ("gt_real_count_incomplete_1" if args.condition == "S2"
                      else "no_evidence")),
            "available_evidence_untruncated": (
                {"note": ("S1 只取已发布候选的前 3 张；其余候选未使用，"
                          "仅登记数量以便核对。"),
                 "retrieved_count_available": len(ex["retrieved_images"]),
                 "used": min(3, len(ex["retrieved_images"]))}
                if args.condition == "S1" else None),
            "status": "ok", "notes": None,
            "task_payload": {"question": ex["question"],
                             "choices": {"A": ex["A"], "B": ex["B"],
                                         "C": ex["C"], "D": ex["D"]}},
            "scoring_only": {
                "gold_choice": ex["answer_choice"],
                "answer_text": ex["answer"],
                "gt_evidence_ids": [f"{qid}#gt{k}" for k in range(len(ex["gt_images"]))],
                "gt_evidence_refs": (ev if args.condition == "S2" else None),
                "gt_evidence_ids_all": [f"{qid}#gt{k}"
                                        for k in range(len(ex["gt_images"]))],
                "gt_on_official_pool_ranks": gt_hit},
            "provenance": {
                "dataset_repo": REPO_ID, "dataset_revision": REVISION,
                "dataset_license": LICENSE,
                "split_version": args.list.stem,
                "evidence_version": ev_ver,
                "run_batch_id": None,
                "generated_by": "scripts/build_evidence_package.py",
                "encoding": ENCODE,
                "path_root": f"{args.name}/",
                "condition": args.condition,
                "evidence_source": cond["desc"],
                "config_hash": None},
        })
        if len(found) % 20 == 0:
            print(f"  已生成 {len(found)}/{len(want)}  ({time.time() - t0:.0f}s)")
        if len(found) >= len(want):
            break

    missing = sorted(want_set - found)
    if missing:
        issues.append({"kind": "questions_not_found", "count": len(missing),
                       "qids": [f"mragb:{m}" for m in missing[:20]]})

    rows.sort(key=lambda r: int(r["raw_id"]) if r["raw_id"].isdigit() else 0)
    (out / "evidence_list.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    with (out / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["evidence_id", "raw_id", "qid", "role",
                                           "rank", "path", "sha256", "w", "h"])
        w.writeheader()
        w.writerows(index_rows)

    (out / "coverage.json").write_text(json.dumps({
        "condition": args.condition,
        "requested": len(want), "generated": len(rows),
        "missing": [f"mragb:{m}" for m in missing],
        "coverage_rate": round(len(rows) / max(len(want), 1), 4),
        "note": ("主准确率分母应使用**题单全量**（requested）；"
                 "成功子集指标另报并给覆盖率。失败题不得静默丢弃。"),
        "issues": issues,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    files = [f for f in imgroot.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    dg = hashlib.sha256()
    for r in rows:
        dg.update(r["qid"].encode())
        for e in [r["question_image"]] + r["evidence_order"]:
            dg.update(e["sha256"].encode())
    (out / "package_meta.json").write_text(json.dumps({
        "artifact_kind": "evidence_package",
        "package_version": ev_ver,
        "condition": args.condition,
        "condition_description": cond["desc"],
        "name": args.name,
        "split_file": args.list.name,
        "protocol_version": rows[0]["protocol_version"] if rows else None,
        "pool_id": cond["pool_id"],
        "is_oracle": cond["is_oracle"],
        "questions": len(rows),
        "image_files": len(files),
        "image_bytes": total,
        "encoding": ENCODE,
        "path_root": f"{args.name}/ (所有 path 相对包根目录；不绑定盘符)",
        "dataset": {"repo": REPO_ID, "revision": REVISION, "license": LICENSE},
        "content_digest": dg.hexdigest(),
        "deterministic": True,
        "generated_at": None,
        "generated_at_note": "故意不写墙上时钟，保证重跑字节一致。",
        "slot_rule": "prompt_image_slots = 1 (查询图) + 证据数",
        "not_claims": [
            "S1 是『已发布候选基线』，不是我方独立重检索结果",
            "不声称任何一路线天然干净",
            "S2 是 Oracle 上界，不是可部署方案",
        ],
        "known_mismatch": ({
            "issue": "S1 与 S2 在 Incomplete 上的图片数不同",
            "s1_incomplete_images": 3, "s2_incomplete_images": 1,
            "consequence": ("同一场景下 S1/S2 图片数不一致，"
                            "Incomplete 的 S1-S2 差距不能纯归因于证据质量"),
            "needs_confirmation": True,
        } if args.condition in ("S1", "S2") else None),
        "issues": issues,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {args.name}: {len(rows)} 题, {len(files)} 图, {total / 1024 ** 2:.1f} MiB")
    print(f"   coverage {len(rows) / max(len(want), 1):.1%}  缺失 {len(missing)}")
    print(f"   content_digest {dg.hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
