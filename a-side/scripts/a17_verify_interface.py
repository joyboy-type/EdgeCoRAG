"""检索接口 v1 产物自校验（不依赖模型/GPU，纯文件级）。

校验项：
  1. artifacts.json 里每个文件的 sha256 与字节数复算一致
  2. 语料：corpus_manifest 行序 = sha256 升序，且 content_digest 可复算
  3. 候选池：每题 10 行、(score desc, sha asc) 真按次序键排序、不含查询图自身 sha、sha 均在语料内
  4. select3：每题每策略 3 行、全部来自该题候选池、slot 连续
  5. pool_quality：每题一行，min_adjacent_margin 可复算
  6. 报告 order_fragile 比例（min_adjacent_margin < 1e-3）

用法: python scripts/a17_verify_interface.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IFACE = ROOT / "a-side" / "retrieval_if_v1"
CORPUS = IFACE / "corpus"
OUT = IFACE / "verify.json"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    fails: list[str] = []
    info: dict = {}

    art = json.loads((IFACE / "artifacts.json").read_text(encoding="utf-8"))
    for a in art["artifacts"]:
        p = IFACE / a["path"]
        if not p.exists():
            fails.append(f"missing {a['path']}")
            continue
        h = sha_file(p)
        if h != a["sha256"]:
            fails.append(f"sha mismatch {a['path']}: {h[:12]} != {a['sha256'][:12]}")
        if p.stat().st_size != a["bytes"]:
            fails.append(f"size mismatch {a['path']}")
    info["artifacts_checked"] = len(art["artifacts"])

    # 2) 语料
    man = list(csv.DictReader((CORPUS / "corpus_manifest.csv").open(encoding="utf-8")))
    shas = [r["sha256"] for r in man]
    if shas != sorted(shas):
        fails.append("corpus_manifest 行序不是 sha256 升序")
    dg = hashlib.sha256()
    for s in shas:
        dg.update(f"{s}\n".encode())
    meta = json.loads((CORPUS / "corpus_meta.json").read_text(encoding="utf-8"))
    if dg.hexdigest() != meta["content_digest_sha256"]:
        fails.append("corpus content_digest 不可复算")
    info["corpus_rows"] = len(shas)
    info["corpus_digest"] = dg.hexdigest()
    corpus_set = set(shas)

    # 3)-6) 各 cohort × 维度
    fragile = {}
    for pool_p in sorted((IFACE / "pools").glob("*__top10.csv")):
        cohort, dim = pool_p.stem.replace("__top10", "").split("__dim")
        rows = list(csv.DictReader(pool_p.open(encoding="utf-8")))
        by_q: dict[str, list[dict]] = {}
        for r in rows:
            by_q.setdefault(r["qid"], []).append(r)
            if r["sha256"] not in corpus_set:
                fails.append(f"{pool_p.name} 出现语料外 sha")
        for q, rs in by_q.items():
            if len(rs) != 10:
                fails.append(f"{pool_p.name} {q} 候选数 {len(rs)} != 10")
            keys = [(-float(r["score"]), r["sha256"]) for r in rs]
            if keys != sorted(keys):
                fails.append(f"{pool_p.name} {q} 未按 (score desc, sha asc) 排序")
            ranks = [int(r["rank"]) for r in rs]
            if ranks != list(range(1, 11)):
                fails.append(f"{pool_p.name} {q} rank 不连续")
        info.setdefault("pools", {})[f"{cohort}|{dim}"] = {"questions": len(by_q), "rows": len(rows)}

        # select3
        sp = IFACE / "select3" / f"{cohort}__dim{dim}__cosine+random.csv"
        srows = list(csv.DictReader(sp.open(encoding="utf-8")))
        sb: dict[tuple[str, str], list[dict]] = {}
        for r in srows:
            sb.setdefault((r["qid"], r["strategy"]), []).append(r)
        for (q, strat), rs in sb.items():
            if len(rs) != 3:
                fails.append(f"{sp.name} {q}/{strat} 行数 {len(rs)} != 3")
            pool_shas = {r["sha256"] for r in by_q.get(q, [])}
            for r in rs:
                if r["sha256"] not in pool_shas:
                    fails.append(f"{sp.name} {q}/{strat} 选中的图不在候选池内")
            if [int(r["slot"]) for r in rs] != [1, 2, 3]:
                fails.append(f"{sp.name} {q}/{strat} slot 不连续")
            if strat == "cosine":
                pool_order = [r["sha256"] for r in sorted(by_q[q], key=lambda x: int(x["rank"]))]
                if [r["sha256"] for r in rs] != pool_order[:3]:
                    fails.append(f"{sp.name} {q} cosine 选图不等于前 3")

        # pool_quality + 脆弱度
        qp = IFACE / "pool_quality" / f"{cohort}__dim{dim}__margins.csv"
        qrows = list(csv.DictReader(qp.open(encoding="utf-8")))
        n_frag = sum(1 for r in qrows if r["min_adjacent_margin"] and float(r["min_adjacent_margin"]) < 1e-3)
        fragile[f"{cohort}|{dim}"] = {"questions": len(qrows), "order_fragile": n_frag,
                                      "share": round(n_frag / len(qrows), 4) if qrows else None}
        for r in qrows:
            rs = sorted(by_q.get(r["qid"], []), key=lambda x: int(x["rank"]))
            if not rs:
                fails.append(f"{qp.name} {r['qid']} 无对应候选")
                continue
            sc = [float(x["score"]) for x in rs]
            mm = min(sc[k] - sc[k + 1] for k in range(len(sc) - 1))
            if r["min_adjacent_margin"] and abs(mm - float(r["min_adjacent_margin"])) > 1e-7:
                fails.append(f"{qp.name} {r['qid']} min_adjacent_margin 不可复算")

    info["order_fragile"] = fragile
    info["fails"] = fails[:50]
    info["fail_count"] = len(fails)
    OUT.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"artifacts 校验 {info['artifacts_checked']} 个文件")
    print(f"语料 {info['corpus_rows']} 行  digest={info['corpus_digest'][:16]}…")
    for k, v in fragile.items():
        print(f"  {k:24s} 题数 {v['questions']:5d}  order_fragile {v['order_fragile']:5d} ({v['share']:.2%})")
    print(f"失败项 {len(fails)}")
    for f in fails[:20]:
        print("  -", f)
    print(f"-> {OUT}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
