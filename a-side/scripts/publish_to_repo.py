"""把 A 侧的产出发布到共创仓库 joyboy-type/EdgeCoRAG。

**设计说明**

仓库当前只有 README 与 .gitignore(空脚手架)。本脚本把工作区产出组织成
适合入库的形式,提交前做安全审查,然后推送。

仓库的 .gitignore 已排除 `/data/`、`/datasets/`、`/models/`、`/outputs/`、
`*.parquet`、`*.safetensors` 等,因此**只放文档、代码、接口契约与少量样例图片**,
不放大体积产物(模型权重、数据集、索引)。

入库布局:

    README.md           仓库总入口(本脚本生成)
    .gitignore          保留原样
    handover/           给 B 的交接包(文档 + schema + 5 题样例含图片)
    a-side/             A 侧可复现资产
        scripts/        探针、校验、生成脚本
        reports/        环境审计与复现进展
        data/           小体积事实文件(schema / 证据本体统计 / 源清单)
        setup/          本机代理与镜像注意事项

**本机注意**

`github.com` 被 Watt Toolkit(`Steam++.Accelerator`)在 `0.0.0.0:443` 本地拦截,
schannel 无法完成吊销检查,故所有 git 操作都带 `-c http.sslVerify=false`。
HTTPS 连接呈**间歇性**失败,故克隆带重试、并优先复用已有副本。

用法:
    python scripts/publish_to_repo.py --dry-run                 # 只准备+审查,不推
    python scripts/publish_to_repo.py --use-stored-credential   # 用本机凭据管理器
    python scripts/publish_to_repo.py --token <PAT>
    $env:EDGECORAG_GH_TOKEN='<PAT>'; python scripts/publish_to_repo.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

WS = cfg.ROOT.parent
HANDOVER = WS / "EdgeCoRAG-B-handover"
A_ROOT = WS / "EdgeCoRAG-A"
REPO_URL = "https://github.com/joyboy-type/EdgeCoRAG.git"
WORKTREE = cfg.store_root() / "_repo_work"
GIT = A_ROOT / "tools" / "mingit" / "cmd" / "git.exe"
GIT_BASE = [str(GIT), "-c", "http.sslVerify=false"]

KEEP_SCRIPTS = [
    "project_config.py", "download_dataset.py", "analyze_evidence_semantics.py",
    "make_b_handover_sample.py", "validate_schema.py", "validate_handover_package.py",
    "download_models.py", "smoke_embedding.py", "probe_gemma4_logits.py",
    "diagnose_vram.py", "probe_network.py", "probe_mirrors.py",
    "probe_model_sizes.py", "probe_coauthor_repo.py",
    "verify_github_api_authenticity.py", "diagnose_tls_interception.py",
    "bootstrap_store.py", "acquire_sources.py", "setup_env.py",
    "install_portable_git.py", "audit_before_push.py", "publish_to_repo.py",
    "git_cred_store.py",
    # 本轮新增（修订与验收）
    "audit_gt_match_rate.py", "reconcile_dataset_size.py",
    "verify_hash_reliability.py", "test_hash_stability.py",
    "determine_hash_method.py", "near_duplicate_check.py",
    "verify_sample_files.py", "verify_handover_sample.py", "make_split.py",
    # 本轮新增（切分 v2 / 实体连通性 / 语料探测）
    "verify_split.py", "build_entity_groups.py", "quantify_entity_connectivity.py",
    "probe_corpus_access.py", "build_evidence_package.py", "build_external_manifest.py",
    # 本轮新增（S1/S2/S3 正式口径证据包 + 包验收）
    "verify_packages.py", "build_distractor_package.py",
    "finalize_s3_packages.py",
]
KEEP_REPORTS = ["audit_env.md", "A_P0_P1.md",
                "requirements-main.lock.txt", "requirements-mrag.lock.txt"]
KEEP_DATA = [
    ("outputs/dataset_probe/mrag_bench_schema.json", "mrag_bench_schema.json"),
    ("outputs/dataset_probe/evidence_ontology.json", "evidence_ontology.json"),
    ("outputs/dataset_probe/gt_match_rate_audit.json", "gt_match_rate_audit.json"),
    ("outputs/dataset_probe/near_duplicate_report.json", "near_duplicate_report.json"),
    ("outputs/dataset_probe/size_reconciliation.json", "size_reconciliation.json"),
    ("outputs/dataset_probe/entity_connectivity.json", "entity_connectivity.json"),
    ("outputs/corpus_probe/corpus_access.json", "corpus_access.json"),
    ("outputs/handover_verify/acceptance_report.json", "acceptance_report.json"),
    ("outputs/handover_verify/sample_files_check.json", "sample_files_check.json"),
    ("outputs/split_verify/split_report.json", "split_report.json"),
    ("outputs/gemma4_probe/tokenizer_check.json", "gemma4_tokenizer_check.json"),
    ("outputs/gemma4_probe/vram_diagnosis_gemma-4-E4B-it.json", "vram_diagnosis_e4b.json"),
    ("source_manifest.csv", "source_manifest.csv"),
]
# setup 与 plans 文档从 a-side-src 读入（避免把长文写死在脚本里）
SETUP_DIR = A_ROOT / "a-side-src" / "setup"
PLANS_DIR = A_ROOT / "a-side-src" / "plans"


def run(args: list[str], cwd: Path | None = None, check: bool = False,
        env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True,
                       text=True, errors="replace", env=env)
    if check and p.returncode != 0:
        print(f"  ! 命令失败({p.returncode}): {(p.stderr or p.stdout).strip()[:300]}")
    return p


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return run(GIT_BASE + list(args), cwd=cwd)


def prepare() -> Path:
    """准备本地工作副本: 有效则复用并同步,否则带重试克隆。"""
    print("=== 1. 准备本地工作副本 ===")
    valid = False
    if (WORKTREE / ".git").exists():
        valid = git("rev-parse", "--git-dir", cwd=WORKTREE).returncode == 0
        if not valid:
            print("  发现残留但无效的 .git 目录,将重新克隆")
            shutil.rmtree(WORKTREE, ignore_errors=True)

    if valid:
        print(f"  复用已有副本: {WORKTREE}")
        git("fetch", "origin", "--depth", "50", cwd=WORKTREE)
        git("reset", "--hard", "origin/main", cwd=WORKTREE)
        git("clean", "-fdq", cwd=WORKTREE)
        head = git("rev-parse", "HEAD", cwd=WORKTREE).stdout.strip()
        print(f"  已同步到 origin/main: {head[:12]}")
        return WORKTREE

    WORKTREE.parent.mkdir(parents=True, exist_ok=True)
    last = ""
    for attempt in range(1, 6):
        if WORKTREE.exists():
            shutil.rmtree(WORKTREE, ignore_errors=True)
        print(f"  克隆尝试 {attempt}/5 ...")
        r = git("clone", "--depth", "50", REPO_URL, str(WORKTREE))
        if (WORKTREE / ".git").exists():
            head = git("rev-parse", "HEAD", cwd=WORKTREE).stdout.strip()
            print(f"  ✅ 已克隆, HEAD {head[:12]}")
            return WORKTREE
        last = (r.stderr or r.stdout).strip()
        time.sleep(3 * attempt)

    print(f"  ✗ 连续 5 次克隆失败: {last[:200]}")
    print("    本机 github.com 被 Watt Toolkit 拦截导致间歇失败。")
    print("    可在 Watt Toolkit 里关闭「GitHub 加速」后重试。")
    raise SystemExit(1)


def populate(wt: Path) -> None:
    print("\n=== 2. 组织入库内容 ===")
    dst_h = wt / "handover"
    if dst_h.exists():
        shutil.rmtree(dst_h)
    shutil.copytree(HANDOVER, dst_h,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"  handover/        {sum(1 for f in dst_h.rglob('*') if f.is_file())} 个文件")

    dst_a = wt / "a-side"
    if dst_a.exists():
        shutil.rmtree(dst_a)
    for sub in ("scripts", "reports", "data", "setup"):
        (dst_a / sub).mkdir(parents=True)
    n = 0
    for name in KEEP_SCRIPTS:
        src = A_ROOT / "scripts" / name
        if src.exists():
            shutil.copy2(src, dst_a / "scripts" / name)
            n += 1
    print(f"  a-side/scripts/  {n} 个脚本")

    for name in KEEP_REPORTS:
        src = A_ROOT / "reports" / name
        if src.exists():
            shutil.copy2(src, dst_a / "reports" / name)
    for rel, out in KEEP_DATA:
        src = A_ROOT / rel
        if src.exists():
            shutil.copy2(src, dst_a / "data" / out)

    # setup 文档: 标准步骤与机器特有绕行**分开存放**
    n_setup = 0
    if SETUP_DIR.exists():
        for src in sorted(SETUP_DIR.glob("*.md")):
            shutil.copy2(src, dst_a / "setup" / src.name)
            n_setup += 1
    print(f"  a-side/setup/    {n_setup} 个文档(标准安装 + 机器特有分开)")

    # 题目切分清单（预先规则 + 固定种子 + sha256，需入库供双方对齐）
    src_splits = A_ROOT / "splits"
    if src_splits.exists():
        dst_sp = dst_a / "splits"
        dst_sp.mkdir(parents=True, exist_ok=True)
        n_sp = 0
        for src in sorted(src_splits.glob("*")):
            if src.is_file():
                shutil.copy2(src, dst_sp / src.name)
                n_sp += 1
        print(f"  a-side/splits/   {n_sp} 个文件(题目划分与种子)")

    # 交接计划：未完成事项与阻塞清单（供下一个接手者）
    if PLANS_DIR.exists():
        dst_pl = dst_a / "plans"
        dst_pl.mkdir(parents=True, exist_ok=True)
        n_pl = 0
        for src in sorted(PLANS_DIR.glob("*")):
            if src.is_file():
                shutil.copy2(src, dst_pl / src.name)
                n_pl += 1
        print(f"  a-side/plans/    {n_pl} 个文档(决策清单/未完成事项/变更说明/验证摘要)")

    # 外置材料清单与小体积哈希明细（物件本身不入库）
    ext_src = A_ROOT / "a-side-src" / "data" / "external"
    if ext_src.exists():
        dst_ext = dst_a / "data"
        dst_ext.mkdir(parents=True, exist_ok=True)
        n_ext = 0
        for src in sorted(ext_src.glob("*")):
            if src.is_file() and src.stat().st_size < 512 * 1024:
                shutil.copy2(src, dst_ext / src.name)
                n_ext += 1
        print(f"  a-side/data/     外置清单哈希明细 {n_ext} 个")

    (wt / "README.md").write_text(ROOT_README, encoding="utf-8")
    print("  README.md 已更新")


def merge_into_main(wt: Path, args, user: str, tok: str | None) -> int:
    """把已推送的分支**快进合并**进 main 并推送。

    只做 fast-forward: 若 main 与分支已分叉, 说明期间有人推了 main,
    此时**中止并提示**, 不生成合并提交, 避免掩盖冲突。
    """
    print(f"\n=== 6. 合并到 main(仅快进) ===")
    # 注意: 必须用 --force 更新跟踪引用。若远程分支历史被改写过(例如上一轮强推过),
    # 普通 fetch 会因非快进而**静默不更新**跟踪引用,导致后续 --force-with-lease
    # 用过期 OID 判租约,报 "stale info"(本机实测踩过两次)。
    git("fetch", "--force", "origin", "main", "--depth", "50", cwd=wt)
    ff = git("merge-base", "--is-ancestor", "origin/main", "HEAD", cwd=wt)
    if ff.returncode != 0:
        print("  ✗ 分支与 origin/main 已分叉(期间有人推送 main),不做合并。")
        print("    请先人工 rebase: git rebase origin/main,再重跑。")
        return 1

    print("  可快进。切换 main 并合并…")
    git("checkout", "-B", "main", "HEAD", cwd=wt)
    mg = git("merge", "--ff-only", args.branch, cwd=wt)
    if mg.returncode != 0:
        print(f"  ✗ 快进合并失败: {(mg.stderr or '').strip()[:200]}")
        return 1
    head = git("rev-parse", "HEAD", cwd=wt).stdout.strip()
    print(f"  main 现在指向 {head[:12]}")

    if tok:
        askpass = WORKTREE.parent / "_askpass2.cmd"
        askpass.write_text("@echo off\r\necho %EC_USER%\r\necho %EC_TOKEN%\r\n",
                           encoding="ascii")
        try:
            r = run(GIT_BASE + ["-c", f"core.askPass={askpass}", "push",
                                "origin", "HEAD:main"],
                    cwd=wt, env_extra={"EC_USER": user, "EC_TOKEN": tok})
        finally:
            askpass.unlink(missing_ok=True)
    else:
        r = git("push", "origin", "HEAD:main", cwd=wt)

    if r.returncode == 0:
        print(f"  ✅ main 已更新: https://github.com/joyboy-type/EdgeCoRAG/tree/main")
        # 合并后切回分支,便于后续增量提交
        git("checkout", args.branch, cwd=wt)
        return 0
    print(f"  ✗ 推送 main 失败: {((r.stderr or '') + (r.stdout or '')).strip()[:300]}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只准备+审查,不推送")
    ap.add_argument("--token", default=None, help="GitHub PAT(仅本次使用)")
    ap.add_argument("--use-stored-credential", action="store_true",
                    help="使用本机 Windows 凭据管理器中的 git 凭证")
    ap.add_argument("--branch", default=None,
                    help="推送到指定分支(默认推 main)。用于独立分支/PR 交付。")
    ap.add_argument("--new-branch-from-main", action="store_true",
                    help="从 origin/main 拉出新分支再推送(独立分支交付的推荐做法)")
    ap.add_argument("--force-with-lease", action="store_true",
                    help=("当远程分支已有本分支的旧提交时使用。带租约校验: "
                          "若远程在此期间被他人改动则会失败,不会覆盖协作者工作。"
                          "**仅在确认远程该分支只有自己的提交时使用。**"))
    ap.add_argument("--expect-remote-oid", default=None,
                    help=("与 --force-with-lease 配合: 显式声明期望的远程 OID。"
                          "因为用 checkout -B 创建的分支没有 upstream 配置,"
                          "纯 --force-with-lease 会报 stale info。"
                          "用法: --expect-remote-oid <sha>"))
    ap.add_argument("--merge-to-main", action="store_true",
                    help=("推送分支后, 再把该分支**快进合并**进 main 并推送 main。"
                          "仅在分支领先 main 时可快进; 若已分叉则中止, 不做合并提交。"))
    ap.add_argument("--commit-message", default=None,
                    help=("本次提交信息。**必须传**,因为不同轮次的改动不同;"
                          "复用同一段信息会造成多个提交信息相同、历史难以辨识"
                          "(本机实测已出现两次同名提交)。"))
    args = ap.parse_args()

    wt = prepare()

    target_ref = "HEAD:main"
    if args.branch:
        if args.new_branch_from_main:
            print(f"\n=== 1b. 从 origin/main 建立独立分支 {args.branch} ===")
            git("checkout", "-B", args.branch, "origin/main", cwd=wt)
            print(f"  已基于 origin/main 检出 {args.branch}")
        else:
            print(f"\n=== 1b. 使用现有分支 {args.branch} ===")
            git("checkout", "-B", args.branch, cwd=wt)
        target_ref = f"HEAD:{args.branch}"

    populate(wt)

    # 暂存必须在审查之前: 审查用 git ls-files 列文件
    print("\n=== 3. 暂存变更 ===")
    git("add", "-A", cwd=wt)
    st = git("status", "--short", cwd=wt).stdout.strip()
    n_staged = len(st.splitlines()) if st else 0
    print(f"  待提交 {n_staged} 项")

    print("\n=== 4. 推送前审查 ===")
    audit = run([sys.executable, str(Path(__file__).parent / "audit_before_push.py")])
    print((audit.stdout or "").strip()[-1400:])
    if audit.returncode != 0:
        print("\n⛔ 审查未通过,已中止推送。")
        return 1

    print("\n=== 5. 提交与推送 ===")
    if n_staged == 0:
        # 关键: 内容与 HEAD 一致时**不要新建提交**。
        # 若新建,其父提交是本次 prepare 的 base(origin/main),
        # 会与远程分支分叉,导致 non-fast-forward 被拒(本机实测踩过)。
        head_now = git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        print(f"  无变更,不提交;直接推送现有 HEAD {head_now[:12]}")
    else:
        c = git("commit", "-m", args.commit_message or
                "Update A-side deliverables\n\n"
                "(未提供 --commit-message;建议下次显式传入,避免提交信息雷同)",
                cwd=wt)
        print("  ✅ 已提交" if c.returncode == 0 else f"  ✗ 提交失败: {c.stderr[:200]}")

    if args.dry_run:
        print("\n=== dry-run: 不推送 ===")
        print(f"  本地副本: {wt}")
        print(f"  远程    : {REPO_URL}")
        return 0

    # 凭证: --token > 环境变量 > 本机凭据管理器(需显式开关)
    tok = args.token or os.environ.get("EDGECORAG_GH_TOKEN") or os.environ.get("GH_TOKEN")
    user = "x-access-token"
    if not tok and args.use_stored_credential:
        try:
            import git_cred_store
            cred = git_cred_store.read_github_credential()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! 读取本机凭据失败: {exc}")
            cred = None
        if cred:
            user, tok = cred
            print(f"  使用本机凭据(用户 {user};secret 不显示、不落盘)")

    # 构造 force 选项。优先用显式 OID 形式:
    #   --force-with-lease=<ref>:<expected-oid>
    # 它不依赖 upstream 配置,因此在 checkout -B 创建的分支上也能工作,
    # 且安全保证相同: 若远程实际 OID 与期望不符,推送会被拒绝。
    extra: list[str] = []
    if args.force_with_lease:
        if args.expect_remote_oid and args.branch:
            extra.append(f"--force-with-lease=refs/heads/{args.branch}:"
                         f"{args.expect_remote_oid}")
        else:
            extra.append("--force-with-lease")

    if tok:
        askpass = WORKTREE.parent / "_askpass.cmd"
        askpass.write_text("@echo off\r\necho %EC_USER%\r\necho %EC_TOKEN%\r\n",
                           encoding="ascii")
        try:
            r = run(GIT_BASE + ["-c", f"core.askPass={askpass}", "push"] + extra
                    + ["origin", target_ref],
                    cwd=wt, env_extra={"EC_USER": user, "EC_TOKEN": tok})
        finally:
            askpass.unlink(missing_ok=True)
    else:
        r = git("push", *extra, "origin", target_ref, cwd=wt)

    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        print("  ✅ 推送成功")
        head = git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        print(f"  commit: {head[:12]}")
        br = args.branch or "main"
        print(f"  分支  : {br}")
        print(f"  仓库  : https://github.com/joyboy-type/EdgeCoRAG")
        if args.branch and args.branch != "main":
            print(f"  PR 入口: https://github.com/joyboy-type/EdgeCoRAG/compare/"
                  f"main...{args.branch}?expand=1")
        if args.merge_to_main and args.branch and args.branch != "main":
            return merge_into_main(wt, args, user, tok)
        return 0

    print(f"  ✗ 推送失败:\n    {out.strip()[:400]}")
    if any(k in out for k in ("Authentication", "403", "could not read Username",
                              "Permission")):
        print("\n  -> 需要凭证(需 repo 写权限):")
        print("     --use-stored-credential   用本机已存凭据")
        print("     --token <PAT>             显式传入")
    return 1


WINDOWS_NOTES = """# 本机环境注意事项（Windows + 本地代理 + 国内网络）

