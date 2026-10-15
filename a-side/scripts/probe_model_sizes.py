"""精确读取 safetensors 元数据,得到真实参数量与各精度下的显存占用。

比 config.json 启发式估算可靠。经 hf-mirror.com 取 model.safetensors.index.json
或直接读 safetensors 头(Range 请求前若干字节)。
用法: python scripts/probe_model_sizes.py
"""

from __future__ import annotations

import json
import struct

import requests

MODELS = [
    "google/embeddinggemma-2",
    "google/gemma-4-E2B-it",
    "google/gemma-4-E4B-it",
]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dsh-probe"}
BASES = ["https://hf-mirror.com", "https://huggingface.co"]

# safetensors dtype -> 每参数字节数
DTYPE_BYTES = {
    "F64": 8, "F32": 4, "F16": 2, "BF16": 2, "I64": 8, "I32": 4,
    "I16": 2, "I8": 1, "U8": 1, "BOOL": 1, "F8_E4M3": 1, "F8_E5M2": 1,
}


def find_base() -> str:
    for b in BASES:
        try:
            r = requests.get(f"{b}/api/models/{MODELS[0]}", headers=UA, timeout=25)
            if r.status_code == 200:
                print(f"使用镜像: {b}")
                return b
        except Exception:  # noqa: BLE001
            continue
    raise SystemExit("无可用镜像")


def get_json(base: str, path: str) -> dict | None:
    try:
        r = requests.get(f"{base}/{path}", headers=UA, timeout=40)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return None


def safetensors_header(base: str, path: str) -> dict | None:
    """读 safetensors 前 8 字节得到 header 长度,再读 header(JSON)。"""
    url = f"{base}/{path}"
    try:
        h = requests.get(url, headers={**UA, "Range": "bytes=0-7"}, timeout=40)
        if h.status_code not in (200, 206):
            return None
        n = struct.unpack("<Q", h.content[:8])[0]
        if n <= 0 or n > 50_000_000:
            return None
        hh = requests.get(url, headers={**UA, "Range": f"bytes=8-{8 + n - 1}"}, timeout=60)
        return json.loads(hh.content.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def total_params_from_index(base: str, model: str) -> tuple[float, dict] | None:
    """从 index.json 的 weight_map + 各分片 header 统计总参数量。"""
    idx = get_json(base, f"{model}/resolve/main/model.safetensors.index.json")
    if not idx:
        return None
    wmap: dict = idx.get("weight_map") or {}
    if not wmap:
        return None
    shards = sorted(set(wmap.values()))
    print(f"  分片数: {len(shards)}")
    total_params = 0
    dtype_totals: dict[str, int] = {}
    for sh in shards:
        head = safetensors_header(base, f"{model}/resolve/main/{sh}")
        if not head:
            print(f"    ! 读取分片失败: {sh}")
            continue
        for name, meta in head.items():
            if name == "__metadata__":
                continue
            dt = meta.get("dtype", "")
            shape = meta.get("shape") or []
            n = 1
            for d in shape:
                n *= d
            total_params += n
            dtype_totals[dt] = dtype_totals.get(dt, 0) + n
    return total_params, dtype_totals


def single_file_params(base: str, model: str, fname: str) -> tuple[float, dict] | None:
    head = safetensors_header(base, f"{model}/resolve/main/{fname}")
    if not head:
        return None
    total = 0
    dtype_totals: dict[str, int] = {}
    for name, meta in head.items():
        if name == "__metadata__":
            continue
        dt = meta.get("dtype", "")
        shape = meta.get("shape") or []
        n = 1
        for d in shape:
            n *= d
        total += n
        dtype_totals[dt] = dtype_totals.get(dt, 0) + n
    return total, dtype_totals


def main() -> int:
    base = find_base()
    for m in MODELS:
        print(f"\n{'=' * 76}\n{m}\n{'=' * 76}")
        res = total_params_from_index(base, m)
        if res is None:
            print("  无 index.json,尝试单文件 model.safetensors")
            res = single_file_params(base, m, "model.safetensors")
        if res is None:
            print("  ✗ 无法读取 safetensors 元数据")
            continue
        total, dtypes = res
        print(f"  真实参数量 : {total / 1e9:.3f} B   ({total:,} 参数)")
        print(f"  存储精度   : {', '.join(f'{k}×{v / 1e9:.2f}B' for k, v in sorted(dtypes.items()))}")
        print("  显存/磁盘需求:")
        for label, bpp in (("FP32", 4), ("BF16/FP16", 2), ("INT8", 1), ("INT4", 0.5)):
            print(f"    {label:10s} ≈ {total * bpp / 1024 ** 3:6.2f} GiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
