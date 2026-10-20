"""跨平台行尾守卫测试：证明 a17 在 LF / CRLF 两种检出下都给出确定的结论。

背景（P0）：清单曾按 Windows CRLF 工作树记录 sha256/bytes，导致干净 LF 检出上 36 个产物
全部 sha+size mismatch。修复后：
  * artifacts.json 一律按 **LF 字节**记哈希（summary.hash_normalization = "LF"）；
  * a17 默认先做 `\\r\\n -> \\n` 归一化再比对（Windows CRLF 工作树也能通过）；
  * `--strict-lf` 反过来：发现 CRLF 直接失败并给修复提示；
  * 内容被改动 / 字节数不符 / 缺少归一化标记 → 一律失败（锁定退出码，不放水）。

实现方式：在临时目录里搭一个**最小但完整**的接口（11 个语料内容、1 题、10 候选、2 策略、
1 条 pool_quality、3 个产物条目），然后跑真实的 a17/a23 子进程。

用法：python a-side/scripts/a22_crlf_guard_test.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys

try:  # Windows 控制台可能是 cp936，统一成 utf-8 输出，避免中文 detail 触发 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
A17 = HERE / "a17_verify_interface.py"
A23 = HERE / "a23_fix_manifest_line_endings.py"
PY = sys.executable
QID = "mragb:1"


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def build_iface(base: Path) -> Path:
    """搭一个能被 a17 完整校验通过的最小接口。"""
    (base / "corpus").mkdir(parents=True)
    (base / "pools").mkdir()
    (base / "select3").mkdir()
    (base / "pool_quality").mkdir()

    contents = [_sha_text(f"img{i}") for i in range(11)]
    contents.sort()
    query_sha, cands = contents[0], sorted(contents[1:])[:10]

    rows = ["row,sha256,bytes,w,h,occurrences,first_seen"]
    for i, s in enumerate(contents):
        rows.append(f"{i},{s},100,32,24,1,x#query")
    (base / "corpus" / "corpus_manifest.csv").write_bytes(("\n".join(rows) + "\n").encode())
    digest = hashlib.sha256()
    for s in contents:
        digest.update(f"{s}\n".encode())
    (base / "corpus" / "corpus_meta.json").write_text(
        json.dumps({"content_digest_sha256": digest.hexdigest()}), encoding="utf-8")

    scores = [round(0.9 - 0.01 * i, 6) for i in range(10)]
    pool = ["qid,pool_id,retriever_id,embed_dim,rank,sha256,score,is_self_removed,refill_used"]
    for r, (s, sc) in enumerate(zip(cands, scores), 1):
        pool.append(f"{QID},toy,eg2@test,768,{r},{s},{sc},0,0")
    (base / "pools" / "toy__dim768__top10.csv").write_bytes(("\n".join(pool) + "\n").encode())

    sel = ["qid,strategy,embed_dim,slot,sha256,score,selection_seed,order_rule"]
    for slot in range(3):
        sel.append(f"{QID},cosine,768,{slot + 1},{cands[slot]},{scores[slot]},,score desc")
    for slot in range(3):
        sel.append(f"{QID},random,768,{slot + 1},{cands[slot]},{scores[slot]},20261017,score desc")
    (base / "select3" / "toy__dim768__cosine+random.csv").write_bytes(
        ("\n".join(sel) + "\n").encode())

    margins = min(scores[i] - scores[i + 1] for i in range(9))
    qual = ["qid,pool_id,embed_dim,top1_score,top2_score,top3_score,gap_top1_top2,gap_top1_top3,"
            "mean_top10,min_adjacent_margin,max_cosine,n_candidates,self_removed,refill_used,"
            "query_sha256,query_w,query_h",
            f"{QID},toy,768,{scores[0]},{scores[1]},{scores[2]},{scores[0]-scores[1]},"
            f"{scores[0]-scores[2]},{sum(scores)/10},{margins},{scores[0]},10,1,False,"
            f"{query_sha},32,24"]
    (base / "pool_quality" / "toy__dim768__margins.csv").write_bytes(
        ("\n".join(qual) + "\n").encode())

    arts = []
    for rel in ("pools/toy__dim768__top10.csv",
                "select3/toy__dim768__cosine+random.csv",
                "pool_quality/toy__dim768__margins.csv"):
        b = (base / rel).read_bytes()
        arts.append({"path": rel, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b),
                     "rows": 0, "note": "test"})
    (base / "artifacts.json").write_text(json.dumps(
        {"summary": {"hash_normalization": "LF"}, "artifacts": arts}, indent=2), encoding="utf-8")
    return base


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(script), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def to_crlf(p: Path) -> None:
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def to_lf(p: Path) -> None:
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))


def verify_json(iface: Path) -> dict:
    return json.loads((iface / "verify.json").read_text(encoding="utf-8"))


def main() -> int:
    checks: list[dict] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(cond), "detail": detail})

    base = Path(tempfile.mkdtemp(prefix="a22test_"))
    iface = build_iface(base / "iface")
    pool = iface / "pools" / "toy__dim768__top10.csv"

    # 1) 纯 LF：默认与 strict 都应通过
    r = run(A17, "--iface", str(iface))
    ok("lf_default_pass", r.returncode == 0 and verify_json(iface)["fail_count"] == 0,
       f"rc={r.returncode}")
    r = run(A17, "--iface", str(iface), "--strict-lf")
    ok("lf_strict_pass", r.returncode == 0, f"rc={r.returncode}")

    # 2) CRLF 工作树：默认归一化后通过
    to_crlf(pool)
    r = run(A17, "--iface", str(iface))
    vj = verify_json(iface)
    ok("crlf_default_pass_normalized", r.returncode == 0 and vj["fail_count"] == 0
       and vj["files_with_crlf"] >= 1, f"rc={r.returncode} crlf={vj.get('files_with_crlf')}")

    # 3) CRLF + --strict-lf：必须失败且提示可操作
    r = run(A17, "--iface", str(iface), "--strict-lf")
    out = r.stdout + r.stderr
    ok("crlf_strict_rejected", r.returncode != 0 and "CRLF" in out and "autocrlf" in out,
       f"rc={r.returncode}")

    # 4) 内容被改（CRLF 状态下改一个字符）：必须失败
    to_crlf(pool)
    txt = pool.read_bytes().replace(b"0.89", b"0.88", 1)
    pool.write_bytes(txt)
    r = run(A17, "--iface", str(iface))
    ok("content_change_rejected", r.returncode != 0
       and any("sha mismatch" in f for f in verify_json(iface)["fails"]), f"rc={r.returncode}")

    # 5) 字节数口径不符：必须失败
    build_iface(base / "iface2")
    man = json.loads((base / "iface2" / "artifacts.json").read_text(encoding="utf-8"))
    man["artifacts"][0]["bytes"] += 1
    (base / "iface2" / "artifacts.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    r = run(A17, "--iface", str(base / "iface2"))
    ok("size_mismatch_rejected", r.returncode != 0
       and any("size mismatch" in f for f in verify_json(base / "iface2")["fails"]))

    # 6) 清单缺 hash_normalization：必须失败（防止口径标记被悄悄删掉）
    build_iface(base / "iface3")
    man = json.loads((base / "iface3" / "artifacts.json").read_text(encoding="utf-8"))
    man["summary"] = {}
    (base / "iface3" / "artifacts.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    r = run(A17, "--iface", str(base / "iface3"))
    ok("missing_normalization_marker_rejected", r.returncode != 0
       and any("hash_normalization" in f for f in verify_json(base / "iface3")["fails"]))

    # 7) a23 幂等：CRLF 目录上跑一次收敛为 LF 口径，再跑不应再改
    build_iface(base / "iface4")
    for rel in ("pools/toy__dim768__top10.csv",
                "select3/toy__dim768__cosine+random.csv",
                "pool_quality/toy__dim768__margins.csv"):
        to_crlf(base / "iface4" / rel)
    r1 = run(A23, "--iface", str(base / "iface4"), "--apply")
    man1 = (base / "iface4" / "artifacts.json").read_text(encoding="utf-8")
    r2 = run(A23, "--iface", str(base / "iface4"), "--apply")
    man2 = (base / "iface4" / "artifacts.json").read_text(encoding="utf-8")
    r3 = run(A17, "--iface", str(base / "iface4"))
    ok("a23_idempotent_and_a17_passes",
       r1.returncode == 0 and r2.returncode == 0 and man1 == man2 and r3.returncode == 0,
       f"rc={r1.returncode}/{r2.returncode}/{r3.returncode}")

    passed = sum(c["pass"] for c in checks)
    payload = {"passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    out = ROOT / "a-side" / "reports" / "next_stage_20261020" / "crlf_guard_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