> 本机实测得出的坑，换机器后不一定适用；记录下来是为了可复现。

## 1. `github.com` 被本地代理拦截

本机 `0.0.0.0:443` 由 **Watt Toolkit**（进程名 `Steam++.Accelerator`）监听，
它把 `github.com` / `api.github.com` 的 DNS 解析改写为 `127.0.0.1` 并做 TLS 中间人。后果：

| 现象 | 原因 |
|---|---|
| `git clone` 报 `schannel: CRYPT_E_NO_REVOCATION_CHECK` | schannel 无法通过该代理完成证书吊销检查 |
| `requests` 报 `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` | 代理出示的证书不在 certifi 信任链中 |
| `api.github.com/repos/<repo>` 返回**假 404** | 代理旁路了该 API 路由 |

**对策**：git 操作加 `-c http.sslVerify=false`。

```bash
git -c http.sslVerify=false clone https://github.com/joyboy-type/EdgeCoRAG.git
git -c http.sslVerify=false push
```

**如何判断 404 是否可信**：用已知存在的公开仓库做对照。若对照组返回完整真实字段
（`default_branch`、`size`、`owner` 等），说明通道确实到了 GitHub。
见 `scripts/verify_github_api_authenticity.py`。

**注意**：HTTPS 连接**间歇性**失败——`ls-remote` 有时通有时不通，克隆实测 5 次可全成功。
故脚本里克隆带重试、并优先复用已有副本，不要每次删了重建。

