"""把冻结接口的候选池/select3 清单物化成 B 可直接消费的证据包（与既有 packages/* 同 schema）。

输入：
  a-side/retrieval_if_v1/pools/<cohort>__dim<D>__top10.csv      （候选池与分数）
  a-side/retrieval_if_v1/select3/<cohort>__dim<D>__cosine+random.csv
  （utility 策略由 B 回传分数后，用相同的 --scores 参数物化）
  E:\\EdgeCoRAG-A-store\\corpus_v1                          （唯一内容图像，按 sha 定位）

输出（默认 a-side/retrieval_if_v1/packages/<cohort>_dim<D>_<strategy>/）：
  images/<raw_id>/q_<raw>.jpg                 查询图（JPEG q95 字节，与 sha 同源）
  images/<raw_id>/eg2_sel_<raw>_<slot>.jpg    选中的 3 张证据
  evidence_index.csv                          evidence_id,raw_id,qid,role,rank,path,sha256,w,h
  evidence_list.jsonl                         每题的输入结构（query + 3 证据，顺序固定）
  package_meta.json                           协议版本、pool_id、维度、策略、内容摘要
  verify.json                                 逐文件 sha 复算结果

边界：
  * 只物化已冻结清单里的内容；不重新排序、不重新选择。
  * gold/答案不进入本包任何字段（gold 仅用于评分与 Oracle）。
  * 图片按 sha 从 corpus_v1 取，物化时逐文件复算 sha，不一致即失败。

用法:
    python scripts/a15_materialize_packets.py --cohort dev_150 --dim 768 --strategy cosine
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IFACE = ROOT / "a-side" / "retrieval_if_v1"
CORPUS = Path(r"E:\EdgeCoRAG-A-store\corpus_v1")
PROTOCOL = "a-side/retrieval-interface-v1"


def read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--dim", type=int, required=True)
    ap.add_argument("--strategy", required=True, choices=["cosine", "random", "utility"])
    ap.add_argument("--scores", type=Path, default=None,
                    help="utility 策略用：B 回传的 (qid,sha256,score) CSV")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    pool_p = IFACE / "pools" / f"{args.cohort}__dim{args.dim}__top10.csv"
    pool = read_csv(pool_p)
    if not pool:
        print(f"空候选池: {pool_p}", file=sys.stderr)
        return 1

    manifest = (CORPUS / "corpus_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]
    meta_of = {}
    for r in manifest:
        f = r.split(",")
        meta_of[f[1]] = {"bytes": int(f[2]), "w": int(f[3]), "h": int(f[4])}

    by_q: dict[str, list[dict]] = {}
    for row in pool:
        by_q.setdefault(row["qid"], []).append(row)
    order = sorted(by_q, key=lambda s: int(s.split(":")[1]))

    # ---------------- 选定 3 张
    if args.strategy in ("cosine", "random"):
        sel_p = IFACE / "select3" / f"{args.cohort}__dim{args.dim}__cosine+random.csv"
        sel_rows = [r for r in read_csv(sel_p) if r["strategy"] == args.strategy]
        sel = {}
        for r in sel_rows:
            sel.setdefault(r["qid"], []).append(r)
        for q in sel:
            sel[q].sort(key=lambda r: int(r["slot"]))
    elif args.strategy == "utility":
        if args.scores is None:
            print("utility 策略需要 --scores（B 回传的候选效用分数）", file=sys.stderr)
            return 2
        sc = {}
        for r in read_csv(args.scores):
            sc[(r["qid"], r["sha256"])] = float(r["score"])
        sel = {}
        missing = 0
        for q, rows in by_q.items():
            scored = []
            for r in rows:
                k = (q, r["sha256"])
                if k not in sc:
                    missing += 1
                    continue
                scored.append((sc[k], r["sha256"], r))
            if missing:
                continue
            scored.sort(key=lambda t: (-t[0], t[1]))
            sel[q] = [{"sha256": s, "slot": i + 1, "score": f"{v:.9f}"} for i, (v, s, _r) in enumerate(scored[:3])]
        if missing:
            print(f"utility 分数缺失 {missing} 个候选，拒绝物化", file=sys.stderr)
            return 3

    out = args.out or (IFACE / "packages" / f"{args.cohort}_dim{args.dim}_{args.strategy}")
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True, exist_ok=True)

    idx_rows, list_rows, verify_rows = [], [], []
    for q in order:
        raw = q.split(":")[1]
        qsha = by_q[q][0].get("query_sha256") or ""
        if not qsha:
            qsha = next(r["query_sha256"] for r in read_csv(IFACE / "pool_quality" / f"{args.cohort}__dim{args.dim}__margins.csv") if r["qid"] == q)
        picks = sel.get(q, [])
        if len(picks) != 3:
            print(f"{q} 选中数 != 3，拒绝物化", file=sys.stderr)
            return 4
        sub = out / "images" / raw
        sub.mkdir(parents=True, exist_ok=True)

        def put(sha: str, stem: str, role: str, rank) -> dict:
            src = CORPUS / "images" / sha[:2] / f"{sha}.jpg"
            dst = sub / f"{stem}.jpg"
            shutil.copyfile(src, dst)
            got = hashlib.sha256(dst.read_bytes()).hexdigest()
            verify_rows.append({"qid": q, "path": str(dst.relative_to(out)).replace("\\", "/"),
                                "expected": sha, "actual": got, "ok": got == sha})
            m = meta_of.get(sha, {})
            return {"evidence_id": f"{q}#{role}{'' if rank is None else rank}",
                    "role": role, "rank": rank,
                    "path": str(dst.relative_to(out)).replace("\\", "/"),
                    "sha256": sha, "w": m.get("w", ""), "h": m.get("h", "")}

        ev_q = put(qsha, f"q_{raw}", "query", None)
        evs = [put(p["sha256"], f"eg2_sel_{raw}_{p['slot']}", "eg2_selected", int(p["slot"])) for p in picks]
        for e in [ev_q] + evs:
            idx_rows.append({"evidence_id": e["evidence_id"], "raw_id": raw, "qid": q,
                             "role": e["role"], "rank": "" if e["rank"] is None else e["rank"],
                             "path": e["path"], "sha256": e["sha256"], "w": e["w"], "h": e["h"]})
        list_rows.append({"qid": q, "raw_id": raw, "pool_id": pool[0]["pool_id"],
                          "retriever_id": pool[0]["retriever_id"], "embed_dim": args.dim,
                          "selection_strategy": args.strategy,
                          "query": ev_q, "evidence": evs})

    with (out / "evidence_index.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["evidence_id", "raw_id", "qid", "role", "rank",
                                          "path", "sha256", "w", "h"])
        w.writeheader()
        w.writerows(idx_rows)
    with (out / "evidence_list.jsonl").open("w", encoding="utf-8") as f:
        for r in list_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dg = hashlib.sha256()
    for r in idx_rows:
        dg.update(f"{r['path']}\x00{r['sha256']}\n".encode())
    meta = {
        "artifact_kind": "evidence_package",
        "protocol": PROTOCOL,
        "cohort": args.cohort,
        "embed_dim": args.dim,
        "selection_strategy": args.strategy,
        "pool_id": pool[0]["pool_id"],
        "retriever_id": pool[0]["retriever_id"],
        "questions": len(order),
        "images": len(idx_rows),
        "content_digest": dg.hexdigest(),
        "order_rule": "query first, then evidence slot 1..3（cosine/utility 为分数降序，random 为抽样后按分数序）",
        "gold_used": False,
        "notes": [
            "gold 只用于评分/Oracle，未进入本包任何字段",
            "候选身份为 JPEG q95 字节 sha256；物化时逐文件复算",
        ],
    }
    (out / "package_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    bad = [v for v in verify_rows if not v["ok"]]
    (out / "verify.json").write_text(
        json.dumps({"files": len(verify_rows), "mismatch": len(bad), "details": bad[:20]},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("cohort", "embed_dim", "selection_strategy",
                                           "questions", "images", "content_digest")}, ensure_ascii=False))
    print(f"sha 校验 {len(verify_rows)} 文件，不一致 {len(bad)} -> {out}")
    return 0 if not bad else 5


if __name__ == "__main__":
    sys.exit(main())
