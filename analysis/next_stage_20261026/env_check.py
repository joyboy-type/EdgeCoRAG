#!/usr/bin/env python3
"""环境核验：CUDA/nvcc、torch、Qwen3.5 所需的两个线性注意力扩展、目标模型权重。

用途：在任何补跑开始前记录硬件与栈事实，失败只报告缺什么，不改环境。
输出：stdout 打印人读摘要；--json <path> 写出机器可读回执。

判定（不满足即视为"不具备执行条件"，不自动安装）：
  - torch 版本与 CUDA runtime 必须能报出；
  - nvcc 必须存在且 major.minor 与 torch.version.cuda 一致（causal_conv1d 源码编译依赖）；
  - flash-linear-attention 必须可导入（Triton JIT，不需要 nvcc）；
  - Qwen3.5 模型类必须可导入（transformers 含 qwen3_5）；
  - 目标权重目录存在且 safetensors 片数符合预期。
"""
import argparse
import importlib.util
import re
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SPECS = {
    "qwen3vl_8b": {
        "repo": "Qwen/Qwen3-VL-8B-Instruct",
        "revision": "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        "shards": 4,
        "role": "S3-8B",
    },
    "qwen35_9b": {
        "repo": "Qwen/Qwen3.5-9B",
        "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "shards": 4,
        "role": "9B S0/S1/S2",
    },
}

# 候选权重根（续租原实例 / 新实例 / 本机）
WEIGHT_ROOTS = [
    "/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub",
    "/root/autodl-tmp/EdgeCoRAG/cache/huggingface",
    str(Path.home() / "cache/huggingface/hub"),
]


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {"rc": r.returncode, "out": (r.stdout or "").strip(), "err": (r.stderr or "").strip()[:300]}
    except Exception as e:  # noqa: BLE001
        return {"rc": -1, "out": "", "err": f"{type(e).__name__}: {e}"}


def has_module(name):
    return importlib.util.find_spec(name) is not None