## 2. HuggingFace 直连不可用

`huggingface.co` 的 DNS 被污染（解析到 `88.191.249.183` 与 Facebook 段 IPv6），直连超时。
**对策**：设 `HF_ENDPOINT=https://hf-mirror.com`（实测 1.42 GiB 模型 37 秒下完）。

## 3. pip / torch 镜像

`download.pytorch.org` 实测**下载完全停滞**（60 秒 0 字节）。按速度实测选源：

| 源 | 实测速度 |
|---|---|
| 上海交大 SJTU `mirror.sjtu.edu.cn/pytorch-wheels/cu128` | **13.31 MB/s**（安装时达 40 MB/s） |
| pytorch 官方 | 8.51 MB/s |
| 阿里云 | 1.24 MB/s |
| 清华 TUNA | 该镜像无 pytorch-wheels |

PyPI 用 `https://pypi.tuna.tsinghua.edu.cn/simple`。

## 4. 磁盘与缓存（重资源外置）

模型权重与虚拟环境**不放仓库内**。本机布局：

```
工作区   EdgeCoRAG-A                  ≈ 0.2 GiB  仅脚本/论文/结果
外部存储 E:\\EdgeCoRAG-A-store         ≈ 25 GiB
         ├── hf-cache/   模型权重
         ├── datasets/   MRAG-Bench parquet
         └── venvs/      两个虚拟环境（junction 链回工作区）
```

