"""三轮键表求交（raw → q95 → l1b），顺序不许跳。

规则（写死）：
  1) 先比 sha256_raw × sha256_raw；交集 > 0 即"内容重合（口径 raw）"
  2) 否则比 sha256_q95 × sha256_q95；交集 > 0 即"内容重合（口径 q95）"
  3) 前两轮都为 0 才比 l1b × l1b；交集 > 0 即"内容重合（口径 l1b，字节基线不同、解码一致）"
  4) 三轮都为 0 才允许写"内容级无重合"，并给出 10 个 l1b 对不上的样例

每轮输出：交集键数、双方独有键数、一对一匹配数、歧义键数（一键对多 sha，单列，不擅自择一）。

用法：
  python intersect_identity_keys.py --a A.csv --b B.csv --out result.json
  python intersect_identity_keys.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

COLS = ["sha256_raw", "sha256_q95", "l1b"]
PASS_NAMES = {"sha256_raw": "raw", "sha256_q95": "q95", "l1b": "l1b"}


def load(p: Path) -> list[dict]:
    rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
    if rows:
        missing = [c for c in COLS if c not in rows[0]]
        if missing:
            raise SystemExit(f"{p} 缺列: {missing}")
    return rows


def index(rows: list[dict], col: str) -> tuple[dict[str, set[str]], int]:
    """key -> {sha256_raw}，并返回该表内重复 (key,sha) 行数。"""
    m: dict[str, set[str]] = {}
    dup_rows = 0
    seen: set[tuple[str, str]] = set()
    for r in rows:
        k, s = r[col].strip(), r["sha256_raw"].strip()
        if (k, s) in seen:
            dup_rows += 1
            continue
        seen.add((k, s))
        m.setdefault(k, set()).add(s)
    return m, dup_rows


def one_pass(a_rows: list[dict], b_rows: list[dict], col: str) -> dict:
    A, dupA = index(a_rows, col)
    B, dupB = index(b_rows, col)
    common = set(A) & set(B)
    one_to_one = sum(1 for k in common if len(A[k]) == 1 and len(B[k]) == 1)
    amb = sorted(k for k in common if len(A[k]) > 1 or len(B[k]) > 1)
    return {
        "pass": PASS_NAMES[col],
        "column": col,
        "a_rows": len(a_rows), "b_rows": len(b_rows),
        "a_unique_keys": len(A), "b_unique_keys": len(B),
        "common_keys": len(common),
        "a_only_keys": len(A) - len(common),
        "b_only_keys": len(B) - len(common),
        "one_to_one": one_to_one,
        "ambiguous_keys": len(amb),
        "ambiguous_examples": [{"key": k, "a_shas": sorted(A[k]), "b_shas": sorted(B[k])}
                               for k in amb[:5]],
        "duplicate_rows_a": dupA, "duplicate_rows_b": dupB,
        "empty_side": ("a" if not A else ("b" if not B else None)),
    }


def intersect(a_rows: list[dict], b_rows: list[dict]) -> dict:
    passes = []
    verdict = None
    for col in COLS:  # 顺序固定：raw → q95 → l1b
        r = one_pass(a_rows, b_rows, col)
        passes.append(r)
        if r["common_keys"] > 0:
            if col == "sha256_raw":
                verdict = {"overlap": True, "basis": "raw",
                           "sentence": f"{r['b_rows']} 中 {r['common_keys']} 张与本研究语料重合（口径：raw）"}
            elif col == "sha256_q95":
                verdict = {"overlap": True, "basis": "q95",
                           "sentence": f"{r['b_rows']} 中 {r['common_keys']} 张与本研究语料重合（口径：q95）"}
            else:
                verdict = {"overlap": True, "basis": "l1b",
                           "sentence": (f"{r['b_rows']} 中 {r['common_keys']} 张与本研究语料重合"
                                        f"（口径：l1b；字节基线不同、解码一致）")}
            break
    if verdict is None:
        verdict = {"overlap": False, "basis": None,
                   "sentence": "内容级无重合（口径：raw / q95 / l1b 三轮交集均为 0）",
                   "samples_to_review": passes[-1]["ambiguous_examples"][:10]}
    return {"passes": passes, "verdict": verdict,
            "order_rule": "raw → q95 → l1b（不许跳）"}


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def self_test() -> int:
    checks = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(cond), "detail": detail})

    tmp = Path(tempfile.mkdtemp(prefix="keys_test_"))
    # 合成：A 三行，B 三行；raw 命中 1；q95 命中 1（raw 不同）；l1b 命中 1（raw/q95 都不同）
    A = [
        {"sha256_raw": "rawA1", "sha256_q95": "q95A1", "l1b": "l1bA1"},
        {"sha256_raw": "rawA2", "sha256_q95": "q95A2", "l1b": "l1bA2"},
        {"sha256_raw": "rawA3", "sha256_q95": "q95A3", "l1b": "same_l1b"},
    ]
    B = [
        {"sha256_raw": "rawA1", "sha256_q95": "q95B1", "l1b": "l1bB1"},
        {"sha256_raw": "rawB2", "sha256_q95": "q95A2", "l1b": "l1bB2"},
        {"sha256_raw": "rawB3", "sha256_q95": "q95B3", "l1b": "same_l1b"},
    ]

    # 1) 命中：raw 交集 1（顺序规则应停在 raw）
    r = intersect(A, B)
    ok("raw_hit_stops_at_raw", r["verdict"]["basis"] == "raw" and r["passes"][0]["common_keys"] == 1,
       str(r["verdict"]))
    ok("raw_pass_counts", r["passes"][0]["one_to_one"] == 1 and r["passes"][0]["a_only_keys"] == 2
       and r["passes"][0]["b_only_keys"] == 2, "")

    # 2) 不命中 → 三轮全 0
    A2 = [{"sha256_raw": "x1", "sha256_q95": "y1", "l1b": "z1"}]
    B2 = [{"sha256_raw": "x2", "sha256_q95": "y2", "l1b": "z2"}]
    r2 = intersect(A2, B2)
    ok("all_miss", r2["verdict"]["overlap"] is False and all(p["common_keys"] == 0 for p in r2["passes"]),
       str(r2["verdict"]["sentence"]))

    # 3) 一对多歧义（同一 l1b 在 B 侧对两个 raw）
    A3 = [{"sha256_raw": "a", "sha256_q95": "q", "l1b": "L"}]
    B3 = [{"sha256_raw": "b1", "sha256_q95": "q1", "l1b": "L"},
          {"sha256_raw": "b2", "sha256_q95": "q2", "l1b": "L"}]
    r3 = intersect(A3, B3)
    ok("ambiguous_counted", r3["passes"][2]["ambiguous_keys"] == 1
       and r3["passes"][2]["one_to_one"] == 0, str(r3["passes"][2]["ambiguous_examples"]))

    # 4) 空表
    r4 = intersect([], B3)
    ok("empty_table", r4["passes"][0]["empty_side"] == "a"
       and all(p["common_keys"] == 0 for p in r4["passes"]), "")

    # 5) 重复键（同 key 同 sha 出现两次 → 计 duplicate_rows，不重复计键）
    A5 = [{"sha256_raw": "d", "sha256_q95": "dq", "l1b": "dl"},
          {"sha256_raw": "d", "sha256_q95": "dq", "l1b": "dl"}]
    B5 = [{"sha256_raw": "d", "sha256_q95": "dq", "l1b": "dl"}]
    r5 = intersect(A5, B5)
    ok("duplicate_rows_flagged", r5["passes"][0]["duplicate_rows_a"] == 1
       and r5["passes"][0]["common_keys"] == 1, "")

    # 真实文件往返（用合成数据写盘再读，验证列校验）
    pa, pb = tmp / "a.csv", tmp / "b.csv"
    _write(pa, A)
    _write(pb, B)
    r6 = intersect(load(pa), load(pb))
    ok("csv_roundtrip", r6["verdict"]["basis"] == "raw", "")

    passed = sum(c["pass"] for c in checks)
    print(json.dumps({"checks": checks, "passed": f"{passed}/{len(checks)}"}, ensure_ascii=False, indent=2))
    return 0 if passed == len(checks) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not (args.a and args.b):
        ap.error("必须给 --a 与 --b（或 --self-test）")
    res = intersect(load(Path(args.a)), load(Path(args.b)))
    text = json.dumps(res, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_bytes(text.encode())
        print(f"-> {args.out}")
    print(res["verdict"]["sentence"])
    for p in res["passes"]:
        print(f"  {p['pass']:4s} common={p['common_keys']:6d} 1:1={p['one_to_one']:6d} "
              f"amb={p['ambiguous_keys']:3d} a_only={p['a_only_keys']:6d} b_only={p['b_only_keys']:6d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
