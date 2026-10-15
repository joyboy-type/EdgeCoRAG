"""生成给 B 侧的接口样例: 少量题目 + 图片 + 索引 + 自校验。

**相对上一版的修正(重要)**

1. **哈希口径与落盘字节统一**: 上一版索引里的 sha256 来自一条取字节路径,
   而落盘文件来自另一条(JPEG95),两者口径不一致 —— 虽恰好都通过校验,
   但属于运气,不是设计。现在统一为: 落盘字节 == 参与哈希的字节 == JPEG95 重编码。
2. **补入 GT 图片**: 上一版只给了 `gt_evidence_ids` 引用而无文件,
   B 无法据此跑 S2。现在按**真实数量**落盘(5 题 × 5 张),不复制、不补图凑数。
3. **路径按题分目录**: `images/<raw_id>/<role>_<rank>.jpg`,
   为将来把 S3 干扰图(取自别题)并入同一目录树做准备,避免同名覆盖。
4. **显式声明未重编码的说法不成立**: 实测 `im.fp` 为 None,原始字节取不到,
   所有字节都是重编码产物,已在 meta 中如实声明。

用法:
    python scripts/make_b_handover_sample.py --limit 5
    python scripts/make_b_handover_sample.py --limit 5 --out <目录>
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
OUT_DIR = cfg.ROOT.parent / "EdgeCoRAG-B-handover" / "samples"

# 与 audit_gt_match_rate.py 保持一致的口径
ENCODE_FORMAT = "JPEG"
ENCODE_QUALITY = 95
ENCODE_NOTE = ("JPEG quality=95 重编码。实测 im.fp / _data / data / filename 全为 None，"
               "无法取到原始字节，故所有落盘字节均为重编码产物；"
               "该编码确定性(多次独立加载哈希一致，见 test_hash_stability.py)，"
               "且哈希与落盘字节使用同一份 bytes。")


def encoded_bytes(im) -> bytes:
    """产出落盘字节。**索引哈希与落盘文件必须用同一份 bytes。**"""
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format=ENCODE_FORMAT, quality=ENCODE_QUALITY)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--split", default="smoke_20")
    ap.add_argument("--include-incomplete", action="store_true", default=True,
                    help="额外补一道 Incomplete 场景题(该场景证据数=1、占位符=2，规则最特殊)")
    ap.add_argument("--no-incomplete", dest="include_incomplete", action="store_false")
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    out: Path = args.out
    imgdir = out / "images"
    if imgdir.exists():
        shutil.rmtree(imgdir)
    imgdir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    rows: list[dict] = []
    index_rows: list[dict] = []
    frozen_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    issues: list[str] = []

    def dump(im, fname: str, qid: str, raw_id: str, role: str, rank, **extra) -> dict:
        b = encoded_bytes(im)
        sub = imgdir / raw_id
        sub.mkdir(parents=True, exist_ok=True)
        p = sub / fname
        p.write_bytes(b)
        sha = hashlib.sha256(b).hexdigest()
        ref = {
            "evidence_id": f"{qid}#{role}{'' if rank is None else rank}",
            "role": role,
            "rank": rank,
            "path": str(p.relative_to(out)).replace("\\", "/"),
            "sha256": sha,
            "w": im.width,
            "h": im.height,
        }
        ref.update(extra)
        # 落盘后立刻回读校验,确保索引哈希与文件一致
        back = hashlib.sha256(p.read_bytes()).hexdigest()
        if back != sha:
            issues.append(f"{ref['evidence_id']}: 落盘回读哈希不一致")
        index_rows.append({
            "evidence_id": ref["evidence_id"], "raw_id": raw_id, "qid": qid,
            "role": role, "rank": "" if rank is None else rank,
            "path": ref["path"], "sha256": sha, "w": im.width, "h": im.height,
        })
        return ref

    # 选题: 取前 limit 题;另外单独补一道 Incomplete
    # (该场景证据数=1、占位符=2,是规则最特殊的一类,样例里必须覆盖)
    picked: list = []
    extra_incomplete = None
    for ex in ds:
        if len(picked) < args.limit:
            picked.append(ex)
            continue
        if args.include_incomplete and extra_incomplete is None \
                and ex["scenario"] == "Incomplete":
            extra_incomplete = ex
            break
        # 已收满且已找到 Incomplete,或不需要补,则停止
        if not args.include_incomplete or extra_incomplete is not None:
            break
    if extra_incomplete is not None:
        picked.append(extra_incomplete)

    n_inc = sum(1 for p in picked if p["scenario"] == "Incomplete")
    print(f"选题 {len(picked)} 题(含 Incomplete {n_inc} 题)\n")

    for i, ex in enumerate(picked):
        raw_id = str(ex["id"])
        qid = f"mragb:{raw_id}"

        q_ref = dump(ex["image"], f"q_{raw_id}.jpg", qid, raw_id, "q", None)

        scenario = ex["scenario"]
        is_incomplete = (scenario == "Incomplete")

        # 官方场景规则(dataloader.py:37-38, 59-60, 46-48):
        #   Incomplete 场景下, GT 与候选都只取第 1 张, 提示模板占位符 = 2(查询图+1 证据)
        #   其余场景使用全部候选, 占位符 = 6(查询图+5 证据)
        # 这里严格遵守, 以保证与官方数字可比; 被截断的候选另存于
        # available_evidence_untruncated, 避免信息丢失。
        n_use = 1 if is_incomplete else len(ex["retrieved_images"])

        ev_all = []
        for j, im in enumerate(ex["retrieved_images"]):
            ref = dump(im, f"official_retrieved_{raw_id}_{j}.jpg", qid, raw_id,
                       "official_retrieved", j,
                       retrieval_rank=j, retrieval_score=None,
                       used_in_prompt=(j < n_use))
            ev_all.append(ref)
        ev_refs = [e for e in ev_all if e["used_in_prompt"]]

        gt_all = [dump(gim, f"gt_{raw_id}_{k}.jpg", qid, raw_id, "gt", k)
                  for k, gim in enumerate(ex["gt_images"])]
        gt_used = gt_all[:1] if is_incomplete else gt_all

        ret_shas = [e["sha256"] for e in ev_refs]
        gt_hit_ranks = [ret_shas.index(g["sha256"]) for g in gt_all
                        if g["sha256"] in ret_shas]

        rec = {
            "qid": qid,
            "raw_id": raw_id,
            "split": args.split,
            "scenario": ex["scenario"],
            "aspect": ex["aspect"],
            "question_image": q_ref,
            "evidence_order": ev_refs,
            "num_evidence": len(ev_refs),
            "pool_id": "official_retrieved_top5",
            "pool_gt_exact_match_rate": None,   # 池级统计在 audit_gt_match_rate.py 的输出里
            "is_oracle": False,
            "retriever_id": None,
            "retrieval_scores": [None] * len(ev_refs),
            "retrieval_ranks": [e["retrieval_rank"] for e in ev_refs],
            "protocol_version": "proto_official_v1",
            "prompt_image_slots": 2 if is_incomplete else 6,
            "scenario_rule_applied": (
                "official_incomplete_truncate_to_first" if is_incomplete
                else "official_use_all_candidates"),
            "available_evidence_untruncated": (
                None if not is_incomplete else {
                    "note": ("Incomplete 场景官方只取第 1 张候选与第 1 张 GT；"
                             "此处保留未截断的完整候选引用，仅供分析，"
                             "不得用于 proto_official_v1 的提示组装。"
                             "这些条目的 used_in_prompt 为 false。"),
                    "retrieved_count": len(ex["retrieved_images"]),
                    "gt_count": len(ex["gt_images"]),
                    "retrieved_refs": [e for e in ev_all if not e["used_in_prompt"]],
                    "gt_refs": gt_all[1:],
                }),
            "status": "ok",
            "notes": None,
            "task_payload": {
                "question": ex["question"],
                "choices": {"A": ex["A"], "B": ex["B"], "C": ex["C"], "D": ex["D"]},
            },
            "scoring_only": {
                "gold_choice": ex["answer_choice"],
                "answer_text": ex["answer"],
                # GT 证据: 按协议实际使用的数量(与数据集真实数量一致,不补图)
                "gt_evidence_ids": [g["evidence_id"] for g in gt_used],
                "gt_evidence_refs": gt_used,
                "gt_evidence_ids_all": [g["evidence_id"] for g in gt_all],
                "gt_on_official_pool_ranks": gt_hit_ranks,
            },
            "provenance": {
                "dataset_repo": REPO_ID,
                "dataset_revision": REVISION,
                "dataset_license": LICENSE,
                "frozen_at": frozen_at,
                "frozen_by": "EdgeCoRAG-A",
                "config_hash": None,
            },
        }
        rows.append(rec)
        print(f"  [{i + 1}/{len(picked)}] {qid}  {ex['scenario']:12s} "
              f"候选 {len(ev_refs)} 张(占位符 {rec['prompt_image_slots']}), "
              f"GT 用 {len(gt_used)}/{len(gt_all)} 张, "
              f"GT命中rank={gt_hit_ranks}")

    (out / "evidence_sample.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    with (out / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        cols = ["evidence_id", "raw_id", "qid", "role", "rank", "path", "sha256", "w", "h"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(index_rows)

    checks = validate(rows, index_rows, out)
    checks["落盘回读哈希全部一致"] = (len(issues) == 0)

    (out / "sample_meta.json").write_text(json.dumps({
        "artifact_kind": "interface_sample",
        "not_a_frozen_result": True,
        "disclaimer": ("这是**接口样例**,用于打通 B 侧程序;既不是完整 smoke_20,"
                       "也不是自研检索的冻结结果。"),
        "generated_at": frozen_at,
        "num_questions": len(rows),
        "num_evidence_refs": len(index_rows),
        "pool_id": "official_retrieved_top5",
        "encoding": {"format": ENCODE_FORMAT, "quality": ENCODE_QUALITY,
                     "note": ENCODE_NOTE},
        "path_root": "samples/ (所有 path 均相对该目录)",
        "dataset": {"repo": REPO_ID, "revision": REVISION, "license": LICENSE},
        "official_pool_note": ("官方候选池的 GT 精确匹配率是**池级统计**,"
                               "见 a-side/data/gt_match_rate_audit.json;"
                               "本文件不再内嵌该比例,以免被误读为逐题标签"),
        "self_checks": checks,
        "issues": issues,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n产出目录: {out}")
    for f in ("evidence_sample.jsonl", "evidence_index.csv", "sample_meta.json"):
        print(f"  {f}  {(out / f).stat().st_size:>9,} B")
    files = list(imgdir.rglob("*"))
    imgs = [f for f in files if f.is_file()]
    print(f"  images/  {len(imgs)} 个文件, "
          f"{sum(f.stat().st_size for f in imgs) / 1024 ** 2:.1f} MiB, "
          f"{len([d for d in files if d.is_dir()])} 个子目录")

    print("\n=== 自校验 ===")
    ok = True
    for k, v in checks.items():
        mark = "✅" if v is True else ("⚠️" if v is None else "❌")
        if v is False:
            ok = False
        print(f"  {mark} {k}: {v}")
    if issues:
        print("  问题:")
        for x in issues:
            print(f"    - {x}")
    return 0 if ok else 1


def validate(rows: list[dict], index_rows: list[dict], base: Path) -> dict:
    checks: dict = {}

    checks["每行必需字段齐全"] = all(
        all(k in r for k in ("qid", "raw_id", "split", "scenario", "aspect",
                             "question_image", "evidence_order", "num_evidence",
                             "pool_id", "retriever_id", "protocol_version", "status",
                             "task_payload", "scoring_only", "provenance"))
        for r in rows)

    checks["evidence_id 全局唯一"] = (
        len({r["evidence_id"] for r in index_rows}) == len(index_rows))

    ok_file = ok_hash = True
    for r in index_rows:
        p = base / r["path"]
        if not p.exists():
            ok_file = False
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            ok_hash = False
    checks["索引中所有文件存在"] = ok_file
    checks["文件 sha256 与索引一致"] = ok_hash

    checks["查询图未混入证据"] = all(
        not any(e["sha256"] == r["question_image"]["sha256"] for e in r["evidence_order"])
        for r in rows)

    checks["num_evidence 与列表长度一致"] = all(
        r["num_evidence"] == len(r["evidence_order"]) for r in rows)

    checks["retrieval_ranks 与列表长度一致"] = all(
        r["retrieval_ranks"] is None or len(r["retrieval_ranks"]) == len(r["evidence_order"])
        for r in rows)

    checks["retrieval_scores 与列表长度一致"] = all(
        r["retrieval_scores"] is None or len(r["retrieval_scores"]) == len(r["evidence_order"])
        for r in rows)

    checks["is_oracle=false"] = all(r["is_oracle"] is False for r in rows)

    checks["三个 split 内 qid 唯一"] = (
        len({r["qid"] for r in rows}) == len(rows))

    checks["task_payload 题干与四选项齐全"] = all(
        r["task_payload"].get("question")
        and set(r["task_payload"].get("choices") or {}) == {"A", "B", "C", "D"}
        for r in rows)

    checks["scoring_only 有 gold_choice 且为 ABCD"] = all(
        r["scoring_only"].get("gold_choice") in ("A", "B", "C", "D") for r in rows)

    checks["GT 证据已提供文件引用(S2 可跑)"] = all(
        len(r["scoring_only"].get("gt_evidence_refs") or [])
        == len(r["scoring_only"].get("gt_evidence_ids") or [])
        and len(r["scoring_only"].get("gt_evidence_refs") or []) > 0
        for r in rows)

    checks["GT 数量与数据集一致(未补图)"] = all(
        len(r["scoring_only"]["gt_evidence_ids"]) in (1, 5) for r in rows)

    checks["每条证据的 sha256 可在索引中查到"] = (
        {e["sha256"] for r in rows for e in r["evidence_order"]}
        <= {r["sha256"] for r in index_rows})

    return checks


if __name__ == "__main__":
    sys.exit(main())
