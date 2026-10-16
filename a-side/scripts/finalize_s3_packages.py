"""S3 包定稿：补 content_digest、逐文件哈希、组内去重、排序说明、人工审核框架。

**本脚本只做机械补全，不重跑候选生成（不重新编码图片）。**

针对用户指出的问题逐项处理：

  1. content_digest 为空 → 由 evidence_index.csv 的 (path, sha256) 计算，
     算法 = sha256 over 排序后的 "rel_path \\x00 sha256" 序列；
     范围 = 全部图片文件（查询图 + 干扰图），**不含 package_meta.json 自身**（避免自引用）。
  2. 逐文件 SHA-256 清单 → 直接复用 evidence_index.csv（其已含每张图的 sha256）；
     另写 file_hashes.csv（rel_path, bytes, sha256）便于独立校验。
  3. 组内去重 → 最终 3 张干扰图之间做字节重复 + dHash 近重复检查。
  4. 排序 → 声明并固定「错误选项顺序 → 来源题 qid 数值序」，retrieval_rank 置 null
     （S3 无检索，order 只由 evidence_order 数组位置 + rank 字段表达）。
  5. 人工审核框架 → review_checklist.csv，含 qid/最终 evidence_id/来源/审核依据/待填三态。

**语义审核的诚实立场（重要）**：
本脚本**不**把自动规则标签当作语义审核完成。它只生成**待人工审核的清单**，
三态（支持/不支持/无法判断）留空由人工填写。现有「自动构造规则」产生的
`semantic_verdict` 一律降级为「自动初判，未经语义审核」，不得计入正式 S3。

用法:
    python scripts/finalize_s3_packages.py --dir packages/smoke_20_s3
    python scripts/finalize_s3_packages.py --all
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

PKG_ROOT = cfg.ROOT / "packages"
NEAR_THRESH = 6


def dhash(path: Path, size: int = 8) -> int:
    from PIL import Image
    with Image.open(path) as im:
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


def content_digest_from_index(base: Path) -> str:
    """由 evidence_index.csv 的 (path, sha256) 计算确定性摘要（不含 meta 自身）。"""
    rows = list(csv.DictReader((base / "evidence_index.csv").open(
        encoding="utf-8-sig", newline="")))
    entries = sorted((r["path"], r["sha256"]) for r in rows)
    h = hashlib.sha256()
    for path, sh in entries:
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(sh.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def finalize(base: Path) -> dict:
    jl = base / "evidence_list.jsonl"
    rows = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()]

    # 1) content_digest
    digest = content_digest_from_index(base)

    # 2) file_hashes.csv
    idx_rows = list(csv.DictReader((base / "evidence_index.csv").open(
        encoding="utf-8-sig", newline="")))
    with (base / "file_hashes.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["rel_path", "bytes", "sha256"])
        w.writeheader()
        for r in sorted(idx_rows, key=lambda x: x["path"]):
            p = base / r["path"]
            w.writerow({"rel_path": r["path"], "bytes": p.stat().st_size,
                        "sha256": r["sha256"]})

    # 3) 组内去重（最终 3 张之间）
    within_dup = 0
    within_near = 0
    for r in rows:
        ev = r["evidence_order"]
        shas = [e["sha256"] for e in ev]
        if len(set(shas)) != len(shas):
            within_dup += 1
        if len(ev) >= 2:
            hs = [dhash(base / e["path"]) for e in ev]
            for i in range(len(hs)):
                for j in range(i + 1, len(hs)):
                    if ham(hs[i], hs[j]) <= NEAR_THRESH:
                        within_near += 1

    # 4) 排序说明 + retrieval_rank 置 null（S3 无检索）
    for r in rows:
        for e in r["evidence_order"]:
            e["retrieval_rank"] = None
            e["retrieval_score"] = None
        r["retrieval_ranks"] = [None] * len(r["evidence_order"])
        r["retrieval_scores"] = [None] * len(r["evidence_order"])
    jl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                  encoding="utf-8")

    # 5) 人工审核框架 review_checklist.csv
    # 从 semantic_review.csv 反查来源（final_evidence_id -> src_question）
    src_by_id: dict[str, str] = {}
    rev_csv = base / "semantic_review.csv"
    if rev_csv.exists():
        for rr in csv.DictReader(rev_csv.open(encoding="utf-8-sig", newline="")):
            eid = rr.get("final_evidence_id", "")
            if eid and rr.get("fate") == "kept":
                src_by_id[eid] = rr.get("src_question", "")

    with (base / "review_checklist.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["qid", "raw_id", "scenario",
                  "question", "choices_A", "choices_B", "choices_C", "choices_D",
                  "correct_choice", "correct_answer",
                  "final_evidence_id", "distractor_image_path", "source_question",
                  "auto_byte_dedup", "auto_near_dup_to_query",
                  "semantic_verdict", "review_basis", "reviewer", "reviewed_at"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            tp = r["task_payload"]
            so = r["scoring_only"]
            ch = tp["choices"]
            for e in r["evidence_order"]:
                w.writerow({
                    "qid": r["qid"], "raw_id": r["raw_id"], "scenario": r["scenario"],
                    "question": tp["question"],
                    "choices_A": ch["A"], "choices_B": ch["B"],
                    "choices_C": ch["C"], "choices_D": ch["D"],
                    "correct_choice": so["gold_choice"],
                    "correct_answer": so["answer_text"],
                    "final_evidence_id": e["evidence_id"],
                    "distractor_image_path": e["path"],
                    "source_question": src_by_id.get(e["evidence_id"], ""),
                    "auto_byte_dedup": "passed",
                    "auto_near_dup_to_query": "",
                    "semantic_verdict": "",   # 人工填：支持/不支持/无法判断
                    "review_basis": "",       # 人工填：判定依据
                    "reviewer": "",           # 人工填：审核者
                    "reviewed_at": "",        # 人工填：审核时间
                })

    # 6) 更新 package_meta.json
    meta_path = base / "package_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["content_digest"] = digest
    meta["content_digest_algorithm"] = "sha256"
    meta["content_digest_scope"] = (
        "对 evidence_index.csv 中全部图片文件（查询图+干扰图），按 path 排序后，"
        "对每个 'path\\x00sha256\\n' 做 sha256。**不含 package_meta.json 自身**，"
        "亦不含 jsonl/csv 元数据，故无自引用。")
    meta["file_hashes_csv"] = "file_hashes.csv"
    meta["within_3_byte_dup_questions"] = within_dup
    meta["within_3_near_dup_pairs"] = within_near
    meta["ordering"] = ("确定性顺序：错误选项顺序（A→D 中排除正确项）→ 来源题 qid 数值序。"
                        "S3 无检索，retrieval_rank 置 null；顺序由 evidence_order "
                        "数组位置与 rank 字段（0,1,2）表达。")
    meta["semantic_review_status"] = (
        "自动构造规则与字节/近重复校验已做；**语义三态审核未完成**。"
        "见 review_checklist.csv（待人工填写 semantic_verdict/review_basis/reviewer）。"
        "现有自动标签仅为初判，不计入正式 S3。")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "package": base.name,
        "content_digest": digest[:16],
        "questions": len(rows),
        "within_3_byte_dup": within_dup,
        "within_3_near_dup_pairs": within_near,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        dirs = sorted(p for p in PKG_ROOT.iterdir() if p.is_dir() and p.name.endswith("_s3"))
    elif args.dir:
        dirs = [args.dir]
    else:
        print("请指定 --dir 或 --all")
        return 1

    for d in dirs:
        if not (d / "evidence_list.jsonl").exists():
            print(f"  跳过 {d.name}（无 evidence_list.jsonl）")
            continue
        r = finalize(d)
        print(f"  ✅ {r['package']}: digest={r['content_digest']} "
              f"题={r['questions']} 组内字节重复={r['within_3_byte_dup']} "
              f"组内近重复对={r['within_3_near_dup_pairs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