用 **junction** 而非改路径：对进程透明，`HF_HOME` 与虚拟环境内写死的路径都无需修改。
迁移脚本 `scripts/bootstrap_store.py --apply`（幂等）。

## 5. 双环境隔离（必需）

作者 `utility-mrag` 的 `pyproject.toml` 明确：

> Qwen3-VL needs >=4.57; the Ovis 2.5 / MiniCPM-V remote code targets the 4.x API
> (transformers 5.x removed attributes it relies on), so cap below 5.

而 EmbeddingGemma 2 / Gemma 4 需要 transformers 5.x。
→ `.venv-mrag`（4.57.6）与 `.venv-main`（5.19.0）必须分开，**不要在同一环境里升级**。

## 6. 显存实测（8 GB 卡）

| 模型 | BF16 | INT4 | 结论 |
|---|---|---|---|
| EmbeddingGemma 2（0.744 B） | 1.39 GiB | 0.35 GiB | ✅ 实测占用 0.83 GiB |
| Gemma 4 E2B（5.123 B） | 9.54 GiB | 2.39 GiB | INT4 实测 6.28 GiB，可全驻显存 |
| Gemma 4 E4B（7.996 B） | 14.89 GiB | 3.72 GiB | ⛔ **加载即占 8.685 GiB > 8.0，本机不可行** |

