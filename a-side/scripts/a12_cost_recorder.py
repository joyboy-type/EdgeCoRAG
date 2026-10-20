"""成本计时记录器（A 侧统一外层计时入口的可对接件）。

设计原则（对应本轮任务 3）：
  1. **分段时间与端到端分开**：端到端必须由外层（B 的 e2e 入口或本模块的 request 段）
     单一计时器测一次；分段时间只用于分解，不允许相加后冒充端到端。
  2. **同名指标口径单一**：字段名沿用已发布 smoke 回执里的组件名，避免双方出现
     同一概念两个字段。
  3. **只在实测时产出数值**：未测的段不写 0，而写 null 并在 `unmeasured` 中列出。
  4. **整卡显存/系统 RAM/能耗**：本模块不产生；必须由外部实测接口写入
     `device_memory` / `system_ram` / `energy` 三个可选块，缺失即 null。

不依赖 torch：需要 CUDA 同步时由调用方传入 `sync` 回调（通常是
`lambda: torch.cuda.synchronize()`），从而本模块可在纯 CPU 环境自检。

用法（A 侧检索段）：
    rec = CostRecorder(out_path="cost.jsonl", run_id="...", provenance={...})
    with rec.request("q1", strategy="cosine"):
        with rec.segment("query_decode_encode_seconds"):
            emb = encode_query(img)
        with rec.segment("ranking_no_self_seconds"):
            cand = search(emb)
        with rec.segment("selection_request_build_seconds"):
            ev = select(cand)
    rec.close()
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SEGMENTS = {
    # ---- 离线（只报一次，不进入在线请求）
    "corpus_encode_seconds": "语料全量编码（含解码与预处理），离线建库阶段",
    "index_build_seconds": "向量索引构建（归一化、矩阵落盘、可选 IVF/HNSW 训练）",
    "index_load_seconds": "索引从磁盘加载到常驻内存/显存的时间（冷启动）",
    # ---- 在线（每题）
    "query_decode_encode_seconds": "查询图像解码 + 预处理 + 编码器前向（含同步）",
    "ranking_no_self_seconds": "全库打分 + 无自匹配过滤 + 取 top-k",
    "utility_scoring_seconds": "候选逐个效用前向（含同步），与 selection 分开",
    "selection_request_build_seconds": "选择 3 张 + 请求组装（不含生成）",
    "switch_seconds": "路径/模型切换开销（A0↔A1↔A2↔A3），单列",
    "generation_decode_seconds": "生成与解码（B 侧主责，此处只接收其上报值）",
}
OFFLINE_SEGMENTS = {"corpus_encode_seconds", "index_build_seconds", "index_load_seconds"}
ONLINE_SEGMENTS = set(SEGMENTS) - OFFLINE_SEGMENTS

REQUIRED_PROVENANCE = ("hardware", "encoder", "corpus", "protocol", "warm_state")


@dataclass
class _Req:
    req_id: str
    attrs: dict[str, Any] = field(default_factory=dict)
    segments: dict[str, float] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    unmeasured: list[str] = field(default_factory=list)
    e2e: float | None = None


class CostRecorder:
    def __init__(self, out_path: str | Path, run_id: str, provenance: dict[str, Any],
                 sync: Callable[[], None] | None = None):
        missing = [k for k in REQUIRED_PROVENANCE if k not in provenance]
        if missing:
            raise ValueError(f"provenance 缺少必填项: {missing}")
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.provenance = provenance
        self.sync = sync
        self._fh = self.out_path.open("w", encoding="utf-8")
        self._cur: _Req | None = None
        self._stack: list[tuple[str, float, bool]] = []
        self.records: list[dict] = []

    # ---------------------------------------------------------------- 请求边界
    @contextmanager
    def request(self, req_id: str, **attrs: Any):
        if self._cur is not None:
            raise RuntimeError("不支持嵌套 request：端到端只能有一个外层计时器")
        cur = self._cur = _Req(req_id=req_id, attrs=attrs)
        if self.sync:
            self.sync()
        t0 = time.perf_counter()
        try:
            yield cur
        finally:
            if self.sync:
                self.sync()
            cur.e2e = time.perf_counter() - t0
            self._emit(cur)
            self._cur = None

    # ---------------------------------------------------------------- 分段
    @contextmanager
    def segment(self, name: str):
        if self._cur is None:
            raise RuntimeError("segment 必须在 request 内使用（离线段用 offline_segment）")
        if name not in SEGMENTS:
            raise KeyError(f"未定义的段名 {name}，允许: {sorted(SEGMENTS)}")
        if self.sync:
            self.sync()
        t0 = time.perf_counter()
        self._stack.append((name, t0, True))
        try:
            yield
        finally:
            n, t, _ = self._stack.pop()
            if self.sync:
                self.sync()
            dt = time.perf_counter() - t
            if n in self._cur.segments:
                raise RuntimeError(f"同一请求内重复段 {n}；重复测量请用 repeat 字段")
            self._cur.segments[n] = dt

    def mark(self, name: str) -> None:
        """打点，用于计算切换/连接等区间差。"""
        if self._cur is None:
            raise RuntimeError("mark 必须在 request 内")
        if self.sync:
            self.sync()
        self._cur.marks[name] = time.perf_counter()

    def unmeasured(self, *names: str) -> None:
        if self._cur is None:
            raise RuntimeError("unmeasured 必须在 request 内")
        for n in names:
            if n not in SEGMENTS:
                raise KeyError(f"未定义段名 {n}")
            self._cur.unmeasured.append(n)

    # ---------------------------------------------------------------- 离线段
    @contextmanager
    def offline_segment(self, name: str):
        if name not in OFFLINE_SEGMENTS:
            raise KeyError(f"离线段只允许 {sorted(OFFLINE_SEGMENTS)}")
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self._emit({"kind": "offline", "run_id": self.run_id, "segment": name,
                        "seconds": time.perf_counter() - t0,
                        "provenance": self.provenance})

    # ---------------------------------------------------------------- 输出
    def _emit(self, cur: _Req | dict) -> None:
        if isinstance(cur, dict):
            self._fh.write(json.dumps(cur, ensure_ascii=False) + "\n")
            self.records.append(cur)
            return
        component_sum = sum(cur.segments.values())
        rec = {
            "kind": "request",
            "run_id": self.run_id,
            "req_id": cur.req_id,
            "attrs": cur.attrs,
            "end_to_end_seconds": cur.e2e,
            "segments": {k: round(v, 9) for k, v in cur.segments.items()},
            "unmeasured_segments": sorted(cur.unmeasured),
            "component_sum_seconds": round(component_sum, 9),
            # 只做一致性诊断，不当作端到端
            "component_exceeds_e2e": bool(cur.e2e is not None and component_sum > cur.e2e + 1e-6),
            "device_memory": None,
            "system_ram": None,
            "energy": None,
            "provenance": self.provenance,
        }
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.records.append(rec)

    def close(self) -> Path:
        self._fh.close()
        return self.out_path

    # ---------------------------------------------------------------- 汇总
    def summary(self) -> dict:
        reqs = [r for r in self.records if r.get("kind") == "request"]
        offs = [r for r in self.records if r.get("kind") == "offline"]
        seg_names = sorted({k for r in reqs for k in r["segments"]})
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "requests": len(reqs),
            "offline_segments": {},
            "segments": {},
            "end_to_end": None,
            "violations": {
                "component_exceeds_e2e": sum(1 for r in reqs if r["component_exceeds_e2e"]),
            },
        }
        for o in offs:
            out["offline_segments"][o["segment"]] = round(o["seconds"], 9)
        for n in seg_names:
            vals = [r["segments"][n] for r in reqs if n in r["segments"]]
            out["segments"][n] = _stats(vals)
        e2e = [r["end_to_end_seconds"] for r in reqs if r["end_to_end_seconds"] is not None]
        out["end_to_end"] = _stats(e2e)
        out["unmeasured_segments"] = sorted({n for r in reqs for n in r["unmeasured_segments"]})
        return out


def _stats(vals: list[float]) -> dict | None:
    if not vals:
        return None
    v = sorted(vals)
    n = len(v)

    def pct(p: float) -> float:
        # 最近秩百分位，避免小样本插值造成的伪精确
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return v[idx]

    return {"n": n, "min": round(v[0], 9), "p50": round(pct(0.5), 9),
            "p95": round(pct(0.95), 9) if n >= 20 else None,
            "max": round(v[-1], 9), "mean": round(sum(v) / n, 9),
            "p95_note": None if n >= 20 else "观测数 <20，不报 P95"}


if __name__ == "__main__":
    print(json.dumps(SEGMENTS, indent=2, ensure_ascii=False))
