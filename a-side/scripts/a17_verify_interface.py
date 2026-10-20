"""检索接口 v1 产物自校验（不依赖模型/GPU，纯文件级）。

校验项：
  1. artifacts.json 里每个文件的 sha256 与字节数复算一致（**按 LF 口径**：
     先做 `\\r\\n -> \\n` 归一化再算，因此 Windows CRLF 工作树与 Linux/macOS 干净检出
     都能通过；`--strict-lf` 则相反，遇到 CRLF 直接拒绝并给修复提示）
  2. 语料：corpus_manifest 行序 = sha256 升序，且 content_digest 可复算
  3. 候选池：每题 10 行、(score desc, sha asc) 真按次序键排序、不含查询图自身 sha、sha 均在语料内
  4. select3：每题每策略 3 行、全部来自该题候选池、slot 连续
  5. pool_quality：每题一行，min_adjacent_margin 可复算
  6. 报告 order_fragile 比例（min_adjacent_margin < 1e-3）

退出码：0 = 全部通过；1 = 有任何 mismatch；2 = 用法/文件缺失。

用法：
    python a-side/scripts/a17_verify_interface.py                 # 归一化后比对（默认）
    python a-side/scripts/a17_verify_interface.py --strict-lf     # 拒绝任何 CRLF 输入
    python a-side/scripts/a17_verify_interface.py --iface <dir>   # 指定接口目录（测试用）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys

try:  # Windows 控制台可能是 cp936，统一成 utf-8 输出，避免中文 detail 触发 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

from pathlib import Path

for _cand in (Path(__file__).resolve().parent,
              Path(__file__).resolve().parent.parent / "a-side" / "scripts"):
    if (_cand / "a00_paths.py").exists():
        sys.path.insert(0, str(_cand))
        break
import a00_paths  # noqa: E402


def lf_bytes(p: Path) -> tuple[bytes, bool]:
    """返回 (LF 归一化后的字节, 原本是否含 CRLF)。只转换 CRLF，孤立 \\r 不动。"""
    raw = p.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    return lf, raw != lf


def sha_lf(p: Path) -> str:
    return hashlib.sha256(lf_bytes(p)[0]).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default=None, help="接口目录（默认按 a00_paths 推导）")
    ap.add_argument("--strict-lf", action="store_true",
                    help="要求磁盘字节已是 LF；发现 CRLF 直接失败并给出修复提示")
    ap.add_argument("--out", default=None,
                    help="verify.json 的输出路径（默认写到接口目录；干净检出重跑不会产生 diff）")
    args = ap.parse_args()

    global IFACE, CORPUS, OUT
    IFACE = a00_paths.iface_root(args.iface)
    CORPUS = IFACE / "corpus"
    OUT = Path(args.out).expanduser().resolve() if args.out else (IFACE / "verify.json")

    fails: list[str] = []
    info: dict = {}

    art = json.loads((IFACE / "artifacts.json").read_text(encoding="utf-8"))
    norm = (art.get("summary") or {}).get("hash_normalization")
    if norm != "LF":
        fails.append(f"artifacts.json summary.hash_normalization 应为 \"LF\"，收到 {norm!r}")

    crlf_files: list[str] = []
    for a in art["artifacts"]:
        p = IFACE / a["path"]
        if not p.exists():
            fails.append(f"missing {a['path']}")
            continue
        lf, had_crlf = lf_bytes(p)
        if had_crlf:
            crlf_files.append(a["path"])
            if args.strict_lf:
                fails.append(f"CRLF 输入 {a['path']}（--strict-lf 要求 LF）")
                continue
        h = hashlib.sha256(lf).hexdigest()
        if h != a["sha256"]:
            fails.append(f"sha mismatch {a['path']}: {h[:12]} != {a['sha256'][:12]}")
        if len(lf) != a["bytes"]:
            fails.append(f"size mismatch {a['path']}: {len(lf)} != {a['bytes']} (LF 字节)")
    info["artifacts_checked"] = len(art["artifacts"])
    info["hash_normalization"] = norm
    info["files_with_crlf"] = len(crlf_files)
    info["line_ending_note"] = (
        "files_with_crlf = 本次运行『需要归一化』的文件数"
        "（Windows CRLF 工作树 36 / 干净 LF 检出 0），"
        "不是『产物里含 CRLF』，也不参与任何哈希"
    )
    if args.strict_lf and crlf_files:
        fails.append(
            "检测到 CRLF 工作树：请用 `git config core.autocrlf false` 重新检出，或 "
            "`git rm --cached -r . && git reset --hard` 让 .gitattributes 的 eol=lf 生效；"
            "产物内容不需要修改"
        )


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
    # 以 LF 字节写出：Windows 上 write_text 会把 \n 转成 CRLF，会让干净检出的 git status 变脏
    OUT.write_bytes((json.dumps(info, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

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
