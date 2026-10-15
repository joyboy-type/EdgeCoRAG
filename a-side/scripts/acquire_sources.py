"""抓取复现对象：论文 PDF + 作者代码仓库。

用法:
    python scripts/acquire_sources.py                # 全部抓取
    python scripts/acquire_sources.py --only pdf     # 只抓论文
    python scripts/acquire_sources.py --only repo    # 只抓代码
    python scripts/acquire_sources.py --key utility_mrag

设计要点:
  * 论文 PDF 与纯文本正文分目录保存 (papers/<key>/{paper.pdf,paper.txt,meta.json})
  * 计算 pdf_sha256 写入 source_manifest.csv,满足任务书"三方留证"要求
  * 仓库保留 .git,以便记录 commit SHA;无 git 时回退到 zipball 下载
  * 全部请求带重试与 UA,失败不静默
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PAPERS = ROOT / "papers"
THIRD_PARTY = ROOT / "third_party"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "*/*"}

# ---------------------------------------------------------------- 源定义
# pdf: 可直连的 PDF 地址(按顺序尝试); repo: 作者代码仓库
SOURCES: dict[str, dict] = {
    "utility_mrag": {
        "title": "Utility-Oriented Visual Evidence Selection for Multimodal Retrieval-Augmented Generation",
        "venue": "ACL 2026 Long", "year": 2026, "priority": "P0",
        "authors": "Weiqing Luo, Zongye Hu, Xiao Wang, Zhiyuan Yu, Haofeng Zhang, Ziyi Huang",
        "pages": "35091-35124", "doi": "10.18653/v1/2026.acl-long.1620",
        "landing": "https://aclanthology.org/2026.acl-long.1620/",
        "pdf": ["https://aclanthology.org/2026.acl-long.1620.pdf"],
        "repo": "https://github.com/Hcnaeg/utility-mrag",
        "license_note": "ACL Anthology CC-BY-4.0 (2016 起材料)",
    },
    "ragrouter": {
        "title": "RAGRouter: Learning to Route Queries to Multiple Retrieval-Augmented Language Models",
        "venue": "NeurIPS 2025 Main", "year": 2025, "priority": "P0",
        "authors": "Zhang et al.",
        "landing": "https://proceedings.neurips.cc/paper_files/paper/2025/hash/"
                   "1759a83b007f0685c3fbc460fa1b6395-Abstract-Conference.html",
        "pdf": ["https://arxiv.org/pdf/2505.23052"],
        "repo": "https://github.com/OwwO99/RAGRouter",
        "license_note": "纯文本 RAG,转视觉属适配,不得称为直接多模态复现",
    },
    "vqpp": {
        "title": "Fix Before Search: Benchmarking Agentic Visual Query Pre-processing "
                 "in Multimodal Retrieval-augmented Generation",
        "venue": "ICML 2026", "year": 2026, "priority": "P1",
        "authors": "Zeng et al.",
        "landing": "https://icml.cc/virtual/2026/poster/62898",
        "pdf": ["https://arxiv.org/pdf/2602.13179"],
        "repo": "https://github.com/phycholosogy/VQQP_Bench",
        "license_note": "robustness 扩展,非首周必需",
    },
    "mrag_bench": {
        "title": "MRAG-Bench: Vision-Centric Evaluation for Retrieval-Augmented Multimodal Models",
        "venue": "ICLR 2025", "year": 2025, "priority": "统一评价",
        "authors": "Hu et al.",
        "landing": "https://arxiv.org/abs/2410.08182",
        "pdf": ["https://arxiv.org/pdf/2410.08182"],
        "repo": "https://github.com/mragbench/MRAG-Bench",
        "dataset": "uclanlp/MRAG-Bench",
        "license_note": "主数据;1,353 题视觉中心评测",
    },
    "visdom": {
        "title": "VisDoM: Multi-Document QA with Visually Rich Elements Using "
                 "Multimodal Retrieval-Augmented Generation",
        "venue": "NAACL 2025 Long", "year": 2025, "priority": "扩展参考",
        "authors": "Manan Suri, Puneet Mathur, Franck Dernoncourt, Kanika Goswami, "
                   "Ryan A. Rossi, Dinesh Manocha",
        "anthology_id": "2025.naacl-long.310", "pages": "6088-6109",
        "doi": "10.18653/v1/2025.naacl-long.310", "arxiv_id": "2412.10704",
        "landing": "https://aclanthology.org/2025.naacl-long.310/",
        "pdf": ["https://aclanthology.org/2025.naacl-long.310.pdf"],
        "repo": "https://github.com/MananSuri27/VisDoM",
        # visdomrag.py 已核实存在于仓库根目录 (blob sha 7bd6abef..., 53691 B)
        "dataset": "VisDoMBench(数据集随仓库分发,无独立 HF 页)",
        "license_note": "⚠️ 仓库与数据集均无 LICENSE(GitHub API license=null);"
                        "数据由 PaperTab/FeTaTab/SciGraphQA/SPIQA/SlideVQA 汇编,"
                        "各上游数据集许可需单独核对。论文为 CC-BY-4.0,不覆盖代码与数据",
    },
}


# ---------------------------------------------------------------- 工具函数
def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, *, timeout: int = 120, tries: int = 4, stream: bool = False):
    """带指数退避的 GET。全部失败则抛最后一个异常。"""
    last: Exception | None = None
    for i in range(1, tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout,
                             allow_redirects=True, stream=stream)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait = min(2 ** i, 20)
            log(f"    ! 第 {i}/{tries} 次失败: {type(exc).__name__}: {exc} -> {wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"无法获取 {url}: {last}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_to_text(pdf_path: Path, txt_path: Path) -> tuple[bool, str]:
    """用 pypdf 抽取正文。返回 (是否成功, 说明)。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return False, "pypdf 未安装"
    try:
        reader = PdfReader(str(pdf_path))
        chunks: list[str] = []
        for idx, page in enumerate(reader.pages, 1):
            try:
                chunks.append(f"\n===== [page {idx}] =====\n" + (page.extract_text() or ""))
            except Exception as exc:  # noqa: BLE001
                chunks.append(f"\n===== [page {idx}] =====\n<抽取失败: {exc}>")
        text = "".join(chunks).strip()
        if not text:
            return False, "抽取结果为空(可能是扫描版 PDF,需 OCR)"
        txt_path.write_text(text, encoding="utf-8")
        return True, f"{len(reader.pages)} 页 / {len(text)} 字符"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- 抓论文
