"""A-01：核验 20 条案例卡的查询图/S1/S2 图片在本地固定证据包中是否可恢复。

只读本地现有资产（frozen_test_s1 / frozen_test_s2 证据包），不触发下载或生成。
输出 case_image_availability.csv（不含个人盘符/用户名/令牌）。

字段（按 A_TASKS.md）:
  qid, role, rank, evidence_id, sha256, local_exists, decode_ok, width, height,
  source_revision, package_id, availability_note

用法: python scripts/a01_case_image_availability.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

REPO_ID = "uclanlp/MRAG-Bench"
REVISION = "43620fde4044bb150e158c67ad7af6b6b11e1da2"
PKG = cfg.ROOT / "packages"
CASES_CSV = cfg.ROOT / "a-side" / "reports" / "next_stage_20261017" / "selected_cases_input.csv"
OUT = cfg.ROOT / "a-side" / "reports" / "next_stage_20261017" / "case_image_availability.csv"


def load_rows(pkg: Path) -> dict[str, dict]:
    """返回 qid -> evidence_list 行。"""
    jl = pkg / "evidence_list.jsonl"
    out = {}
    if not jl.exists():
        return out
    for line in jl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["qid"]] = r
    return out


def main() -> int:
    qids = []
    with CASES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["qid"] not in qids:
                qids.append(r["qid"])
    print(f"案例卡去重 qid 数: {len(qids)}")

    s1_rows = load_rows(PKG / "frozen_test_s1")
    s2_rows = load_rows(PKG / "frozen_test_s2")
    print(f"frozen_test_s1 行数 {len(s1_rows)}；frozen_test_s2 行数 {len(s2_rows)}")

    rows: list[dict] = []

    def add_ref(qid: str, ref: dict, package_id: str, pkg: Path) -> None:
        """ref 是 evidence_list 里的图片引用（含 path/sha256/w/h）。"""
        p = pkg / ref["path"]
        exists = p.exists()
        decode_ok = False
        w = h = ""
        hash_ok = ""
        if exists:
            b = p.read_bytes()
            h = hashlib.sha256(b).hexdigest()
            hash_ok = "match" if h == ref["sha256"] else "MISMATCH"
            from PIL import Image
            try:
                with Image.open(p) as im:
                    im.load()
                    w, h = im.width, im.height
                    decode_ok = True
            except Exception:  # noqa: BLE001
                decode_ok = False
        if not exists:
            avail = "missing"
        elif not decode_ok:
            avail = "decode_failed"
        elif hash_ok == "MISMATCH":
            avail = "hash_mismatch"
        else:
            avail = "available"
        rows.append({
            "qid": qid, "role": ref.get("role", "?"),
            "rank": "" if ref.get("rank") is None else ref.get("rank"),
            "evidence_id": ref["evidence_id"], "sha256": ref.get("sha256", ""),
            "local_exists": exists, "decode_ok": decode_ok,
            "width": w, "height": h,
            "source_revision": REVISION, "package_id": package_id,
            "availability_note": avail if avail == "available" else avail,
        })

    for qid in qids:
        # 查询图 + S1（frozen_test_s1）
        r = s1_rows.get(qid)
        if r:
            add_ref(qid, r["question_image"], "frozen_test_s1", PKG / "frozen_test_s1")
            for e in r["evidence_order"]:
                add_ref(qid, e, "frozen_test_s1", PKG / "frozen_test_s1")
        else:
            rows.append({"qid": qid, "role": "q", "rank": "", "evidence_id": "",
                         "sha256": "", "local_exists": False, "decode_ok": False,
                         "width": "", "height": "", "source_revision": REVISION,
                         "package_id": "frozen_test_s1",
                         "availability_note": "qid_not_in_s1_package"})
        # S2（frozen_test_s2）
        r2 = s2_rows.get(qid)
        if r2:
            for e in r2["evidence_order"]:
                add_ref(qid, e, "frozen_test_s2", PKG / "frozen_test_s2")
        else:
            rows.append({"qid": qid, "role": "gt", "rank": "", "evidence_id": "",
                         "sha256": "", "local_exists": False, "decode_ok": False,
                         "width": "", "height": "", "source_revision": REVISION,
                         "package_id": "frozen_test_s2",
                         "availability_note": "qid_not_in_s2_package"})

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["qid", "role", "rank", "evidence_id", "sha256", "local_exists",
                  "decode_ok", "width", "height", "source_revision",
                  "package_id", "availability_note"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 汇总
    from collections import Counter
    c = Counter(r["availability_note"] for r in rows)
    print(f"\n总记录 {len(rows)} 条")
    for k, v in c.most_common():
        print(f"  {k}: {v}")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
