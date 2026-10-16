"""生成外置材料清单（大小 / SHA-256 / 获取方式）。

**为什么要外置 + 清单**

模型权重、数据集、图片包、索引合计约 40 GiB，不入库。
但"外置"不能变成"找不到"——因此必须有一份**可复验的清单**：
每个外置物件的稳定获取方式、版本、大小与内容 SHA-256。

清单本身入库（体积小），B 据此可：
  1. 判断自己是否已具备该物件；
  2. 用 SHA-256 校验取得的内容是否一致；
  3. 知道从哪里重新取得。

**同时产出逐文件哈希明细**（图片包文件多，单文件哈希另存 CSV）。

用法:
    python scripts/build_external_manifest.py
    python scripts/build_external_manifest.py --include-hashes
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

OUT = cfg.ROOT / "a-side-src" / "plans" / "EXTERNAL_ARTIFACTS.json"
OUT_DIR = cfg.ROOT / "a-side-src" / "data" / "external"


def dir_stats(p: Path) -> tuple[int, int]:
    if not p.exists():
        return 0, 0
    n = 0
    b = 0
    for f in p.rglob("*"):
        if f.is_file():
            n += 1
            b += f.stat().st_size
    return n, b


def _split_of(pkg_name: str) -> str:
    """从包名反推 split 名。"""
    for s in ("smoke_20", "dev", "internal_holdout", "frozen_test"):
        if pkg_name.startswith(s):
            return s
    return "unknown"


def agg_digest(paths: list[Path]) -> str:
    """对一组文件做确定性聚合哈希（按相对路径排序，逐个喂入路径+内容哈希）。"""
    h = hashlib.sha256()
    entries: list[tuple[str, Path]] = []
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    entries.append((str(f.relative_to(p)).replace("\\", "/"), f))
        elif p.is_file():
            entries.append((p.name, p))
    for rel, f in sorted(entries):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-hashes", action="store_true",
                    help="为图片包生成逐文件哈希 CSV")
    args = ap.parse_args()

    store = cfg.store_root()
    items: list[dict] = []

    # 1) 模型权重缓存
    hf = cfg.hf_home()
    n, b = dir_stats(hf)
    items.append({
        "id": "hf_model_cache",
        "kind": "model_weights",
        "description": "EmbeddingGemma 2 与 Gemma 4 E2B 权重（HF 缓存布局）",
        "path_hint": "由 $EDGECORAG_STORE/hf-cache 指定；HF_HOME 指向它",
        "files": n, "bytes": b,
        "how_to_obtain": [
            "export HF_ENDPOINT=https://hf-mirror.com（本机 huggingface.co DNS 被污染）",
            "python a-side/scripts/download_models.py --model embeddinggemma",
            "python a-side/scripts/download_models.py --model e2b",
        ],
        "models": [
            {"repo": "google/embeddinggemma-2", "revision": "914f7f89142e33e7",
             "params": "0.744 B", "approx_gb": 1.42},
            {"repo": "google/gemma-4-E2B-it", "revision": "3e22461f65e89153",
             "params": "5.123 B", "approx_gb": 9.57},
        ],
        "note": "Gemma 4 E4B 未下载：8 GB 显存实测不可行（4bit 加载即占 8.685 GiB）",
    })

    # 2) 数据集 parquet
    dsdir = store / "datasets" / "mrag_bench" / "43620fde4044bb150e158c67ad7af6b6b11e1da2"
    n, b = dir_stats(dsdir)
    items.append({
        "id": "mrag_bench_parquet",
        "kind": "dataset",
        "description": "MRAG-Bench test split parquet（28 个文件）",
        "path_hint": "$EDGECORAG_STORE/datasets/mrag_bench/43620fde.../",
        "files": n, "bytes": b,
        "how_to_obtain": [
            "export HF_ENDPOINT=https://hf-mirror.com",
            "python a-side/scripts/download_dataset.py",
        ],
        "dataset": {"repo": "uclanlp/MRAG-Bench",
                    "revision": "43620fde4044bb150e158c67ad7af6b6b11e1da2",
                    "license": "cc-by-4.0", "split": "test", "questions": 1353},
    })

    # 3) 证据包（S1/S2/S3，按题单可确定性重建）
    pkg_root = cfg.ROOT / "packages"
    pkg_items = []
    if pkg_root.exists():
        for sub in sorted(pkg_root.iterdir()):
            if not sub.is_dir():
                continue
            n, b = dir_stats(sub)
            meta = {}
            mp = sub / "package_meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    meta = {}
            cond = meta.get("condition")
            # 旧版 smoke_20（无 condition）是已被 S1/S2/S3 取代的接口样例，跳过
            if cond is None:
                print(f"  跳过旧包（无 condition，已被取代）: {sub.name}")
                continue
            is_s3 = (cond == "S3")
            kind = "distractor_package" if is_s3 else "evidence_package"
            pkg_items.append({
                "id": f"evidence_package_{sub.name}",
                "kind": kind,
                "description": meta.get("condition_description",
                                       meta.get("artifact_kind", "evidence package")),
                "name": sub.name,
                "condition": cond,
                "pool_id": meta.get("pool_id"),
                "package_version": meta.get("package_version"),
                "content_digest": meta.get("content_digest"),
                "content_digest_scope": meta.get("content_digest_scope"),
                "questions": meta.get("questions"),
                "coverage": meta.get("coverage_rate_full_3", meta.get("coverage_rate")),
                "path_hint": f"工作区 packages/{sub.name}/（可按题单重建）",
                "files": n, "bytes": b,
                "how_to_obtain": (
                    ["python a-side/scripts/build_distractor_package.py "
                     f"--list a-side/splits/{_split_of(sub.name)}.v2.txt "
                     f"--name {sub.name}",
                     "python a-side/scripts/finalize_s3_packages.py "
                     f"--dir packages/{sub.name}"]
                    if is_s3 else
                    ["python a-side/scripts/build_evidence_package.py "
                     f"--list a-side/splits/{_split_of(sub.name)}.v2.txt "
                     f"--name {sub.name} --condition {cond}"]),
                "rebuildable": True,
                "rebuild_note": "content_digest 可校验重建结果字节一致",
            })
    items.extend(pkg_items)

    # 4) 虚拟环境
    for name in ("venv-main", "venv-mrag"):
        vd = store / "venvs" / name
        n, b = dir_stats(vd)
        items.append({
            "id": name.replace("-", "_"),
            "kind": "python_env",
            "description": (".venv-main（transformers 5.x：EmbeddingGemma 2 / Gemma 4）"
                            if name == "venv-main"
                            else ".venv-mrag（transformers 4.x：作者代码；作者注释要求 <5）"),
            "path_hint": f"$EDGECORAG_STORE/venvs/{name}（工作区内以 junction 指向）",
            "files": n, "bytes": b,
            "how_to_obtain": [
                "python a-side/scripts/setup_env.py main",
                "python a-side/scripts/setup_env.py mrag",
            ],
            "lockfile": f"a-side/reports/requirements-{'main' if name == 'venv-main' else 'mrag'}.lock.txt",
        })

    manifest = {
        "script": "scripts/build_external_manifest.py",
        "purpose": ("外置材料清单：记录稳定获取方式、版本、大小与内容 SHA-256。"
                    "清单入库，物件本身不入库。"),
        "path_convention": {
            "env_var": "EDGECORAG_STORE",
            "default": str(cfg.store_root()),
            "resolution": "EDGECORAG_STORE -> HF_HOME -> 默认路径（见 a-side/scripts/project_config.py）",
            "portability_note": "**不绑定机器盘符**：设 EDGECORAG_STORE 即可整盘迁移",
        },
        "total_bytes": sum(i["bytes"] for i in items),
        "items": items,
        "unavailable": [
            {"id": "official_retrieval_corpus",
             "status": "not_obtained",
             "reason": ("本机网络无法访问 Google 系域名（drive/docs/www.googleapis.com 超时）；"
                        "许可亦未确认。详见 a-side/data/corpus_access.json"),
             "consequence": "独立重检索路线当前不具备可执行条件"},
            {"id": "gemma_4_E4B_weights",
             "status": "deliberately_not_downloaded",
             "reason": "8 GB 显存实测不可行；已删除以节省空间",
             "consequence": "A2/A3 路径需更大显存机器"},
        ],
        "deterministic": True,
        "generated_at": None,
        "generated_at_note": "故意不写墙上时钟，保证重跑字节一致。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {OUT}")
    for i in items:
        print(f"  {i['id']:32s} {i['files']:6d} 文件  {i['bytes'] / 1024 ** 2:9.1f} MiB")
    print(f"  {'合计':32s} {'':6s}        {manifest['total_bytes'] / 1024 ** 3:9.2f} GiB")

    if args.include_hashes and pkg.exists():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        csvp = OUT_DIR / "smoke_20_file_hashes.csv"
        rows = []
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                rows.append({"rel_path": str(f.relative_to(pkg)).replace("\\", "/"),
                             "bytes": f.stat().st_size,
                             "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
        with csvp.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["rel_path", "bytes", "sha256"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n-> {csvp}  ({len(rows)} 个文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
