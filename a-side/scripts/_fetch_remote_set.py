"""批量下载远端 ref 的关键文件到本地只读快照目录（UTF-8 路径安全）。

只读取远端内容，用于分析；不触碰本地 git 仓库。

用法: python scripts/_fetch_remote_set.py [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_api import get_file  # noqa: E402

REF = "2975d9cae550339628681dc397d80ed9ab6e0158"

FILES = [
    "reports/EXPERIMENT_RESULTS.md",
    "logs/results_20261020/README.md",
    "provenance/results_20261020/completed_experiments.json",
    "provenance/results_20261020/e2e_smoke_public_receipt.json",
    "provenance/results_20261020/public_manifest.json",
    "reports/next_stage_20261019/EdgeCoRAG_同机端到端smoke实测_20261020.md",
    "reports/next_stage_20261019/同机端到端_smoke检索一致性_20261020.csv",
    "reports/next_stage_20261019/同机端到端_smoke汇总_20261020.csv",
    "reports/next_stage_20261019/同机端到端_smoke逐次测量_20261020.csv",
    "reports/next_stage_20261019/EdgeCoRAG_无自匹配协议复核结果_20261019.md",
    "reports/next_stage_20261019/EdgeCoRAG_无自匹配检索维度消融_20261019.md",
    "reports/next_stage_20261019/无自匹配检索_维度消融.csv",
    "reports/next_stage_20261019/无自匹配协议_准确率汇总.csv",
    "reports/next_stage_20261019/无自匹配协议_时延与显存.csv",
    "reports/next_stage_20261019/无自匹配协议_精确证据覆盖.csv",
    "reports/next_stage_20261019/EdgeCoRAG_图像相关性与证据变化分析_20261020.md",
    "reports/next_stage_20261019/证据变化_相同输入核对_20261020.csv",
    "reports/next_stage_20261017/next_experiment_decision.md",
    "reports/next_stage_20261017/B_return.md",
    "reports/next_stage_20261017/B_TASKS.md",
    "reports/next_stage_20261017/B_mmdocrag_scoring_contract.md",
    "reports/next_stage_20261017/B_paper_table_audit.md",
    "reports/Next_steps.md",
    "reports/Requirements.md",
    "reports/Delivery.md",
    "README.md",
]


def main() -> int:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("outputs/_remote/snapshot")
    ok, bad = 0, []
    for f in FILES:
        try:
            info = get_file(f, REF, out)
            ok += 1
            print(f"ok {info['size']:>8}  {f}")
        except Exception as exc:  # noqa: BLE001
            bad.append((f, str(exc)[:120]))
            print(f"FAIL        {f}: {str(exc)[:120]}")
    print(f"\ndownloaded {ok}/{len(FILES)} -> {out}")
    for f, e in bad:
        print(f"  missing: {f} ({e})")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
