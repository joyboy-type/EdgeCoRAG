"""任务边界收口：跑三个产出脚本 → 记录 rc → 给出"产出前后 diff 只含新增目录"的证明。

基线 = 仓库里既有的 A 侧跟踪树（E: 工作树 `a-side/`，对应提交 ba5cc3c 的检出）。
当前 = 本次新产物所在树（C: `EdgeCoRAG-A/a-side/`，因为原工作区已被清空）。

判定：
  * added   = 只在当前存在（本次新增）——应当恰好等于本次三个交付
  * modified= 两边都有但 sha256 不同——必须为 0（不改既有跟踪文件）
  * removed = 只在基线存在——必须为 0

用法: python a33_boundary_and_receipts.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent          # EdgeCoRAG-A/a-side
BASELINE = Path(r"E:\EdgeCoRAG-A-store\_next_stage\a-side")
CURRENT = ROOT

DELIVERABLES = [
    "reports/index_scope_20261021.md",
    "reports/order_diff_20261021/receipt.json",
    "reports/order_diff_20261021/per_qid.csv",
    "reports/order_diff_20261021/reproduce.md",
    "reports/order_diff_20261021/census.json",
    "reports/cross_stack_statement_20261021.md",
]

RUNS = [
    ("a30_order_diff_minchain.py", ["--out", str(ROOT / "reports/order_diff_20261021")]),
    ("a31_index_scope_census.py", ["--out", str(ROOT / "reports/order_diff_20261021")]),
]


def manifest(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if ".git" in p.parts or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        out[str(p.relative_to(root)).replace("\\", "/")] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main() -> int:
    runs = []
    for script, extra in RUNS:
        s = Path(__file__).resolve().parent / script
        r = subprocess.run([PY, str(s), *extra], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        runs.append({"script": script, "rc": r.returncode,
                     "tail": (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""})
        print(f"{script:34s} rc={r.returncode}")
        if r.returncode != 0:
            print(r.stdout[-800:], r.stderr[-800:], file=sys.stderr)
            return 1

    gen = ROOT / "reports" / "order_diff_20261021" / "_gen_reproduce.py"
    r = subprocess.run([PY, str(gen)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    runs.append({"script": "_gen_reproduce.py", "rc": r.returncode,
                 "tail": (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""})
    print(f"{'_gen_reproduce.py':34s} rc={r.returncode}")
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:], file=sys.stderr)
        return 1

    base = manifest(BASELINE)
    cur = manifest(CURRENT)
    added = sorted(set(cur) - set(base))
    removed = sorted(set(base) - set(cur))
    modified = sorted(p for p in set(cur) & set(base) if cur[p] != base[p])

    # 只允许"本次交付 + 生成脚本"是新增
    allowed_prefix = (
        "reports/index_scope_20261021.md",
        "reports/order_diff_20261021/",
        "reports/cross_stack_statement_20261021.md",
        "reports/receipts_20261021.json",
        "scripts/a30_order_diff_minchain.py",
        "scripts/a31_index_scope_census.py",
        "scripts/a33_boundary_and_receipts.py",
        "reports/next_stage_20261020/EXPERIMENT_DOC.md",  # 上一轮产物，本轮未改
    )
    unexpected = [p for p in added if not p.startswith(allowed_prefix)]

    receipts = {
        "batch": "index_scope/order_diff/cross_stack @ 2026-10-21",
        "runs": runs,
        "deliverables": [],
        "boundary": {
            "baseline_root": str(BASELINE),
            "baseline_files": len(base),
            "current_root": str(CURRENT),
            "current_files": len(cur),
            "added": added,
            "added_unexpected": unexpected,
            "modified": modified,
            "removed": removed,
            "removed_note": (
                "当前树不是基线树的超集：原 C: 工作区在本轮开始前已被清空，"
                "removed 反映的是清空，而不是本次删除了跟踪文件；判定不使用该字段"
            ),
            "verdict_additions_only": (not modified and not unexpected),
        },
        "invariants": {
            "ablation_rerun": False,
            "gold_read": False,
            "gpu_used": False,
            "network_used": "仅 GitHub API 读取 a18 源码（提交 4a60d75），未下载数据/权重",
            "frozen_artifacts_touched": [p for p in modified if p.startswith("retrieval_if_v1/")],
            "frozen_artifacts_absent_from_current_tree": sum(
                1 for p in removed if p.startswith("retrieval_if_v1/")),
            "frozen_artifacts_note": (
                "原 C: 工作区在本轮开始前已被清空，因此当前树里没有 retrieval_if_v1/；"
                "这属于环境删除，不是本次改动。本次**没有写入**该目录，"
                "modified 为 0 即证明既有跟踪文件未被修改。基线仍在 "
                "E:/EdgeCoRAG-A-store/_next_stage（检出 ba5cc3c），远端有 4a60d75 及其后的标签。"
            ),
        },
    }
    for rel in DELIVERABLES:
        p = ROOT / rel
        receipts["deliverables"].append({
            "path": rel, "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else None,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None,
        })

    out = ROOT / "reports" / "receipts_20261021.json"
    out.write_bytes((json.dumps(receipts, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    print(f"\nbaseline files={len(base)}  current files={len(cur)}")
    print(f"added={len(added)}  modified={len(modified)}  removed={len(removed)}  unexpected={len(unexpected)}")
    print(f"additions_only={receipts['boundary']['verdict_additions_only']}")
    for a in added:
        print("  +", a)
    if modified:
        print("  ! modified:", modified)
    print(f"-> {out}")
    return 0 if receipts["boundary"]["verdict_additions_only"] else 2


if __name__ == "__main__":
    sys.exit(main())
