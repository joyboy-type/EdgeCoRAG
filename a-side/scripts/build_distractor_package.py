"""构建 S3 纯干扰集（D1：同类不同实例）。

## 构造依据（可辩护的规则，非人工猜测）

MRAG-Bench 的 GT 图是**人工标注**的：题目 s 的每个 GT 图都被标注为「描绘 s 的正确答案」。
因此，若题目 s 的 `answer` 恰好等于目标题 q 的某个**错误选项**，
则 s 的 GT 图**描绘的是 q 的错误类别**，而不是 q 的正确类别。

这就是 D1「外观相似但对象不符」的**数据集标注保证**，不是我对图片内容的猜测。

## 三层校验（对应任务要求）

| 层 | 检查 | 作用 |
|---|---|---|
| L1 字节去重 | 候选 sha256 ∉ q 的查询图/GT 哈希集 | 排除完全相同字节（本数据集跨题共享图片达 2688 个哈希） |
| L2 近重复 | 候选 dHash 与 q 查询图汉明距离 > 阈值 | 排除视觉近重复（旋转/裁剪/翻转会漏，故只作辅助） |
| L3 语义三态 | 见下 | **最终判定** |

## 语义三态（不能仅凭哈希不同就当干扰）

| 判定 | 条件 | 是否进入纯干扰集 |
|---|---|---|
| `不支持` | 图片描绘的是 q 的**错误选项**类别（数据集标注保证），且 q 是**对象/实体识别**类（image_type ∈ 7 类） | ✅ 进入 |
| `无法判断` | 无法保证"不支持"（如 Others_Geo 区域图，错误区域图可能通过对比帮助排除，语义不纯） | ❌ **不进入**，单列报告 |
| `支持` | 与 q 查询图/GT 近重复或字节相同 | ❌ 剔除 |

**关键诚实声明**：
- 「不支持」的判定依据是**构造规则 + 数据集标注**，不是逐张人工看图；
- 因此报告里明确写"语义复核方式 = 构造保证（数据集标注），非逐张人工视觉复核"；
- Others_Geo 等无法保证的题**全部标「无法判断」并排除**，不虚称纯干扰。
- **绝不设置"允许 X% 未知"的门槛**——无法判断的题不是"允许"，而是"排除并单列"。

## 与 S1 对齐

- 图片数量 = 3（与 S1 top-3 一致）；
- 排序：候选按确定性顺序（错误选项顺序 → 来源题 qid 数值序）；
- 顺序规则随机但不设种子（本构造本身确定性），不需要额外打乱。

## GT/答案的使用边界

- **构造阶段**使用 answer / answer_choice / 错误选项：用于选"描绘错误类别"的候选；
- **审核阶段**使用 GT 哈希与查询图哈希：用于字节去重与近重复剔除；
- **推理阶段**：这些字段**绝不进入** `task_payload` 或任何模型消息——
  `distractor_type`、`semantic_verdict`、`source_answer` 只出现在 `scoring_only` 之外的
  独立审核文件里，模型的输入只有 `task_payload` + 图片。

用法:
    python scripts/build_distractor_package.py --list splits/dev.v2.txt --name dev_s3
    python scripts/build_distractor_package.py --list splits/smoke_20.v2.txt --name smoke_20_s3
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
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
LICENSE = "cc-by-4.0"
PKG_ROOT = cfg.ROOT / "packages"
NEAR_THRESH = 6
N_WANT = 3
MAX_CAND = 12

# 对象/实体识别类：构造规则可保证"描绘错误选项类别" → 判定为"不支持"
OBJECT_TYPES = {"Animal", "Car", "Flowers", "Fruit", "Cats", "Keyboard", "Building"}


def enc(im) -> bytes:
    b = io.BytesIO()
    im.convert("RGB").save(b, format="JPEG", quality=95)
    return b.getvalue()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


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


def norm(s: str) -> str:
    """规范化答案/选项文本用于匹配。

    实测数据集的答案与选项存在大小写/下划线/空格不一致：
      answer='silky_terrier'  vs  选项 'Silky_Terrier'
      answer='dalmatian'      vs  选项 'dalmatian'
    精确字符串匹配会漏掉大量合法候选（D1 覆盖率因此被压低）。
    规范化 = 小写 + '_' 转空格 + 合并空白 + 去首尾空格。
    """
    return " ".join(s.lower().replace("_", " ").split())


def read_qids(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s[6:] if s.startswith("mragb:") else s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or (PKG_ROOT / args.name)
    want = read_qids(args.list)
    if args.limit:
        want = want[: args.limit]
    want_set = set(want)
    print(f"S3/D1 干扰集  题单 {args.list.name}  {len(want)} 题")
    print(f"输出 {out}")

    cfg.apply_env()
    from datasets import load_dataset

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    # ---------------- Pass 1: 建 规范化answer -> (来源题, gt_idx) 索引 + 目标元数据 ----------------
    print("\n[Pass 1] 建索引（不编码图片）…")
    answer_map: dict[str, list[tuple[str, int]]] = defaultdict(list)
    targets: dict[str, dict] = {}
    t0 = time.time()
    for ex in ds:
        rid = str(ex["id"])
        ans_n = norm(ex["answer"])
        for k in range(len(ex["gt_images"])):
            answer_map[ans_n].append((rid, k))
        if rid in want_set:
            opt = {ex["answer_choice"]: ex[ex["answer_choice"]],
                   "A": ex["A"], "B": ex["B"], "C": ex["C"], "D": ex["D"]}
            targets[rid] = {
                "answer_choice": ex["answer_choice"],
                "answer_text": ex["answer"],
                "options": opt,
                "image_type": ex["image_type"],
                "scenario": ex["scenario"],
                "aspect": ex["aspect"],
                "question": ex["question"],
                "A": ex["A"], "B": ex["B"], "C": ex["C"], "D": ex["D"],
            }
    print(f"  规范化 answer 唯一值 {len(answer_map)}；目标题 {len(targets)}  "
          f"({time.time() - t0:.0f}s)")

    # ---------------- 选择候选（引用级，不编码）----------------
    print("[选择] 按错误选项收集候选…")
    # 正确选项文本 -> 错误选项文本（规范化去重，保序）
    for rid, t in targets.items():
        letters = ["A", "B", "C", "D"]
        wrong = [t[l] for l in letters if l != t["answer_choice"]]
        seen = set()
        wrong_u: list[str] = []
        for w in wrong:
            wn = norm(w)
            if wn not in seen:
                seen.add(wn)
                wrong_u.append(w)
        t["wrong_options"] = wrong_u
        refs: list[tuple[str, int, str]] = []   # (来源题, gt_idx, 错误选项文本)
        for w in wrong_u:
            wn = norm(w)
            for src_rid, gi in sorted(answer_map.get(wn, []),
                                      key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                if src_rid == rid:
                    continue
                refs.append((src_rid, gi, w))
                if len(refs) >= MAX_CAND:
                    break
            if len(refs) >= MAX_CAND:
                break
        t["candidate_refs"] = refs

    n_any = sum(1 for t in targets.values() if t["candidate_refs"])
    print(f"  有候选的目标题 {n_any}/{len(targets)}")

    # ---------------- Pass 2: 提取候选图与目标题查询图/GT ----------------
    print("\n[Pass 2] 提取候选图…")
    # 来源题 -> {gt_idx -> [目标题...]}
    need: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for rid, t in targets.items():
        for src_rid, gi, _ in t["candidate_refs"]:
            need[src_rid][gi].append(rid)

    # 候选缓存: target_rid -> list[dict]
    cand_buf: dict[str, list[dict]] = {r: [] for r in targets}
    # 目标题查询图/GT 哈希与 dHash（用于 L1/L2）
    t_meta: dict[str, dict] = {r: {"query_sha": None, "gt_shas": set(),
                                   "query_dhash": None, "query_bytes": None,
                                   "query_w": None, "query_h": None} for r in targets}
    tmpdir = out / "_cand_tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for ex in ds:
        rid = str(ex["id"])
        # 目标题：写查询图、算 GT 哈希
        if rid in targets:
            qb = enc(ex["image"])
            t_meta[rid]["query_sha"] = sha(qb)
            t_meta[rid]["query_dhash"] = dhash(ex["image"])
            t_meta[rid]["query_bytes"] = qb
            t_meta[rid]["query_w"] = ex["image"].width
            t_meta[rid]["query_h"] = ex["image"].height
            for g in ex["gt_images"]:
                t_meta[rid]["gt_shas"].add(sha(enc(g)))
        # 来源题：提取被引用的 GT 图
        if rid in need:
            for gi, target_list in need[rid].items():
                if gi < len(ex["gt_images"]):
                    im = ex["gt_images"][gi]
                    b = enc(im)
                    for trid in target_list:
                        cand_buf[trid].append({
                            "src_rid": rid, "src_gt_idx": gi,
                            "sha256": sha(b), "dhash": dhash(im),
                            "bytes": b, "w": im.width, "h": im.height,
                        })
    print(f"  提取完成 ({time.time() - t0:.0f}s)")

    # ---------------- Finalize: L1/L2/L3 + 选 3 ----------------
    print("\n[Finalize] 字节去重 / 近重复 / 语义三态…")
    rows: list[dict] = []
    index_rows: list[dict] = []
    review_rows: list[dict] = []
    stats = {"with_3": 0, "partial": 0, "none": 0,
             "unsupported_kept": 0, "undetermined_excluded": 0,
             "byte_dup_excluded": 0, "near_dup_excluded": 0}
    scenario_stat: dict[str, dict] = {}

    for rid, t in sorted(targets.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        qid = f"mragb:{rid}"
        m = t_meta[rid]
        kept: list[dict] = []
        undet: list[dict] = []
        review_all: list[dict] = []   # 全部候选的审核记录（含被排除者）
        for c in cand_buf[rid]:
            rec = {
                "qid": qid, "src_question": f"mragb:{c['src_rid']}",
                "src_gt_idx": c["src_gt_idx"],
                "distractor_type": "D1_same_class_wrong_instance",
                "source_answer_matches_wrong_option": True,
            }
            # L1 字节去重
            if c["sha256"] == m["query_sha"] or c["sha256"] in m["gt_shas"]:
                stats["byte_dup_excluded"] += 1
                rec["semantic_verdict"] = "支持(字节相同，剔除)"
                rec["fate"] = "excluded_byte_dup"
                rec["justification"] = "与本题查询图/GT 字节相同"
                rec["byte_dedup_passed"] = False
                review_all.append(rec)
                continue
            # L2 近重复（对查询图）
            hd = (ham(c["dhash"], m["query_dhash"])
                  if m["query_dhash"] is not None else None)
            if hd is not None and hd <= NEAR_THRESH:
                stats["near_dup_excluded"] += 1
                rec["semantic_verdict"] = "支持(视觉近重复，剔除)"
                rec["fate"] = "excluded_near_dup"
                rec["justification"] = f"与查询图 dHash 汉明距离 {hd} <= {NEAR_THRESH}"
                rec["byte_dedup_passed"] = True
                rec["near_dup_hamming_to_query"] = hd
                review_all.append(rec)
                continue
            # L3 语义三态
            verdict = ("不支持" if t["image_type"] in OBJECT_TYPES else "无法判断")
            rec["byte_dedup_passed"] = True
            rec["near_dup_hamming_to_query"] = hd
            rec["semantic_verdict"] = verdict
            rec["justification"] = (
                "构造保证：来源题标注该图为错误选项类别的实例"
                if verdict == "不支持"
                else "非对象识别类，无法由构造规则保证不支持，需人工看")
            if verdict == "不支持":
                c["semantic_verdict"] = verdict
                c["justification"] = rec["justification"]
                if len(kept) < N_WANT:
                    c["final_evidence_id"] = f"{qid}#distractor{len(kept)}"
                    rec["final_evidence_id"] = c["final_evidence_id"]
                    rec["fate"] = "kept"
                    kept.append(c)
                else:
                    rec["fate"] = "excess_unused"
                    rec["final_evidence_id"] = ""
                stats["unsupported_kept"] += 1
            else:
                undet.append(c)
                rec["fate"] = "excluded_undetermined"
                rec["final_evidence_id"] = ""
                stats["undetermined_excluded"] += 1
            review_all.append(rec)

        scen = t["scenario"]
        s = scenario_stat.setdefault(scen, {"total": 0, "with_3": 0, "partial": 0, "none": 0})
        s["total"] += 1
        status = "ok" if len(kept) == N_WANT else "insufficient"
        if len(kept) == N_WANT:
            s["with_3"] += 1
            stats["with_3"] += 1
        elif kept:
            s["partial"] += 1
            stats["partial"] += 1
        else:
            s["none"] += 1
            stats["none"] += 1

        # 写入最终图与索引（查询图 + kept 干扰图）
        ev = []
        imgsub = out / "images" / rid
        imgsub.mkdir(parents=True, exist_ok=True)
        # 查询图
        qfn = f"query_{rid}.jpg"
        (imgsub / qfn).write_bytes(m["query_bytes"])
        q_ref = {"evidence_id": f"{qid}#q", "role": "q", "rank": None,
                 "path": f"images/{rid}/{qfn}", "sha256": m["query_sha"],
                 "w": m["query_w"], "h": m["query_h"]}
        index_rows.append({"evidence_id": q_ref["evidence_id"], "raw_id": rid,
                           "qid": qid, "role": "q", "rank": "",
                           "path": q_ref["path"], "sha256": m["query_sha"],
                           "w": m["query_w"], "h": m["query_h"]})
        for i, c in enumerate(kept):
            fn = f"distractor_{rid}_{i}.jpg"
            (imgsub / fn).write_bytes(c["bytes"])
            ref = {"evidence_id": f"{qid}#distractor{i}", "role": "distractor",
                   "rank": i, "path": f"images/{rid}/{fn}", "sha256": c["sha256"],
                   "w": c["w"], "h": c["h"],
                   "retrieval_rank": i, "retrieval_score": None,
                   "used_in_prompt": True}
            ev.append(ref)
            index_rows.append({"evidence_id": ref["evidence_id"], "raw_id": rid,
                               "qid": qid, "role": "distractor", "rank": i,
                               "path": ref["path"], "sha256": c["sha256"],
                               "w": c["w"], "h": c["h"]})
        # 全部候选的审核记录（含被排除者）—— 供审计，不进入模型
        for rec in review_all:
            review_rows.append({
                "qid": rec.get("qid", ""),
                "final_evidence_id": rec.get("final_evidence_id", ""),
                "src_question": rec.get("src_question", ""),
                "src_gt_idx": rec.get("src_gt_idx", ""),
                "distractor_type": rec.get("distractor_type", ""),
                "semantic_verdict": rec.get("semantic_verdict", ""),
                "justification": rec.get("justification", ""),
                "byte_dedup_passed": rec.get("byte_dedup_passed", ""),
                "near_dup_hamming_to_query": rec.get("near_dup_hamming_to_query", ""),
                "source_answer_matches_wrong_option":
                    rec.get("source_answer_matches_wrong_option", ""),
                "fate": rec.get("fate", ""),
            })

        rows.append({
            "qid": qid, "raw_id": rid, "split": args.name,
            "scenario": scen, "aspect": t["aspect"],
            "question_image": q_ref,
            "evidence_order": ev,
            "num_evidence": len(ev),
            "pool_id": "pure_distractor_d1",
            "pool_gt_exact_match_rate": 0.0,
            "is_oracle": False,
            "retriever_id": None,
            "retrieval_scores": [None] * len(ev),
            "retrieval_ranks": [e["retrieval_rank"] for e in ev],
            "protocol_version": "proto_s3_d1_top3_v1",
            "prompt_image_slots": 1 + len(ev),
            "scenario_rule_applied": "d1_same_class_wrong_instance",
            "status": status,
            "notes": (None if status == "ok" else
                      f"仅 {len(kept)}/{N_WANT} 张「不支持」干扰图，"
                      f"无法判断 {len(undet)} 张；不足数未补造"),
            "task_payload": {"question": t["question"],
                             "choices": {"A": t["A"], "B": t["B"],
                                         "C": t["C"], "D": t["D"]}},
            "scoring_only": {
                "gold_choice": t["answer_choice"],
                "answer_text": t["answer_text"],
                "gt_evidence_ids": [],   # S3 不携带 GT 附件；由 B 侧评分时按题单取
                "gt_evidence_refs": None,
                "gt_evidence_ids_all": [],
                "gt_on_official_pool_ranks": []},
            "provenance": {
                "dataset_repo": REPO_ID, "dataset_revision": REVISION,
                "dataset_license": LICENSE,
                "split_version": args.list.stem,
                "evidence_version": args.name,
                "run_batch_id": None,
                "generated_by": "scripts/build_distractor_package.py",
                "encoding": {"format": "JPEG", "quality": 95,
                             "note": "JPEG q95 重编码；哈希与落盘字节同源"},
                "path_root": f"{args.name}/",
                "condition": "S3",
                "evidence_source": ("D1 纯干扰（同类不同实例）；"
                                    "构造+数据集标注保证描绘错误选项类别"),
                "config_hash": None},
        })

    # 查询图：S3 也需要查询图，补写
    # （上面 evidence_order 里 query 图 path 已指，但还没实际写查询图字节）
    # 简化：查询图从 S1 包复用（同 split 的 S1 包有 query 图）。
    # 这里明确声明依赖，避免重复写。

    # ---------------- 输出 ----------------
    rows.sort(key=lambda r: int(r["raw_id"]) if r["raw_id"].isdigit() else 0)
    (out / "evidence_list.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    with (out / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["evidence_id", "raw_id", "qid", "role",
                                           "rank", "path", "sha256", "w", "h"])
        w.writeheader()
        w.writerows(index_rows)
    with (out / "semantic_review.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(review_rows[0].keys()) if review_rows else
                           ["qid"])
        if review_rows:
            w.writeheader()
            w.writerows(review_rows)

    coverage = {
        "condition": "S3",
        "requested": len(want), "generated": len(rows),
        "with_full_3": stats["with_3"], "partial": stats["partial"], "none": stats["none"],
        "coverage_rate": round(stats["with_3"] / max(len(want), 1), 4),
        "coverage_rate_full_3": round(stats["with_3"] / max(len(want), 1), 4),
        "coverage_rate_definition": (
            "coverage_rate 定义为「满 3 张『不支持』干扰图的题数 / 题单题数」；"
            "partial/none 的题**不**计入，且单列报告，不静默删题。"),
        "subset_for_s1_s3_comparison": (
            "仅『with_full_3』的题可在 S1/S3 间公平比较；partial/none 题单列，不得混入"),
        "excluded_reasons": {
            "undetermined_semantics": stats["undetermined_excluded"],
            "byte_duplicate": stats["byte_dup_excluded"],
            "near_duplicate": stats["near_dup_excluded"],
        },
        "per_scenario": scenario_stat,
        "semantic_review_method": (
            "构造保证（数据集标注：来源题 GT 图标注为其答案，"
            "且该答案 == 目标题错误选项）。非逐张人工视觉复核。"),
        "gt_usage_disclosure": {
            "construction": ("使用 answer/answer_choice/错误选项选择『描绘错误类别』的候选"),
            "review": "使用 GT 哈希与查询图哈希做字节去重、查询图 dHash 做近重复",
            "inference": ("这些字段不进入 task_payload 或模型消息；"
                          "模型输入只有 task_payload + 图片"),
        },
        "issues": [],
    }
    (out / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    (out / "package_meta.json").write_text(json.dumps({
        "artifact_kind": "distractor_package",
        "package_version": args.name,
        "condition": "S3", "distractor_type": "D1",
        "pool_id": "pure_distractor_d1",
        "questions": len(rows),
        "with_full_3": stats["with_3"],
        "coverage_rate_full_3": coverage["coverage_rate_full_3"],
        "dataset": {"repo": REPO_ID, "revision": REVISION, "license": LICENSE},
        "not_claims": [
            "语义三态中『无法判断』的题已排除，未标为纯干扰",
            "未设置任何『允许未知比例』门槛",
            "D1 依赖构造规则+数据集标注，非逐张人工看图",
        ],
        "query_image_note": "查询图已写入本包（每题的 images/<raw_id>/query_<raw_id>.jpg）。",
        "deterministic": True,
        "generated_at": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    shutil.rmtree(tmpdir, ignore_errors=True)
    files = [f for f in (out / "images").rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    print(f"\n✅ {args.name}: {len(rows)} 题, {len(files)} 图, {total / 1024 ** 2:.1f} MiB")
    print(f"   满 3 张: {stats['with_3']}  部分: {stats['partial']}  无: {stats['none']}")
    print(f"   覆盖率(满3): {coverage['coverage_rate_full_3']:.1%}")
    print(f"   排除: 字节重复 {stats['byte_dup_excluded']}, "
          f"近重复 {stats['near_dup_excluded']}, 无法判断 {stats['undetermined_excluded']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
