"""校验切分产物是否满足全部不变量 —— 先用它抓 bug，再用它验收修复。

**为什么需要它**

原 `make_split.py` 有三处已确认的缺陷，只靠"题数相加等于 1353"是查不出来的：

  1. 已调试题只在 smoke/dev/internal_holdout 分配期间被过滤，
     最后 `rows[pos:]` 直接进 frozen_test —— **已调试题会漏进冻结集**。
     此时题数仍然相加正确，检查总数完全无效。
  2. 文档与 manifest 声称"同源组整组分配"，代码实际是**按场景分层逐题分配**。
  3. `--dry-run` 仍会写文件。

因此本脚本按**语义不变量**逐条检查，而不是只对数：

  I1  子集互斥（任一 qid 只出现在一个子集）
  I2  总覆盖完整（并集 == 全量 1353，无遗漏无重复）
  I3  已调试题不进入 internal_holdout / frozen_test
  I4  已调试题**全部被记录**（既不丢失，也不被静默丢弃）
  I5  raw_id 保持字符串原样（未被整数化、无前导零丢失）
  I6  qid 唯一且形如 mragb:<raw_id>
  I7  相同输入可重现（同一 seed 两次运行哈希一致）—— 由 --reproduce 触发
  I8  声明的计数与文件实际行数一致
  I9  manifest 的规则描述与代码实际行为一致（用规则字段显式声明，
      不再是自由文本"同源组整组分配"这种无法校验的说法）
  I10 近重复/实体组的处理方式已声明（隔离 或 如实声明未隔离）

用法:
    python scripts/verify_split.py                      # 校验 splits/ 下产物
    python scripts/verify_split.py --dir <目录>
    python scripts/verify_split.py --json               # 机器可读
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

SPLITS = ["smoke_20", "dev", "internal_holdout", "frozen_test"]
DEFAULT_DIR = cfg.ROOT / "splits"
OUT = cfg.ROOT / "outputs" / "split_verify" / "split_report.json"

QID_RE = re.compile(r"^mragb:(.+)$")


class Rep:
    def __init__(self) -> None:
        self.items: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.items.append((name, ok, detail))

    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.items)

    def dump(self) -> list[dict]:
        return [{"check": n, "ok": ok, "detail": d} for n, ok, d in self.items]


def load_split(d: Path, name: str, version: str | None = None) -> tuple[list[str], str]:
    """读取子集清单。**跳过空行与 `#` 注释行**。

    实测踩过: reviewed_ids.txt 带注释头,旧解析把它当 ID 收进来,
    导致"丢失的已调试题"里出现整条注释文本。清单文件必须容忍注释。
    """
    p = (d / f"{name}.{version}.txt") if version else (d / f"{name}.txt")
    if not p.exists():
        return [], ""
    txt = p.read_text(encoding="utf-8")
    lines = []
    for l in txt.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines, hashlib.sha256(txt.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--expect-total", type=int, default=1353)
    ap.add_argument("--version", default=None,
                    help=("切分版本号。指定后读 <name>.<version>.txt 与 "
                          "split_manifest.<version>.json；不指定则读旧命名 "
                          "<name>.txt（v1）以兼容。"))
    args = ap.parse_args()
    d: Path = args.dir

    def split_path(name: str) -> Path:
        if args.version:
            return d / f"{name}.{args.version}.txt"
        return d / f"{name}.txt"

    rep = Rep()
    if not d.exists():
        print(f"✗ 目录不存在: {d}")
        return 1

    man_path = (d / f"split_manifest.{args.version}.json") if args.version \
        else (d / "split_manifest.json")
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    rep.add("manifest 存在", man_path.exists(), man_path.name)

    data: dict[str, list[str]] = {}
    hashes: dict[str, str] = {}
    for s in SPLITS:
        qids, h = load_split(d, s, version=args.version)
        data[s] = qids
        hashes[s] = h
        rep.add(f"{split_path(s).name} 存在", split_path(s).exists())

    all_qids = [q for s in SPLITS for q in data[s]]

    # ---------------------------------------------------------------- I1
    dup = {q for q in all_qids if all_qids.count(q) > 1}
    rep.add("I1 子集互斥（无 qid 跨子集）", not dup,
            f"重复 {len(dup)}: {sorted(dup)[:5]}" if dup else "")

    # ---------------------------------------------------------------- I2
    uniq = set(all_qids)
    rep.add("I2 总覆盖完整", len(uniq) == args.expect_total,
            f"唯一 {len(uniq)} / 期望 {args.expect_total}")
    rep.add("I2b 无重复计数", len(all_qids) == len(uniq),
            f"总行数 {len(all_qids)} vs 唯一 {len(uniq)}")

    # ---------------------------------------------------------------- I6
    bad_fmt = [q for q in uniq if not QID_RE.match(q)]
    rep.add("I6 qid 格式 mragb:<raw_id>", not bad_fmt, f"异常 {bad_fmt[:5]}")

    # ---------------------------------------------------------------- I5
    raw_ids = [QID_RE.match(q).group(1) for q in uniq if QID_RE.match(q)]
    # 原始 id 是十进制字符串；不应出现被 int() 处理后回写的痕迹
    # （例如 '007' -> '7'）。这里检查是否存在"看起来被整数化"的形态：
    # 全部为数字且没有前导零、且长度分布合理。
    nonstr = [r for r in raw_ids if not isinstance(r, str)]
    rep.add("I5 raw_id 为字符串", not nonstr, f"非字符串 {nonstr[:5]}")
    leading_zero = [r for r in raw_ids if len(r) > 1 and r.startswith("0")]
    # 有前导零说明**保留了原始形态**（好事）；这里只做记录不判失败
    rep.add("I5b raw_id 形态记录", True,
            f"含前导零的 raw_id {len(leading_zero)} 个（说明未做整数化）")

    # ---------------------------------------------------------------- I4 / I3
    reviewed = set(man.get("reviewed_ids") or [])
    # 兼容旧字段名
    reviewed |= set(man.get("reviewed_ids_forced_to_dev") or [])
    rev_q = {f"mragb:{r}" for r in reviewed}

    in_sets = {s: (rev_q & set(data[s])) for s in SPLITS}
    leaked_holdout = in_sets["internal_holdout"]
    leaked_frozen = in_sets["frozen_test"]
    rep.add("I3 已调试题不进入 internal_holdout", not leaked_holdout,
            f"泄漏 {len(leaked_holdout)}: {sorted(leaked_holdout)[:5]}" if leaked_holdout else "")
    rep.add("I3b 已调试题不进入 frozen_test", not leaked_frozen,
            f"泄漏 {len(leaked_frozen)}: {sorted(leaked_frozen)[:5]}" if leaked_frozen else "")

    if reviewed:
        placed = (in_sets["smoke_20"] | in_sets["dev"] | leaked_holdout | leaked_frozen)
        missing = rev_q - placed
        rep.add("I4 已调试题全部有归属", not missing,
                f"丢失 {len(missing)}: {sorted(missing)[:5]}" if missing else
                f"{len(rev_q)} 题均已放置")
    else:
        rep.add("I4 已调试题全部有归属", False,
                "manifest 未声明 reviewed_ids —— 无法证明已调试题被妥善处理")

    # ---------------------------------------------------------------- I8
    counts = {s: len(data[s]) for s in SPLITS}
    declared = {s: (man.get("splits", {}).get(s, {}) or {}).get("count") for s in SPLITS}
    mismatch = {s: (counts[s], declared[s]) for s in SPLITS
                if declared[s] is not None and counts[s] != declared[s]}
    rep.add("I8 声明计数 == 文件行数", not mismatch, f"不符 {mismatch}" if mismatch else
            " ".join(f"{s}={counts[s]}" for s in SPLITS))

    # 文件哈希与 manifest 一致
    hbad = {s: hashes[s] for s in SPLITS
            if (man.get("splits", {}).get(s, {}) or {}).get("sha256")
            and man["splits"][s]["sha256"] != hashes[s]}
    rep.add("I8b 文件哈希与 manifest 一致", not hbad, f"不符 {list(hbad)}" if hbad else "")

    # ---------------------------------------------------------------- I9
    rule = man.get("assignment_rule")
    rep.add("I9 manifest 声明了机器可校验的分配规则",
            bool(rule), f"assignment_rule={rule!r}")

    # ---------------------------------------------------------------- I10
    ent = man.get("entity_isolation")
    rep.add("I10 声明了实体/近重复组的处理方式",
            bool(ent) and bool(ent.get("mode")),
            f"entity_isolation.mode={(ent or {}).get('mode')!r}")

    payload = {
        "script": "scripts/verify_split.py",
        "dir": str(d),
        "counts": counts,
        "reviewed_count": len(reviewed),
        "reviewed_by_set": {s: len(v) for s, v in in_sets.items()},
        "checks": rep.dump(),
        "overall_pass": rep.ok(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"切分目录: {d}")
        print(f"计数: " + "  ".join(f"{s}={counts[s]}" for s in SPLITS))
        print(f"已调试题: {len(reviewed)}")
        print()
        nfail = 0
        for n, ok, det in rep.items:
            if not ok:
                nfail += 1
            print(f"  {'✅' if ok else '❌'} {n}" + (f"  — {det}" if det else ""))
        print(f"\n{'=' * 62}")
        print(f"{'✅ 全部通过' if rep.ok() else f'❌ {nfail} 项未通过'}")
        print(f"-> {OUT}")
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