def find_weights(repo, revision):
    """返回 (路径, 片数) 或 (None, 0)。容忍 snapshot 布局与 local_dir 扁平布局。"""
    dirname = "models--" + repo.replace("/", "--")
    for root in WEIGHT_ROOTS:
        base = Path(root) / dirname
        if not base.is_dir():
            continue
        # 标准 snapshots/<rev>
        snap = base / "snapshots" / revision
        if snap.is_dir():
            return str(snap), len(list(snap.glob("*.safetensors")))
        # 扁平 local_dir
        n = len(list(base.glob("*.safetensors")))
        if n:
            return str(base), n
        # Do not accept a different snapshot revision.
    return None, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/root/autodl-tmp/env_check_20261026.json")
    args = ap.parse_args()

    receipt = {
        "schema": "env_check_20261026/v1",
        "host": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "cuda": {},
        "packages": {},
        "weights": {},
        "verdict": {},
    }

    # --- torch ---
    torch_info = {"available": has_module("torch")}
    if torch_info["available"]:
        import torch  # local import: only when available
        torch_info.update({
            "version": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "bf16_supported": bool(torch.cuda.is_bf16_supported()) if torch.cuda.is_available() else False,
        })
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            torch_info.update({
                "gpu_name": torch.cuda.get_device_name(0),
                "gpu_total_bytes": props.total_memory,
                "gpu_total_gib": round(props.total_memory / 1024**3, 3),
                "compute_capability": list(torch.cuda.get_device_capability(0)),
            })
    receipt["packages"]["torch"] = torch_info

    # --- nvcc ---
    nvcc_path = shutil.which("nvcc")
    nvcc_info = {"path": nvcc_path}
    if nvcc_path:
        r = run([nvcc_path, "--version"])
        nvcc_info["version_raw"] = r["out"]
        # 解析 "release 12.8"
        match = re.search(r"release (\d+\.\d+)", r["out"])
        if match: nvcc_info["version"] = match.group(1)
    receipt["cuda"]["nvcc"] = nvcc_info

    # --- 其余包 ---
    for name, mod in [("transformers", "transformers"), ("triton", "triton"),
                      ("flash_linear_attention", "fla"), ("causal_conv1d", "causal_conv1d")]:
        info = {"module": mod, "present": has_module(mod)}
        if info["present"]:
            try:
                m = __import__(mod)
                info["version"] = getattr(m, "__version__", None)
            except Exception as e:  # noqa: BLE001
                info["import_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        receipt["packages"][name] = info

    # --- Qwen3.5 模型类 ---
    qwen35_class = {"present": False}
    if receipt["packages"]["transformers"]["present"]:
        try:
            from transformers import Qwen3_5ForConditionalGeneration  # noqa: F401
            qwen35_class["present"] = True
            qwen35_class["class"] = "Qwen3_5ForConditionalGeneration"
        except Exception as e:  # noqa: BLE001
            qwen35_class["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    receipt["packages"]["qwen3_5_class"] = qwen35_class

    # --- 权重 ---
    for key, spec in SPECS.items():
        path, n = find_weights(spec["repo"], spec["revision"])
        receipt["weights"][key] = {
            "repo": spec["repo"], "revision": spec["revision"],
            "expected_shards": spec["shards"], "found_path": path, "found_shards": n,
            "ok": bool(path) and n == spec["shards"],
        }

    # --- 判定 ---
    torch_ok = (torch_info.get("cuda_available", False) and torch_info.get("version") == "2.8.0+cu128" and torch_info.get("cuda_runtime") == "12.8" and torch_info.get("gpu_total_bytes",0) >= 32*1024**3)
    transformers_ok = str(receipt["packages"]["transformers"].get("version","")).startswith("5.19.") and "import_error" not in receipt["packages"]["transformers"]
    fla_ok = receipt["packages"]["flash_linear_attention"]["present"] and "import_error" not in receipt["packages"]["flash_linear_attention"]
    causal_ok = receipt["packages"]["causal_conv1d"]["present"] and "import_error" not in receipt["packages"]["causal_conv1d"]
    try:
        from transformers import Qwen3VLForConditionalGeneration
        vl_ok=True
    except Exception:
        vl_ok=False
    cap = receipt["packages"]["torch"].get("compute_capability") or [0, 0]
    bf16_ok = cap[0] >= 8 and torch_info.get("bf16_supported", False)
    cuda_ver = receipt["packages"]["torch"].get("cuda_runtime") or ""
    nvcc_ver = nvcc_info.get("version") or ""
    nvcc_ok = bool(nvcc_ver) and nvcc_ver == cuda_ver

    receipt["verdict"] = {
        "torch_cuda_ready": torch_ok,
        "native_bf16": bf16_ok,
        "nvcc_present": bool(nvcc_path),
        "nvcc_matches_torch_cuda": nvcc_ok,
        "fla_present": fla_ok,
        "causal_conv1d_present": causal_ok,
        "qwen3_5_class_present": qwen35_class["present"],
        "s3_8b_ready": receipt["weights"]["qwen3vl_8b"]["ok"] and torch_ok and bf16_ok and transformers_ok and vl_ok,
        "nine_b_ready": (receipt["weights"]["qwen35_9b"]["ok"] and torch_ok and bf16_ok
                         and nvcc_ok and qwen35_class["present"]
                         and fla_ok and causal_ok and transformers_ok),
    }

    # --- 打印 ---
    print("=" * 62)
    print("环境核验（补跑前置）")
    print("=" * 62)
    t = receipt["packages"]["torch"]
    print(f"GPU        : {t.get('gpu_name')}  ({t.get('gpu_total_gib')} GiB)  cc={t.get('compute_capability')}")
    print(f"torch      : {t.get('version')}  cuda={t.get('cuda_runtime')}  bf16={t.get('bf16_supported')}")
    print(f"nvcc       : {nvcc_info.get('version') or '缺失'}  ({nvcc_path or 'not found'})")
    print(f"transformers: {receipt['packages']['transformers'].get('version')}")
    print(f"triton     : {receipt['packages']['triton'].get('version')}")
    print(f"fla        : {receipt['packages']['flash_linear_attention'].get('version') or '缺失'}")
    print(f"causal_conv1d: {receipt['packages']['causal_conv1d'].get('version') or '缺失'}")
    print(f"Qwen3_5 类 : {'有' if qwen35_class['present'] else '无'}")
    for key, w in receipt["weights"].items():
        print(f"权重 {key:12s}: {w['found_shards']}/{w['expected_shards']} 片  {w['found_path'] or '未找到'}")
    print("-" * 62)
    v = receipt["verdict"]
    for k in ["torch_cuda_ready", "native_bf16", "nvcc_present", "nvcc_matches_torch_cuda",
              "fla_present", "causal_conv1d_present", "qwen3_5_class_present",
              "s3_8b_ready", "nine_b_ready"]:
        print(f"  {k:26s}: {'OK' if v[k] else 'NO'}")
    print("=" * 62)
    if not v["s3_8b_ready"]:
        print("S3-8B 不具备条件：需 ≥32GB 显存 + 原生 bf16 + 8B 权重 4 片；不得降精度/限 max_pixels。")
    if not v["nine_b_ready"]:
        missing = [n for n, ok in [("nvcc(与 torch CUDA 匹配)", v["nvcc_matches_torch_cuda"]),
                                   ("flash-linear-attention", v["fla_present"]),
                                   ("Qwen3_5 模型类", v["qwen3_5_class_present"]),
                                   ("9B 权重 4 片", receipt["weights"]["qwen35_9b"]["ok"])] if not ok]
        print("9B 不具备条件，缺：" + "、".join(missing))

    p = Path(args.json)
    if p.parent and str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"回执已写入 {p}")
    return 0 if (v["s3_8b_ready"] or v["nine_b_ready"]) else 3


if __name__ == "__main__":
    sys.exit(main())
