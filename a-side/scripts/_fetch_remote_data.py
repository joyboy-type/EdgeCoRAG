"""下载本批分析所需的远端派生数据（只读；不重新分发原题/原始响应）。

文件均为结果分支已公开的派生台账：
  - logs/B_predictions.jsonl.gz                      v1.10.1 五模型逐题记录（含 S0/S1/S2/S3）
  - logs/results_20261020/no_self_scored_outcomes.jsonl.gz
  - logs/results_20261020/legacy_self_match_scored_outcomes.jsonl.gz
  - logs/README.md, provenance/results_20261020/completed_experiments.json

用法: python scripts/_fetch_remote_data.py [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_api import get_file  # noqa: E402

REF = "2975d9cae550339628681dc397d80ed9ab6e0158"
FILES = [
    "logs/B_predictions.jsonl.gz",
    "logs/README.md",
    "logs/results_20261020/no_self_scored_outcomes.jsonl.gz",
    "logs/results_20261020/legacy_self_match_scored_outcomes.jsonl.gz",
    "provenance/results_20261020/completed_experiments.json",
    "provenance/v1.10.1/publication_checks.json",
]


def main() -> int:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("outputs/_remote/data")
    ok = 0
    for f in FILES:
        try:
            info = get_file(f, REF, out)
            ok += 1
            print(f"ok {info['size']:>9}  {f}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {f}: {str(exc)[:150]}")
    print(f"{ok}/{len(FILES)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
