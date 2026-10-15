"""校验 EdgeCoRAG-B-handover 包里所有 JSON/JSONL/CSV 的格式合法性。

用法: python scripts/validate_handover_package.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

HANDOVER = cfg.ROOT.parent / "EdgeCoRAG-B-handover"


def main() -> int:
    if not HANDOVER.exists():
        print(f"✗ 交接目录不存在: {HANDOVER}")
        return 1

    print(f"交接包: {HANDOVER}\n")
    bad = 0
    n_json = n_jsonl = n_csv = 0

    # JSON
    for p in sorted(HANDOVER.rglob("*.json")):
        try:
            json.loads(p.read_text(encoding="utf-8"))
            print(f"  OK   {p.relative_to(HANDOVER)}")
            n_json += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {p.relative_to(HANDOVER)}: {exc}")
            bad += 1

    # JSONL
    for p in sorted(HANDOVER.rglob("*.jsonl")):
        ok = 0
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    json.loads(line)
                    ok += 1
            print(f"  OK   {p.relative_to(HANDOVER)}  ({ok} 行)")
            n_jsonl += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {p.relative_to(HANDOVER)} 第 {i} 行: {exc}")
            bad += 1

    # CSV
    for p in sorted(HANDOVER.rglob("*.csv")):
        try:
            with p.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            cols = list(rows[0].keys()) if rows else []
            print(f"  OK   {p.relative_to(HANDOVER)}  ({len(rows)} 行, {len(cols)} 列)")
            n_csv += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {p.relative_to(HANDOVER)}: {exc}")
            bad += 1

    files = [f for f in HANDOVER.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    print(f"\n汇总: {n_json} 个 json / {n_jsonl} 个 jsonl / {n_csv} 个 csv")
    print(f"      共 {len(files)} 个文件, {total / 1024 ** 2:.1f} MiB")
    print(f"      格式错误: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
