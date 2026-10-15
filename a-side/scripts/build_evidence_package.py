"""按题单生成完整联调证据包 —— B 可直接接收运行。

与 `make_b_handover_sample.py`（6 题接口样例）的区别：
  * **按题单文件**生成（默认新切分的 `smoke_20.v2.txt`），不再用"前 N 题"；
  * 每题给全：查询图、题干与四选项、S1 有序证据（含原始排名）、
    S2 实际 GT 附件、图片索引、哈希、尺寸、编码说明；
  * 严格遵守官方场景规则（Incomplete 只取首张，占位符 2，其余 5 张，占位符 6）。

**编码口径（固定，不重复转码）**

实测数据集图片取不到原始字节（`im.fp`/`_data`/`data`/`filename` 全为 None），
因此落盘字节一律为 **JPEG quality=95 重编码**，且**索引哈希与落盘字节同源**
（同一份 bytes 既写文件也算哈希）。该编码确定性已在多次独立加载中验证。

**路径约定（不绑定机器盘符）**

所有 `path` 均相对包根目录，形如 `images/<raw_id>/<role>_<raw_id>_<rank>.jpg`。
B 只需把包根目录放在任意位置即可定位全部文件。

用法:
    python scripts/build_evidence_package.py --list splits/smoke_20.v2.txt --name smoke_20
    python scripts/build_evidence_package.py --list splits/frozen_test.v2.txt --name frozen_test --limit 50
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
                   "故落盘字节为 JPEG q95 重编码；哈希与落盘字节同源。"
                   "确定性已由 test_hash_stability.py 多次独立加载验证。")}


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
        out.append(s[6:] if s.startswith("mragb:") else s)   # raw_id
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=Path, required=True, help="题单文件（qid 或 raw_id，一行一个）")
    ap.add_argument("--name", required=True, help="包名，如 smoke_20")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--evidence-version", default=None)
    args = ap.parse_args()

    out = args.out or (PKG_ROOT / args.name)
    ev_ver = args.evidence_version or f"{args.name}_official_retrieved"
    want = read_qids(args.list)
    if args.limit:
        want = want[: args.limit]
    want_set = set(want)
    print(f"题单: {args.list.name}  {len(want)} 题")
    print(f"输出: {out}")
    print(f"证据版本: {ev_ver}")

    if out.exists():
        shutil.rmtree(out)
    imgroot = out / "images"
    imgroot.mkdir(parents=True, exist_ok=True)

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    rows: list[dict] = []
    index_rows: list[dict] = []
    issues: list[str] = []
    t0 = time.time()

    def dump(im, stem: str, raw_id: str, qid: str, role: str, rank, **extra) -> dict:
        b = enc(im)
        sub = imgroot / raw_id
        sub.mkdir(parents=True, exist_ok=True)
        p = sub / f"{stem}.jpg"
        p.write_bytes(b)
        sha = hashlib.sha256(b).hexdigest()
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            issues.append(f"{qid}#{role}{rank}: 落盘回读哈希不一致")
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
    for i, ex in enumerate(ds):
        rid = str(ex["id"])
        if rid not in want_set:
            continue
        found.add(rid)
        qid = f"mragb:{rid}"
        scenario = ex["scenario"]
        is_incomplete = scenario == "Incomplete"
        n_use = 1 if is_incomplete else len(ex["retrieved_images"])

        q_ref = dump(ex["image"], f"query_{rid}", rid, qid, "q", None)

        ev_all = []
        for j, im in enumerate(ex["retrieved_images"]):
            ev_all.append(dump(im, f"official_retrieved_{rid}_{j}", rid, qid,
                               "official_retrieved", j,
                               retrieval_rank=j, retrieval_score=None,
                               used_in_prompt=(j < n_use)))
        ev_use = [e for e in ev_all if e["used_in_prompt"]]

        gt_all = [dump(g, f"gt_{rid}_{k}", rid, qid, "gt", k)
                  for k, g in enumerate(ex["gt_images"])]
        gt_use = gt_all[:1] if is_incomplete else gt_all

        ret_shas = [e["sha256"] for e in ev_use]
        hit_ranks = [ret_shas.index(g["sha256"]) for g in gt_all
                     if g["sha256"] in ret_shas]

        rows.append({
            "qid": qid, "raw_id": rid,
            "split": args.name,
            "scenario": scenario, "aspect": ex["aspect"],
            "question_image": q_ref,
            "evidence_order": ev_use,
            "num_evidence": len(ev_use),
            "pool_id": "official_retrieved_top5",
            "pool_gt_exact_match_rate": None,
            "is_oracle": False,
            "retriever_id": None,
            "retrieval_scores": [None] * len(ev_use),
            "retrieval_ranks": [e["retrieval_rank"] for e in ev_use],
            "protocol_version": "proto_official_v1",
            "prompt_image_slots": 2 if is_incomplete else 6,
            "scenario_rule_applied": ("official_incomplete_truncate_to_first"
                                      if is_incomplete
                                      else "official_use_all_candidates"),
            "available_evidence_untruncated": (None if not is_incomplete else {
                "note": "Incomplete 按官方规则只取首张；其余候选取用于分析，"
                        "used_in_prompt=false，不得送入提示。",
                "retrieved_count": len(ex["retrieved_images"]),
                "gt_count": len(ex["gt_images"]),
                "retrieved_refs": [e for e in ev_all if not e["used_in_prompt"]],
                "gt_refs": gt_all[1:]}),
            "status": "ok", "notes": None,
            "task_payload": {"question": ex["question"],
                             "choices": {"A": ex["A"], "B": ex["B"],
                                         "C": ex["C"], "D": ex["D"]}},
            "scoring_only": {
                "gold_choice": ex["answer_choice"],
                "answer_text": ex["answer"],
                "gt_evidence_ids": [g["evidence_id"] for g in gt_use],
                "gt_evidence_refs": gt_use,
                "gt_evidence_ids_all": [g["evidence_id"] for g in gt_all],
                "gt_on_official_pool_ranks": hit_ranks},
            "provenance": {
                "dataset_repo": REPO_ID, "dataset_revision": REVISION,
                "dataset_license": LICENSE,
                "split_version": args.list.stem,
                "evidence_version": ev_ver,
                "run_batch_id": None,
                "generated_by": "scripts/build_evidence_package.py",
                "encoding": ENCODE,
                "path_root": f"{args.name}/",
                "config_hash": None},
        })
        if len(found) % 5 == 0:
            print(f"  已生成 {len(found)}/{len(want)}  ({time.time() - t0:.0f}s)")
        if len(found) >= len(want):
            break

    missing = want_set - found
    if missing:
        issues.append(f"题单中有 {len(missing)} 题未在数据集中找到: {sorted(missing)[:10]}")

    rows.sort(key=lambda r: int(r["raw_id"]) if r["raw_id"].isdigit() else 0)
    (out / "evidence_list.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    with (out / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["evidence_id", "raw_id", "qid", "role",
                                           "rank", "path", "sha256", "w", "h"])
        w.writeheader()
        w.writerows(index_rows)

    # 覆盖率与失败记录
    coverage = {
        "requested": len(want), "generated": len(rows),
        "missing": sorted(missing),
        "coverage_rate": round(len(rows) / max(len(want), 1), 4),
        "note": ("主准确率分母应使用**题单全量**（requested）；"
                 "成功子集指标另报，并给出 coverage_rate"),
    }
    (out / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    files = [f for f in imgroot.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    # 确定性: 不用墙上时钟（时间戳会让重跑产生不同字节，破坏可复现性）
    dg = hashlib.sha256()
    dg.update(args.name.encode("utf-8"))
    dg.update(args.list.name.encode("utf-8"))
    dg.update(ev_ver.encode("utf-8"))
    dg.update(str(len(rows)).encode("utf-8"))
    for r in rows:
        dg.update(r["qid"].encode("utf-8"))
        for e in [r["question_image"]] + r["evidence_order"]:
            dg.update(e["sha256"].encode("utf-8"))
    pkg = {
        "artifact_kind": "evidence_package",
        "name": args.name,
        "split_file": args.list.name,
        "evidence_version": ev_ver,
        "protocol_version": "proto_official_v1",
        "pool_id": "official_retrieved_top5",
        "questions": len(rows),
        "image_files": len(files),
        "image_bytes": total,
        "encoding": ENCODE,
        "path_root": f"{args.name}/ (所有 path 相对包根目录；不绑定盘符)",
        "dataset": {"repo": REPO_ID, "revision": REVISION, "license": LICENSE},
        "content_digest": dg.hexdigest(),
        "deterministic": True,
        "generated_at": None,
        "generated_at_note": "故意不写墙上时钟，以保证重跑字节一致。用 content_digest 标识。",
        "not_claims": ["不声称任何一路线天然干净",
                       "官方候选池的 GT 精确匹配命中率是池级统计，"
                       "见 a-side/data/gt_match_rate_audit.json"],
        "issues": issues,
    }
    (out / "package_meta.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {args.name}: {len(rows)} 题, {len(files)} 张图, {total / 1024 ** 2:.1f} MiB")
    print(f"   coverage: {coverage['coverage_rate']:.1%}  缺失 {len(missing)}")
    if issues:
        print("   ⚠️ issues:")
        for x in issues[:5]:
            print(f"      {x}")
    print(f"-> {out}")
    return 0 if not missing else 0


if __name__ == "__main__":
    sys.exit(main())
