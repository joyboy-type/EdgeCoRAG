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
    "git_cred_store.py", "check_stored_git_credential.py",
]
KEEP_REPORTS = ["audit_env.md", "A_P0_P1.md",
                "requirements-main.lock.txt", "requirements-mrag.lock.txt"]
KEEP_DATA = [
    ("outputs/dataset_probe/mrag_bench_schema.json", "mrag_bench_schema.json"),
    ("outputs/dataset_probe/evidence_ontology.json", "evidence_ontology.json"),
    ("outputs/gemma4_probe/tokenizer_check.json", "gemma4_tokenizer_check.json"),
    ("outputs/gemma4_probe/vram_diagnosis_gemma-4-E4B-it.json", "vram_diagnosis_e4b.json"),
    ("source_manifest.csv", "source_manifest.csv"),
]


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

    (dst_a / "setup" / "WINDOWS_PROXY_NOTES.md").write_text(WINDOWS_NOTES,
                                                           encoding="utf-8")
    (wt / "README.md").write_text(ROOT_README, encoding="utf-8")
    print("  README.md 已更新")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只准备+审查,不推送")
    ap.add_argument("--token", default=None, help="GitHub PAT(仅本次使用)")
    ap.add_argument("--use-stored-credential", action="store_true",
                    help="使用本机 Windows 凭据管理器中的 git 凭证")
    args = ap.parse_args()

    wt = prepare()
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
        print("  无变更可提交")
    else:
        c = git("commit", "-m",
                "Add A-side retrieval deliverables and B handover package\n\n"
                "- handover/: 分工与进度、证据规则、S3 干扰规范、接口 JSON Schema、5 题样例\n"
                "- a-side/scripts: 数据集/模型/环境探针与契约校验脚本\n"
                "- a-side/reports: 环境审计与复现进展报告\n"
                "- a-side/setup: 本机代理/证书/镜像注意事项\n"
                "- 记录 MRAG-Bench 版本锁定与官方池 55.9% GT 泄漏的实测结论",
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

    if tok:
        askpass = WORKTREE.parent / "_askpass.cmd"
        askpass.write_text("@echo off\r\necho %EC_USER%\r\necho %EC_TOKEN%\r\n",
                           encoding="ascii")
        try:
            r = run(GIT_BASE + ["-c", f"core.askPass={askpass}", "push", "origin",
                                "HEAD:main"],
                    cwd=wt, env_extra={"EC_USER": user, "EC_TOKEN": tok})
        finally:
            askpass.unlink(missing_ok=True)
    else:
        r = git("push", "origin", "HEAD:main", cwd=wt)

    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        print("  ✅ 推送成功")
        head = git("rev-parse", "HEAD", cwd=wt).stdout.strip()
        print(f"  commit: {head[:12]}")
        print(f"  仓库  : https://github.com/joyboy-type/EdgeCoRAG")
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
├── scripts/          数据/模型/环境探针与样例生成脚本
├── reports/          环境审计与复现进展报告
├── data/             小体积事实文件（schema、证据本体统计、源清单）
└── setup/            本机环境注意事项（代理、证书、镜像）
```

## 证据与数据规则（双方共同遵守）

1. **GT、正确答案、命中标记只用于评分、Oracle 条件与离线分析，绝不能用于检索条件下的证据选择。**
2. 官方 `retrieved_images` 中 **55.9%** 的题已含 GT 正确证据（场景间 6.9%–81.7%），
   因此**不能当作干净检索基线**；跨场景对比会失真。
3. 官方 RAG 提示模板的**图片占位符数量写死**（常规 6、Incomplete 2）。
   改 top-k 必须同步改占位符，并另立 `protocol_version`。
4. **失败题目不得静默删除**，需保留并记录 `status`，同时报告两个分母。

## 数据版本（已锁定）

| 项 | 值 |
|---|---|
| 数据集 | `uclanlp/MRAG-Bench` |
| revision | `43620fde4044bb150e158c67ad7af6b6b11e1da2` |
| 许可 | CC-BY-4.0 |
| split | **只有 `test`**，1,353 题（无官方 dev/val，需项目内自切分） |

## 当前进展

- A：环境与工具链已验证；论文、作者代码、数据集版本已核验；
  **尚未产出冻结证据列表**。已交付 5 题接口样例供 B 联调。
- B：已完成小样本与评分验证，正在整理运行代码和租用单卡 GPU 前的准备。
- **真实模型试跑与正式实验尚未完成。**

模型权重、数据图片、索引和运行缓存保存在仓库外；代码与配置后续按已验证版本陆续提交。

## 本机环境注意（Windows + 本地代理）

本机 `github.com` 被 **Watt Toolkit（`Steam++.Accelerator`）** 在 `0.0.0.0:443` 本地拦截，
schannel 无法完成吊销检查，会报 `CRYPT_E_NO_REVOCATION_CHECK`。克隆/推送需要：

```bash
git -c http.sslVerify=false clone https://github.com/joyboy-type/EdgeCoRAG.git
```

详细说明见 `a-side/setup/WINDOWS_PROXY_NOTES.md`。
"""


if __name__ == "__main__":
    sys.exit(main())