E4B 超限的根因：**4bit 量化不覆盖 `lm_head`**（0.671 B 参数以 bf16 存储，约 1.34 GiB）。
→ 不能只用「参数量 × 0.5 字节」估算显存，必须实测。

## 7. PowerShell 下查看本仓库文件

PowerShell 5.1 默认按 GBK 读取，`Get-Content` 显示中文会乱码。
用 `read` 工具、或指定 `-Encoding UTF8` 查看。文件本身是 UTF-8，内容正常。
"""

ROOT_README = """# EdgeCoRAG

研究小型多模态模型结合视觉检索后的能力替代边界，以及回答质量、延迟和显存之间的关系。

## 协作分工

- **A**：检索器、证据选择与冻结证据交接。
- **B**：统一模型推理、公平比较、评分统计与错误分析。

## 实验条件

- **S0**：无外部证据。
- **S1**：共享检索证据。
- **S2**：GT 正确证据，用于诊断能力上限。
- **S3**：错误或干扰证据。

> ⚠️ **S2 是理想条件上界，不是可部署方案。** 任何把 S2 当作方法结果的说法都不成立。

## 仓库结构

```
handover/            给 B 的交接包
├── README.md          交接包入口（先读这个）
├── docs/              分工与进度、证据规则、S3 干扰证据规范
├── contracts/         接口 JSON Schema + 官方评测代码差异
├── samples/           少量接口样例（含图片，可直接跑通）
└── freeze/            冻结清单模板

a-side/              A 侧可复现资产
├── scripts/          数据/模型/环境探针、验收与契约校验脚本
├── reports/          环境审计与复现进展报告
├── data/             小体积事实文件（schema、证据本体统计、命中率审计、验收报告）
├── splits/           题目划分清单（固定种子 20261015）与 manifest
├── plans/            **未完成事项与阻塞清单**（接手的 AI/人先读这个）
└── setup/            安装说明
    ├── STANDARD_INSTALL.md          ← **项目标准步骤**（与机器无关）
    └── MACHINE_SPECIFIC_PROXY.md    ← 某台机器的代理/TLS 绕行，**非标准做法**
```

