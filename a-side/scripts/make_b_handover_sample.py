"""生成给 B 侧的接口样例(少量题目 + 图片 + 索引),并自校验契约。

产出(默认放到 EdgeCoRAG-B-handover/samples/):
    evidence_sample.jsonl   2–5 题的证据清单,符合 contracts/evidence_list.schema.json
    evidence_index.csv      evidence_id ↔ 文件 ↔ sha256 ↔ 尺寸 ↔ 原始 id 映射
    images/                 样例图片本体,便于 B 直接跑通
    sample_meta.json        生成参数与自校验结果

用法:
    python scripts/make_b_handover_sample.py --limit 5
    python scripts/make_b_handover_sample.py --limit 5 --pool official_retrieved_top5
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
# 官方池实测 GT 泄漏率,见 scripts/analyze_evidence_semantics.py
OFFICIAL_POOL_LEAKAGE = 0.559
OUT_DIR = cfg.ROOT.parent / "EdgeCoRAG-B-handover" / "samples"


def raw_bytes(im) -> bytes:
    """取图片**原始字节**,尽量不重编码。

    实测: datasets 流式模式下图片是 `PIL.JpegImagePlugin.JpegImageFile`,
    `_data` / `data` / `filename` **全部取不到**,所以必须走 PIL 的文件指针 `im.fp`
    读取底层 JPEG 字节。若直接 `im.convert("RGB").save(PNG)` 会重编码,
    体积膨胀约 6 倍(实测样例 50 MiB 中大部分是这种膨胀)。

    取不到 `fp` 时才回退到重编码,并统一用 **JPEG q95**(而非 PNG)以控制体积。
    """
    # 1) datasets 的 Image 特征若保留了原始字节
    for attr in ("_data", "data"):
        blob = getattr(im, attr, None)
        if isinstance(blob, (bytes, bytearray)):
            return bytes(blob)
    # 2) 文件路径
    fn = getattr(im, "filename", None)
    if fn and Path(fn).exists():
        return Path(fn).read_bytes()
    # 3) PIL 的文件指针(实测这条对 MRAG-Bench 生效)
    fp = getattr(im, "fp", None)
    if fp is not None and hasattr(fp, "read") and hasattr(fp, "seek"):
        try:
            pos = fp.tell()
            fp.seek(0)
            data = fp.read()
            fp.seek(pos)
            if data:
                return bytes(data)
        except Exception:  # noqa: BLE001
            pass
    # 4) 兜底: 重编码为 JPEG
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def sniff_ext(b: bytes, fallback: str = "bin") -> str:
    """按魔数判断真实容器格式。

    数据集里的图片是 JPEG;若按 .png 落盘会是"内容 JPEG 但扩展名 png"的错误命名。
    按魔数决定扩展名,保证 扩展名—内容 一致。
    """
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:2] == b"BM":
        return "bmp"
    return fallback


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--pool", default="official_retrieved_top5",
                    choices=["official_retrieved_top5"])
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    cfg.apply_env()
    from datasets import load_dataset

    out = args.out
    imgdir = out / "images"
    if imgdir.exists():
        shutil.rmtree(imgdir)
    imgdir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(REPO_ID, split="test", streaming=True, revision=REVISION)

    rows: list[dict] = []
    index_rows: list[dict] = []
    frozen_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def dump(im, fname: str, qid: str, role: str, rank, **extra) -> dict:
        b = raw_bytes(im)
        # 按内容的真实格式决定扩展名,避免"内容 JPEG 却叫 .png"
        ext = sniff_ext(b, Path(fname).suffix.lstrip(".") or "bin")
        p = imgdir / f"{Path(fname).stem}.{ext}"
        p.write_bytes(b)
        sha = hashlib.sha256(b).hexdigest()
        ref = {
            "evidence_id": f"{qid}#{role}{'' if rank is None else rank}",
            "role": role,
            "rank": rank,
            "path": f"images/{p.name}",
            "sha256": sha,
            "w": im.width,
            "h": im.height,
        }
        ref.update(extra)
        index_rows.append({
            "evidence_id": ref["evidence_id"], "raw_id": qid.split(":", 1)[1],
            "qid": qid, "role": role, "rank": "" if rank is None else rank,
            "path": ref["path"], "sha256": sha, "w": im.width, "h": im.height,
        })
        return ref

    for i, ex in enumerate(ds):
        if i >= args.limit:
            break
        raw_id = ex["id"]
        qid = f"mragb:{raw_id}"

        q_ref = dump(ex["image"], f"q_{raw_id}.png", qid, "q", None)

        # 证据: 官方候选池,送入顺序 = 官方排名升序
        # role 必须用 schema 定义的 'official_retrieved'(不能用缩写 'ret'),
        # 否则 evidence_id 不匹配 contracts/evidence_list.schema.json 的 pattern。
        ev_refs = []
        scores = []
        ranks = []
        for j, im in enumerate(ex["retrieved_images"]):
            ev_refs.append(dump(im, f"official_retrieved_{raw_id}_{j}.png", qid,
                                "official_retrieved", j,
                                retrieval_rank=j, retrieval_score=None))
            scores.append(None)      # 官方未提供分数
            ranks.append(j)

        # 计算该题 GT 落在官方候选池的位置(池泄漏量化,仅供分析)
        ret_shas = [e["sha256"] for e in ev_refs]
        gt_refs = []
        gt_hit_ranks = []
        for k, gim in enumerate(ex["gt_images"]):
            gsha = hashlib.sha256(raw_bytes(gim)).hexdigest()
            gt_refs.append(f"{qid}#gt{k}")
            if gsha in ret_shas:
                gt_hit_ranks.append(ret_shas.index(gsha))

        rec = {
            "qid": qid,
            "raw_id": raw_id,
            "split": "smoke_20",
            "scenario": ex["scenario"],
            "aspect": ex["aspect"],
            "question_image": q_ref,
            "evidence_order": ev_refs,
            "num_evidence": len(ev_refs),
            "pool_id": args.pool,
            "pool_leakage_rate": OFFICIAL_POOL_LEAKAGE,
            "is_oracle": False,
            "retriever_id": None,          # 官方池不由我检索器产生
            "retrieval_scores": scores,
            "retrieval_ranks": ranks,
            "protocol_version": "proto_official_v1",
            "prompt_image_slots": 2 if ex["scenario"] == "Incomplete" else 6,
            "status": "ok",
            "notes": None,
            "task_payload": {
                "question": ex["question"],
                "choices": {"A": ex["A"], "B": ex["B"], "C": ex["C"], "D": ex["D"]},
            },
            # ⚠️ 仅供评分/Oracle/离线分析,严禁进入证据选择或 prompt
            "scoring_only": {
                "gold_choice": ex["answer_choice"],
                "answer_text": ex["answer"],
                "gt_evidence_ids": gt_refs,
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
        leak = f"GT 命中官方池 rank={gt_hit_ranks}" if gt_hit_ranks else "GT 未在官方池中"
        print(f"  [{i + 1}/{args.limit}] {qid}  scenario={ex['scenario']:12s} "
              f"证据 {len(ev_refs)} 张  {leak}")

    # 写 jsonl
    (out / "evidence_sample.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    # 写索引
    with (out / "evidence_index.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        cols = ["evidence_id", "raw_id", "qid", "role", "rank", "path", "sha256", "w", "h"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(index_rows)

    # 契约自校验
    checks = validate(rows, index_rows, imgdir)
    (out / "sample_meta.json").write_text(json.dumps({
        "generated_at": frozen_at,
        "pool_id": args.pool,
        "num_questions": len(rows),
        "num_evidence_refs": len(index_rows),
        "dataset": {"repo": REPO_ID, "revision": REVISION, "license": LICENSE},
        "official_pool_gt_leakage_rate": OFFICIAL_POOL_LEAKAGE,
        "self_checks": checks,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n产出目录: {out}")
    for f in ("evidence_sample.jsonl", "evidence_index.csv", "sample_meta.json"):
        print(f"  {f}  {(out / f).stat().st_size:>8,} B")
    n = len(list(imgdir.glob("*")))
    print(f"  images/  {n} 个文件  "
          f"{sum(p.stat().st_size for p in imgdir.glob('*')) / 1024 ** 2:.1f} MiB")

    print("\n=== 自校验 ===")
    for k, v in checks.items():
        mark = "✅" if v is True else ("⚠️" if v is None else "❌")
        print(f"  {mark} {k}: {v}")
    return 0 if all(v is not False for v in checks.values()) else 1


def validate(rows: list[dict], index_rows: list[dict], imgdir: Path) -> dict:
    """本地自校验:字段齐全、文件存在、哈希一致、ID 唯一、不含 GT 泄漏声明。"""
    checks: dict = {}

    checks["每行必需字段齐全"] = all(
        all(k in r for k in ("qid", "raw_id", "split", "scenario", "aspect",
                             "question_image", "evidence_order", "num_evidence",
                             "pool_id", "retriever_id", "protocol_version", "status",
                             "task_payload", "scoring_only", "provenance"))
        for r in rows)

    checks["evidence_id 全局唯一"] = (
        len({r["evidence_id"] for r in index_rows}) == len(index_rows))

    # 文件存在 + sha256 一致
    ok_file = ok_hash = True
    for r in index_rows:
        p = imgdir.parent / r["path"]
        if not p.exists():
            ok_file = False
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            ok_hash = False
    checks["索引中所有文件存在"] = ok_file
    checks["文件 sha256 与索引一致"] = ok_hash

    # query 图不在证据里
    bad = 0
    for r in rows:
        qs = r["question_image"]["sha256"]
        if any(e["sha256"] == qs for e in r["evidence_order"]):
            bad += 1
    checks["查询图未混入证据"] = (bad == 0)

    checks["num_evidence 与 evidence_order 长度一致"] = all(
        r["num_evidence"] == len(r["evidence_order"]) for r in rows)

    checks["is_oracle=false 未使用 GT"] = all(r["is_oracle"] is False for r in rows)

    checks["已声明官方池泄漏率"] = all(
        r["pool_leakage_rate"] == OFFICIAL_POOL_LEAKAGE for r in rows)

    checks["scoring_only 区存在且含 gold_choice"] = all(
        isinstance(r.get("scoring_only"), dict) and "gold_choice" in r["scoring_only"]
        for r in rows)

    checks["task_payload 含题干与四选项"] = all(
        r.get("task_payload", {}).get("question")
        and set(r["task_payload"].get("choices") or {}) == {"A", "B", "C", "D"}
        for r in rows)

    checks["gt 泄漏位点已逐题量化"] = all(
        isinstance(r["scoring_only"].get("gt_on_official_pool_ranks"), list)
        for r in rows)

    # evidence_order 内的 sha256 必须都在索引里
    idx_shas = {r["sha256"] for r in index_rows}
    checks["证据 sha256 均可在索引中查到"] = all(
        e["sha256"] in idx_shas for r in rows for e in r["evidence_order"])

    return checks


if __name__ == "__main__":
    sys.exit(main())
