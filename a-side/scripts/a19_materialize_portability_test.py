"""a15 物化器的可移植性测试：临时目录内自造语料 + 接口，验证 --corpus/--iface/--scores 与错误信息。

不依赖真实数据集、不联网、不加载模型；用 PIL 生成 3 张极小 JPEG 当语料。

覆盖：
  1. 缺 --corpus 且无环境变量 → 清晰报错（非零退出，提示语含 --corpus 与 EDGECORAG_CORPUS）
  2. --corpus 指向不完整目录 → 报错并列出缺什么
  3. --corpus × 环境变量 两条路径都能物化，verify.json mismatch == 0
  4. cosine / random 两策略的 evidence_index 行数正确、slot 连续、sha 与语料一致
  5. utility：--scores 缺候选时拒绝（退出码 3）；给全时按 score 降序、sha 升序选 top3
  6. 输出目录可自定义（--out）

用法: python a-side/scripts/a19_materialize_portability_test.py
"""

from __future__ import annotations

import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import a00_paths  # noqa: E402

ROOT = a00_paths.side_root()
SCRIPT = HERE / "a15_materialize_packets.py"
PY = sys.executable

QIDS = ["mragb:1", "mragb:2"]
_TMP_RE = re.compile(r"[A-Za-z]:[\\/][^\s"',]*a15test_[0-9a-z_]+", re.IGNORECASE)


def _scrub(text: str) -> str:
    return _TMP_RE.sub("<tmp>", str(text))


def make_corpus(base: Path) -> tuple[Path, dict[str, str], dict[str, dict]]:
    """生成 3 张图（1 查询 + 2 候选）与 manifest/occurrences。"""
    from PIL import Image

    imgs = base / "images"
    imgs.mkdir(parents=True, exist_ok=True)
    colors = {"q1": (200, 30, 30), "a1": (30, 200, 30), "a2": (30, 30, 200), "a3": (200, 200, 30)}
    meta: dict[str, dict] = {}
    for name, rgb in colors.items():
        im = Image.new("RGB", (32, 24), rgb)
        p = base / f"{name}.jpg"
        im.save(p, format="JPEG", quality=95)
        b = p.read_bytes()
        sha = hashlib.sha256(b).hexdigest()
        sub = imgs / sha[:2]
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{sha}.jpg").write_bytes(b)
        meta[name] = {"sha": sha, "bytes": len(b), "w": 32, "h": 24}

    rows = ["row,sha256,bytes,w,h,occurrences,first_seen"]
    for i, name in enumerate(sorted(meta, key=lambda n: meta[n]["sha"])):
        m = meta[name]
        rows.append(f"{i},{m['sha']},{m['bytes']},{m['w']},{m['h']},1,x#query")
    (base / "corpus_manifest.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    occ = ["qid,role,rank,sha256"]
    occ.append(f"{QIDS[0]},query,,{meta['q1']['sha']}")
    occ.append(f"{QIDS[0]},gt,0,{meta['a1']['sha']}")
    (base / "occurrences.csv").write_text("\n".join(occ) + "\n", encoding="utf-8")
    (base / "corpus_meta.json").write_text(json.dumps({"content_digest_sha256": "test"}), encoding="utf-8")
    return base, {k: v["sha"] for k, v in meta.items()}, meta


def make_iface(base: Path, sha: dict[str, str], meta: dict[str, dict]) -> Path:
    (base / "pools").mkdir(parents=True, exist_ok=True)
    (base / "select3").mkdir(parents=True, exist_ok=True)
    (base / "pool_quality").mkdir(parents=True, exist_ok=True)
    cands = [sha["a1"], sha["a2"], sha["a3"]]

    lines = ["qid,pool_id,retriever_id,embed_dim,rank,sha256,score,is_self_removed,refill_used"]
    for q in QIDS:
        for r, s in enumerate(cands, 1):
            lines.append(f"{q},eg2_shared_top10,eg2@test,768,{r},{s},{0.9 - 0.1 * r:.3f},0,0")
    (base / "pools" / "toy__dim768__top10.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    sel = ["qid,strategy,embed_dim,slot,sha256,score,selection_seed,order_rule"]
    for q in QIDS:
        for slot, s in enumerate(cands, 1):
            sel.append(f"{q},cosine,768,{slot},{s},0.8,,score desc")
        for slot, s in enumerate(reversed(cands), 1):
            sel.append(f"{q},random,768,{slot},{s},0.7,20261017,score desc")
    (base / "select3" / "toy__dim768__cosine+random.csv").write_text("\n".join(sel) + "\n", encoding="utf-8")

    qual = ["qid,pool_id,embed_dim,top1_score,top2_score,top3_score,gap_top1_top2,gap_top1_top3,"
            "mean_top10,min_adjacent_margin,max_cosine,n_candidates,self_removed,refill_used,"
            "query_sha256,query_w,query_h"]
    for q in QIDS:
        qual.append(f"{q},eg2_shared_top10,768,0.8,0.7,,0.1,,0.75,0.1,0.8,2,1,False,{sha['q1']},32,24")
    (base / "pool_quality" / "toy__dim768__margins.csv").write_text("\n".join(qual) + "\n", encoding="utf-8")
    return base


def run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.pop("EDGECORAG_CORPUS", None)
    e.pop("EDGECORAG_IFACE", None)
    if env:
        e.update(env)
    return subprocess.run([PY, str(SCRIPT), *args], capture_output=True, text=True, env=e)


def main() -> int:
    checks: list[dict] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        # 洗掉临时目录绝对路径，使回执可逐字节复现
        checks.append({"check": name, "pass": bool(cond), "detail": _scrub(detail)})

    tmp = Path(tempfile.mkdtemp(prefix="a15test_"))
    try:
        corpus, sha, meta = make_corpus(tmp / "corpus")
        iface = make_iface(tmp / "iface", sha, meta)

        # 1) 缺 --corpus 且无环境变量
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "cosine", "--iface", str(iface)])
        ok("missing_corpus_clear_error", r.returncode != 0
           and "--corpus" in (r.stderr + r.stdout)
           and "EDGECORAG_CORPUS" in (r.stderr + r.stdout),
           (r.stderr + r.stdout).strip().splitlines()[:1])

        # 2) 不完整语料目录
        bad = tmp / "bad_corpus"
        bad.mkdir()
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "cosine",
                 "--iface", str(iface), "--corpus", str(bad)])
        ok("incomplete_corpus_error", r.returncode != 0 and "不完整" in (r.stderr + r.stdout),
           (r.stderr + r.stdout).strip().splitlines()[:1])

        # 3a) 显式 --corpus 物化 cosine
        out1 = tmp / "out_cosine"
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "cosine",
                 "--iface", str(iface), "--corpus", str(corpus), "--out", str(out1)])
        ok("materialize_with_corpus_flag", r.returncode == 0, (r.stderr or r.stdout)[-200:])
        vj = json.loads((out1 / "verify.json").read_text(encoding="utf-8")) if (out1 / "verify.json").exists() else {}
        ok("verify_zero_mismatch", vj.get("mismatch") == 0, json.dumps(vj)[:120])
        idx = (out1 / "evidence_index.csv").read_text(encoding="utf-8").splitlines()[1:]
        ok("evidence_rows_query_plus_3", len(idx) == len(QIDS) * 4, f"rows={len(idx)}")
        import csv as _csv
        rows = list(_csv.DictReader((out1 / "evidence_index.csv").open(encoding="utf-8")))
        per_q: dict[str, list[str]] = {}
        for row in rows:
            per_q.setdefault(row["qid"], []).append(row["rank"])
        ok("slot_contiguous",
           all(sorted(int(r) for r in ranks if r != "") == [1, 2, 3]
               and ranks.count("") == 1 for ranks in per_q.values()),
           json.dumps(per_q))

        # 3b) 环境变量 EDGECORAG_CORPUS
        out2 = tmp / "out_env"
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "random",
                 "--iface", str(iface), "--out", str(out2)],
                env={"EDGECORAG_CORPUS": str(corpus)})
        ok("materialize_with_env_var", r.returncode == 0, (r.stderr or r.stdout)[-200:])
        vj2 = json.loads((out2 / "verify.json").read_text(encoding="utf-8"))
        ok("env_var_verify_ok", vj2.get("mismatch") == 0)

        # 4) random 策略的 slot 顺序与清单一致（此处 reversed 候选）
        lst = [json.loads(x) for x in (out2 / "evidence_list.jsonl").read_text(encoding="utf-8").splitlines()]
        ok("random_slots_follow_listing",
           [e["sha256"] for e in lst[0]["evidence"]] == [sha["a3"], sha["a2"], sha["a1"]],
           json.dumps([e["sha256"][:8] for e in lst[0]["evidence"]]))

        # 5) utility：缺分数 → 退出码 3；给全 → 按分数降序选 top3
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "utility",
                 "--iface", str(iface), "--corpus", str(corpus),
                 "--scores", str(tmp / "nope.csv")])
        ok("utility_missing_scores_nonzero", r.returncode != 0, f"rc={r.returncode}")

        scores = tmp / "scores.csv"
        scores.write_text("qid,sha256,score\n" + "".join(
            f"{q},{sha['a1']},0.2\n{q},{sha['a2']},0.9\n{q},{sha['a3']},0.5\n" for q in QIDS), encoding="utf-8")
        out3 = tmp / "out_utility"
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "utility",
                 "--iface", str(iface), "--corpus", str(corpus),
                 "--scores", str(scores), "--out", str(out3)])
        ok("utility_materialize_ok", r.returncode == 0, (r.stderr or r.stdout)[-200:])
        lst3 = [json.loads(x) for x in (out3 / "evidence_list.jsonl").read_text(encoding="utf-8").splitlines()]
        ok("utility_top3_by_score_desc",
           [e["sha256"] for e in lst3[0]["evidence"]] == [sha["a2"], sha["a3"], sha["a1"]],
           json.dumps([e["sha256"][:8] for e in lst3[0]["evidence"]]))

        # 5b) 分数缺一半候选 → 拒绝
        half = tmp / "scores_half.csv"
        half.write_text("qid,sha256,score\n" + f"{QIDS[0]},{sha['a1']},0.5\n", encoding="utf-8")
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "utility",
                 "--iface", str(iface), "--corpus", str(corpus),
                 "--scores", str(half), "--out", str(tmp / "out_half")])
        ok("utility_incomplete_scores_rejected", r.returncode == 3, f"rc={r.returncode}")

        # 6) 缺 --iface 时用默认路径（仓库内）应找不到 toy 池 → 非零
        r = run(["--cohort", "toy", "--dim", "768", "--strategy", "cosine",
                 "--corpus", str(corpus)])
        ok("default_iface_missing_pool_nonzero", r.returncode != 0, f"rc={r.returncode}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(c["pass"] for c in checks)
    payload = {"passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    out = a00_paths.reports_dir() / "a15_portability_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