def acquire_pdfs(keys: list[str]) -> list[dict]:
    rows: list[dict] = []
    for key in keys:
        spec = SOURCES[key]
        outdir = PAPERS / key
        outdir.mkdir(parents=True, exist_ok=True)
        row = {
            "key": key, "paper_title": spec["title"], "venue": spec["venue"],
            "year": spec["year"], "priority": spec["priority"], "authors": spec.get("authors", ""),
            "paper_url": spec.get("landing", ""), "pdf_url": "", "pdf_sha256": "",
            "repo_url": spec.get("repo", ""), "commit_sha": "",
            "dataset_repo": spec.get("dataset", ""), "dataset_revision": "",
            "license": spec.get("license_note", ""), "checked_at": time.strftime("%Y-%m-%d"),
            "notes": "",
        }

        if not spec["pdf"]:
            log(f"[{key}] 未配置 PDF 地址,跳过(待补)")
            row["notes"] = "PDF 地址待核对"
            rows.append(row)
            continue

        pdf_path = outdir / "paper.pdf"
        if pdf_path.exists() and pdf_path.stat().st_size > 20_000:
            log(f"[{key}] PDF 已存在,跳过下载 ({pdf_path.stat().st_size} B)")
        else:
            ok = False
            for url in spec["pdf"]:
                try:
                    log(f"[{key}] 下载 {url}")
                    r = fetch(url, timeout=180)
                    data = r.content
                    if not data.startswith(b"%PDF"):
                        log(f"    ! 返回内容不是 PDF (前 16 字节: {data[:16]!r}),换下一个源")
                        continue
                    pdf_path.write_bytes(data)
                    log(f"    -> {len(data)} B 已保存")
                    row["pdf_url"] = url
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001
                    log(f"    ! 下载失败: {exc}")
            if not ok:
                row["notes"] = "PDF 下载失败"
                rows.append(row)
                continue

        if not row["pdf_url"]:
            row["pdf_url"] = spec["pdf"][0] if spec["pdf"] else ""
        row["pdf_sha256"] = sha256_of(pdf_path)
        log(f"[{key}] sha256={row['pdf_sha256'][:16]}...")

        txt_path = outdir / "paper.txt"
        ok_txt, note = pdf_to_text(pdf_path, txt_path)
        log(f"[{key}] 正文抽取: {'成功' if ok_txt else '失败'} — {note}")
        if not ok_txt:
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + f"正文抽取失败: {note}"

        meta = {**spec, "pdf_sha256": row["pdf_sha256"], "pdf_bytes": pdf_path.stat().st_size,
                "text_ok": ok_txt, "text_note": note, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 抓仓库
def _git_exe() -> str | None:
    """优先使用项目内便携版 git(tools/mingit),否则回退系统 PATH。"""
    portable = ROOT / "tools" / "mingit" / "cmd" / "git.exe"
    if portable.exists():
        return str(portable)
    return shutil.which("git")


def _git_available() -> bool:
    return _git_exe() is not None


# ---------------------------------------------------------------- GitHub 直连探测
# 本机实测(scripts/probe_network.py):
#   github.com            -> TCP 443 阻断(git clone 不可用)
#   api.github.com        -> 可用
#   codeload.github.com   -> 可用(zipball)
#   raw.githubusercontent -> DNS 被劫持到 127.0.0.1
# 故克隆策略: 优先 git;git 失败则回退 codeload zipball + API 取 commit SHA。
GITHUB_API = "https://api.github.com"


def github_repo_info(owner_repo: str) -> dict:
    """取仓库元信息: 默认分支、commit SHA、许可证。"""
    r = fetch(f"{GITHUB_API}/repos/{owner_repo}", timeout=60)
    j = r.json()
    branch = j.get("default_branch", "main")
    lic = (j.get("license") or {}).get("spdx_id") or ""
    # 取该分支最新 commit SHA
    sha = ""
    try:
        c = fetch(f"{GITHUB_API}/repos/{owner_repo}/commits/{branch}", timeout=60)
        sha = c.json().get("sha", "")
    except Exception as exc:  # noqa: BLE001
        log(f"    ! 取 commit SHA 失败: {exc}")
    return {"branch": branch, "sha": sha, "license": lic,
            "pushed_at": j.get("pushed_at", ""), "size_kb": j.get("size", 0)}


def download_zipball(owner_repo: str, branch: str, dest: Path) -> bool:
    """经 codeload.github.com 下载 zipball 并解压到 dest。"""
    url = f"https://codeload.github.com/{owner_repo}/zip/refs/heads/{branch}"
    try:
        log(f"    zipball: {url}")
        r = fetch(url, timeout=600)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            zf.extractall(dest)
        # codeload 的 zipball 顶层目录形如 <repo>-<sha>
        tops = {n.split("/")[0] for n in names if "/" in n}
        top = sorted(tops)[0] if tops else None
        if top:
            inner = dest / top
            if inner.is_dir():
                for item in inner.iterdir():
                    shutil.move(str(item), str(dest / item.name))
                inner.rmdir()
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        log(f"    ! zipball 失败: {exc}")
        return False


def acquire_repos(keys: list[str], rows: list[dict]) -> None:
    by_key = {r["key"]: r for r in rows}
    for key in keys:
        spec = SOURCES[key]
        repo = spec.get("repo")
        if not repo:
            log(f"[{key}] 未配置仓库地址,跳过(待补)")
            continue
        owner_repo = "/".join(repo.rstrip("/").split("/")[-2:])
        dest = THIRD_PARTY / owner_repo.split("/")[-1]

        # 先用 API 拿元信息(本机 api.github.com 可达)
        info: dict = {}
        try:
            info = github_repo_info(owner_repo)
            log(f"[{key}] {owner_repo}: branch={info['branch']} sha={info['sha'][:12]} "
                f"license={info['license'] or '无'} size={info['size_kb']}KB")
        except Exception as exc:  # noqa: BLE001
            log(f"[{key}] ! GitHub API 不可用: {exc}")

        if (dest / ".git").exists():
            log(f"[{key}] 已有 git 仓库: {dest}")
        elif dest.exists() and any(dest.iterdir()):
            log(f"[{key}] 目录已存在且非空,跳过下载: {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            git = _git_exe()
            cloned = False
            if git:
                log(f"[{key}] 尝试 git clone {repo}")
                r = subprocess.run([git, "clone", "--depth", "50", repo, str(dest)],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    cloned = True
                else:
                    log(f"    ! git clone 失败(github.com 可能被阻断): "
                        f"{r.stderr.strip().splitlines()[-1][:200] if r.stderr.strip() else ''}")
            if not cloned:
                log(f"[{key}] 回退 codeload zipball")
                ok = download_zipball(owner_repo, info.get("branch", "main"), dest)
                if not ok:
                    log(f"[{key}] ✗ 仓库获取失败,需人工处理")
                    continue
                log(f"    -> 已解压到 {dest} (无 .git,commit SHA 来自 API)")

        # 记录 commit SHA
        sha = ""
        if (dest / ".git").exists() and _git_exe():
            r = subprocess.run([_git_exe(), "-C", str(dest), "rev-parse", "HEAD"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                sha = r.stdout.strip()
        if not sha:
            sha = info.get("sha", "")
        if sha:
            log(f"[{key}] commit_sha={sha[:12]}")
            if key in by_key:
                by_key[key]["commit_sha"] = sha

        # 记录许可证
        if key in by_key:
            lic = info.get("license", "")
            for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
                p = dest / name
                if p.exists():
                    first = p.read_text(encoding="utf-8", errors="replace")[:120].splitlines()
                    lic = f"{lic} | {first[0]}" if lic and first else (first[0] if first else lic)
                    break
            if lic:
                by_key[key]["license"] = (by_key[key]["license"] + f" | repo: {lic}").strip(" |")


# ---------------------------------------------------------------- 清单
FIELDS = ["key", "paper_title", "venue", "year", "priority", "authors", "paper_url",
          "pdf_url", "pdf_sha256", "repo_url", "commit_sha", "dataset_repo",
          "dataset_revision", "license", "checked_at", "notes"]


def write_manifest(rows: list[dict]) -> Path:
    path = ROOT / "source_manifest.csv"
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                existing[r.get("key", "")] = r
    for r in rows:
        old = existing.get(r["key"], {})
        for f in FIELDS:
            if not r.get(f) and old.get(f):
                r[f] = old[f]
        existing[r["key"]] = r
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in existing.values():
            w.writerow({f: r.get(f, "") for f in FIELDS})
    return path


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["pdf", "repo", "all"], default="all")
    ap.add_argument("--key", action="append", default=None,
                    help="只处理指定 key,可重复")
    args = ap.parse_args()

    keys = args.key or list(SOURCES)
    unknown = [k for k in keys if k not in SOURCES]
    if unknown:
        log(f"未知 key: {unknown};可选: {list(SOURCES)}")
        return 2

    PAPERS.mkdir(parents=True, exist_ok=True)
    THIRD_PARTY.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    if args.only in ("pdf", "all"):
        rows = acquire_pdfs(keys)
    else:
        # 仅抓仓库时也要能更新已存在的清单
        rows = [{f: "" for f in FIELDS} | {"key": k} for k in keys]

    if args.only in ("repo", "all"):
        acquire_repos(keys, rows)

    path = write_manifest(rows)
    log(f"\n清单已写出: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