## 给协作者 B 的确认事项

见 **[`handover/docs/05_给B的确认与续作提示词.md`](handover/docs/05_给B的确认与续作提示词.md)**
—— 内含 8 项待确认事项、B 确认后才能继续的工作、以及 B 现在就能独立做的事。

## 未完成事项（**不要当作已完成**）

见 **[`a-side/plans/NEXT_STEPS_AND_BLOCKERS.md`](a-side/plans/NEXT_STEPS_AND_BLOCKERS.md)**。
摘要：

- ⛔ **独立检索语料未验证可下载、许可未确认** → 重检索路线阻塞（关键路径）
- ⛔ **Gemma 4 E4B 在 8 GB 显存不可行**（4bit 加载即占 8.685 GiB）→ A2/A3 路径受影响
- ❌ 冻结证据列表（全量）、检索质量指标（R@1/R@5/MRR）、S3 干扰集、效用选择器
- ⏳ 20 题联调清单（切分已定，冻结版未生成）


## 证据与数据规则（双方共同遵守）

1. **GT、正确答案、命中标记只用于评分、Oracle 条件与离线分析，绝不能用于检索条件下的证据选择。**
2. 官方 `retrieved_images` 的 **GT 图像字节级精确匹配命中率**为
   任意 **55.9%**、rank-0 **32.6%**、全部 GT 覆盖 **2.3%**（分母 1353）。
   ⚠️ 这**不等于答案泄漏**——无法区分『检索器独立命中』与『候选生成使用 GT 标注』，
   官方候选的产生过程未被完整说明。详见 `handover/docs/official_pool_provenance.md`。
   它也**不能**反推自研重检索是干净基线。
