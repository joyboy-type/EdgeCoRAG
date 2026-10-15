"""实测各 pip / torch 镜像的下载速度,为环境安装选出最快源。

用法: python scripts/probe_mirrors.py
每个候选源只取固定字节数(默认 20 MB)并计时,不写盘。
"""

from __future__ import annotations

import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dsh-probe"}

# torch 2.11.0+cu128 / cp312 / win_amd64 的轮子在各方镜像上的路径
TORCH_WHEEL = ("torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl")
TORCH_INDEXES = {
    "pytorch 官方": "https://download.pytorch.org/whl/cu128",
    "上海交大 SJTU": "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128",
    "阿里云": "https://mirrors.aliyun.com/pytorch-wheels/cu128",
    "清华 TUNA": "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128",
}

PYPI_INDEXES = {
    "PyPI 官方": "https://pypi.org/simple/",
    "清华 TUNA": "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "阿里云": "https://mirrors.aliyun.com/pypi/simple/",
    "腾讯云": "https://mirrors.cloud.tencent.com/pypi/simple/",
}

PROBE_BYTES = 20 * 1024 * 1024


def time_download(url: str, limit: int = PROBE_BYTES, timeout: int = 25) -> tuple[float, int] | None:
    """下载至多 limit 字节,返回 (秒, 实际字节)。失败返回 None。"""
    try:
        t0 = time.time()
        got = 0
        with requests.get(url, headers=UA, stream=True, timeout=timeout) as r:
            if r.status_code != 200:
                return None
            for chunk in r.iter_content(1 << 18):
                got += len(chunk)
                if got >= limit or time.time() - t0 > timeout:
                    break
        return time.time() - t0, got
    except Exception:  # noqa: BLE001
        return None


def report(name: str, url: str, res: tuple[float, int] | None) -> float:
    if res is None:
        print(f"  FAIL  {name:16s} {url}")
        return 0.0
    secs, got = res
    mbs = got / secs / 1e6 if secs > 0 else 0.0
    print(f"  OK    {name:16s} {mbs:6.2f} MB/s  ({got / 1e6:.1f} MB in {secs:.1f}s)")
    return mbs


def main() -> int:
    print("=== torch 轮子镜像 (cu128) ===")
    torch_speeds: dict[str, float] = {}
    for name, base in TORCH_INDEXES.items():
        url = f"{base}/{TORCH_WHEEL}"
        torch_speeds[name] = report(name, url, time_download(url))

    print("\n=== PyPI 镜像 (取 pip 自身的小轮子探测) ===")
    pypi_speeds: dict[str, float] = {}
    # 用一个体积适中的纯 python 包探测: packaging
    probe_pkg = "packaging"
    for name, base in PYPI_INDEXES.items():
        url = f"{base}/{probe_pkg}/"
        try:
            r = requests.get(url, headers=UA, timeout=20)
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        print(f"  {'OK  ' if ok else 'FAIL'}  {name:16s} {url}")
        # 索引可达性即可,速度用 torch 源近似判断
        pypi_speeds[name] = 1.0 if ok else 0.0

    print("\n=== 结论 ===")
    good = {k: v for k, v in torch_speeds.items() if v > 0}
    if good:
        best = max(good, key=good.get)  # type: ignore[arg-type]
        print(f"torch 最快源: {best} ({good[best]:.2f} MB/s) -> {TORCH_INDEXES[best]}")
        if good[best] < 0.5:
            print("⚠️ 最快源仍低于 0.5 MB/s,2753 MB 的 torch 轮子需 "
                  f"{2753 / good[best] / 60:.0f} 分钟,建议改用 CPU 版或离线拷贝")
    else:
        print("✗ 所有 torch 镜像均不可用")
    ok_pypi = [k for k, v in pypi_speeds.items() if v > 0]
    print(f"PyPI 可达镜像: {', '.join(ok_pypi) if ok_pypi else '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