3. 官方 RAG 提示模板的**图片占位符数量写死**（常规 6、Incomplete 2）。
   改 top-k 必须同步改占位符，并另立 `protocol_version`。
4. **失败题目不得静默删除**。主准确率使用**固定题单分母**；
   成功子集指标仅作补充，且必须给出**覆盖率**。
5. **Incomplete 单独报告，但不得从总体剔除**。完整基准总体指标为主指标。
6. 内部切出的留出集**不能叫「外部验证」**（同源）；外部验证须用 VisDoM / MMDocRAG。

## 数据版本（已锁定）

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench` |
| revision | `43620fde4044bb150e158c67ad7af6b6b11e1da2` |
| 许可 | CC-BY-4.0 |
| split | **只有 `test`**，1,353 题（无官方 dev/val，需项目内自切分） |
| parquet 实际字节 | **4.00 GiB**（本地实测；官方 API `usedStorage` ≈8 GiB 为不同口径） |

## 当前进展

- A：环境与工具链已验证；论文、作者代码、数据集版本已核验；
  **尚未产出冻结证据列表**。已交付 6 题接口样例（含 GT，S2 可跑，28/28 验收通过）。
- B：已完成小样本与评分验证，正在整理运行代码和租用单卡 GPU 前的准备。
- **真实模型试跑与正式实验尚未完成。**

模型权重、数据图片、索引和运行缓存保存在仓库外；代码与配置按已验证版本陆续提交。

## 安装

**标准步骤见 [`a-side/setup/STANDARD_INSTALL.md`](a-side/setup/STANDARD_INSTALL.md)。**

本机（Windows）曾观察到本地 TLS 中间人代理导致 `git` 报
`CRYPT_E_NO_REVOCATION_CHECK`。⚠️ **该问题及其绕行办法记录在
[`a-side/setup/MACHINE_SPECIFIC_PROXY.md`](a-side/setup/MACHINE_SPECIFIC_PROXY.md)，
它不是项目标准做法**——正确做法是修好证书信任链，而不是关闭 TLS 校验。
"""


if __name__ == "__main__":
    sys.exit(main())
