"""成本计时记录器（A 侧统一外层计时入口的可对接件）。

设计原则（任务 3 + 审阅补充 A1/A2）：
  1. **分段时间与端到端分开**：端到端必须由外层单一计时器测一次；分段时间只用于分解，
     不允许相加后冒充端到端。
  2. **同名指标口径单一**：字段名沿用已发布 smoke 回执里的组件名。
  3. **只在实测时产出数值**：未测的段不写 0，而写进 `unmeasured_segments`。
  4. **整卡显存 / 系统 RAM / 能耗**：本模块不产生，只能由外部实测注入
     （`resources()` 行内注入 或 `attach_resources()` 后处理）。注入值必须带
     `value/unit/method`，且 `method` 不得是分配器口径。
  5. **CPU 线程必填**：`provenance["hardware"]["cpu_thread_env"]` 必须是正整数（记录生效值）
     或字符串 `"unfixed"`（未固定，会在每条记录的 `unmeasured_provenance` 留痕，正式基准
     不得采信）。缺项、"auto"、空串、0、负值一律拒绝构造。

不依赖 torch：需要 CUDA 同步时由调用方传入 `sync` 回调。

用法（A 侧检索段）：
    prov = {
        "hardware": {"gpu": "RTX 4060 Laptop", "vram_gib": 8, "cpu_thread_env": 8},
        "encoder": {"model": "google/embeddinggemma-2", "revision": "914f...", "dtype": "fp32"},
        "corpus": {"corpus_version": "corpus_v1", "rows": 4712},
        "protocol": "a-side/retrieval-interface-v1",
        "warm_state": "warm",
    }
    rec = CostRecorder(out_path="cost.jsonl", run_id="r1", provenance=prov,
                       sync=lambda: torch.cuda.synchronize())
    with rec.request("mragb:10", strategy="cosine"):
        with rec.segment("query_decode_encode_seconds"):
            emb = encode_query(img)
        with rec.segment("ranking_no_self_seconds"):
            cand = search(emb)
        with rec.segment("selection_request_build_seconds"):
            ev = select(cand)
        rec.resources(device_memory={"value": 7.1, "unit": "GiB",
                                     "method": "nvidia-smi --query-gpu=memory.used 10Hz"})
    rec.close()
"""

from __future__ import annotations

import copy
import json
import re
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
RESOURCE_KEYS = ("device_memory", "system_ram", "energy")

# 分配器口径不允许冒充整卡 / 系统 RAM / 能耗实测值
_ALLOCATOR_PATTERN = re.compile(
    r"allocat|memory_allocated|memory_reserved|reserved_peak|torch\.cuda\.memory", re.IGNORECASE
)


# ---------------------------------------------------------------- 校验工具
class ProvenanceError(ValueError):
    """provenance 不满足必填口径。"""


class ResourceError(ValueError):
    """外部注入的资源实测值不满足口径。"""


def normalize_cpu_thread_env(value: Any) -> tuple[int | str, str | None]:
    """返回 (规范化值, 未测说明)。

    合法：正整数（实际生效线程数）或 "unfixed"（未固定，留痕）。
    非法：缺失、"auto"、空串/空白、0、负值、bool、其他类型。
    """
    if isinstance(value, bool):
        raise ProvenanceError(
            "hardware.cpu_thread_env 不能是布尔值；请给生效线程数（正整数）或 \"unfixed\""
        )
    if isinstance(value, int):
        if value <= 0:
            raise ProvenanceError(f"hardware.cpu_thread_env 必须是正整数，收到 {value}")
        return value, None
    if isinstance(value, str):
        s = value.strip()
        if s == "unfixed":
            return "unfixed", (
                "hardware.cpu_thread_env=unfixed：CPU 线程未固定，该记录只作技术联调，"
                "不得进入正式基准或对外报告"
            )
        if not s:
            raise ProvenanceError("hardware.cpu_thread_env 不能是空字符串")
        if s.lower() == "auto":
            raise ProvenanceError(
                "hardware.cpu_thread_env=\"auto\" 不可接受：必须记录实际生效线程数或显式 \"unfixed\""
            )
        raise ProvenanceError(f"hardware.cpu_thread_env 只接受正整数或 \"unfixed\"，收到 {s!r}")
    raise ProvenanceError(
        f"hardware.cpu_thread_env 类型不受支持：{type(value).__name__}（只接受 int 或 \"unfixed\"）"
    )


def validate_measurement(name: str, value: Any) -> dict:
    """校验外部实测资源值：value/unit/method 齐全，且 method 不得是分配器口径。"""
    if not isinstance(value, dict):
        raise ResourceError(f"{name} 必须是对象（含 value/unit/method），收到 {type(value).__name__}")
    missing = [k for k in ("value", "unit", "method") if k not in value]
    if missing:
        raise ResourceError(f"{name} 缺少字段 {missing}；未测请留 null，不得用 0 或空对象代替")
    v = value["value"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ResourceError(f"{name}.value 必须是数值，收到 {type(v).__name__}")
    if v < 0:
        raise ResourceError(f"{name}.value 不能为负：{v}")
    for k in ("unit", "method"):
        if not isinstance(value[k], str) or not value[k].strip():
            raise ResourceError(f"{name}.{k} 必须是非空字符串")
    if _ALLOCATOR_PATTERN.search(value["method"]):
        raise ResourceError(
            f"{name}.method 命中分配器口径（{value['method']!r}）：分配器峰值不得改名为"
            "整卡/系统 RAM/能耗指标，请改用外部实测方法"
        )
    return {"value": v, "unit": value["unit"].strip(), "method": value["method"].strip()}


# ---------------------------------------------------------------- 记录器
@dataclass
class _Req:
    req_id: str
    attrs: dict[str, Any] = field(default_factory=dict)
    segments: dict[str, float] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    unmeasured: list[str] = field(default_factory=list)
    resources: dict[str, dict] = field(default_factory=dict)
    e2e: float | None = None


class CostRecorder:
    def __init__(self, out_path: str | Path, run_id: str, provenance: dict[str, Any],
                 sync: Callable[[], None] | None = None):
        missing = [k for k in REQUIRED_PROVENANCE if k not in provenance]
        if missing:
            raise ProvenanceError(f"provenance 缺少必填项: {missing}")
        hw = provenance.get("hardware")
        if not isinstance(hw, dict):
            raise ProvenanceError("provenance['hardware'] 必须是对象，且包含 cpu_thread_env")
        if "cpu_thread_env" not in hw:
            raise ProvenanceError(
                "provenance['hardware']['cpu_thread_env'] 必填：给生效线程数（正整数）或 \"unfixed\""
            )
        cpu_val, cpu_note = normalize_cpu_thread_env(hw["cpu_thread_env"])

        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.provenance = copy.deepcopy(provenance)
        self.provenance["hardware"]["cpu_thread_env"] = cpu_val
        self.unmeasured_provenance: list[str] = [cpu_note] if cpu_note else []
        self.sync = sync
        self._fh = self.out_path.open("w", encoding="utf-8")
        self._cur: _Req | None = None
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
        try:
            yield
        finally:
            if self.sync:
                self.sync()
            dt = time.perf_counter() - t0
            if name in self._cur.segments:
                raise RuntimeError(f"同一请求内重复段 {name}；重复测量请用 repeat 字段")
            self._cur.segments[name] = dt

    def mark(self, name: str) -> None:
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

    # ---------------------------------------------------------------- 资源（外部实测注入）
    def resources(self, *, device_memory: Any = None, system_ram: Any = None,
                  energy: Any = None) -> None:
        """注入当前请求的外部实测资源值。null 表示未测；不得用 0 或分配器峰值代替。"""
        if self._cur is None:
            raise RuntimeError("resources 必须在 request 内调用")
        provided = {"device_memory": device_memory, "system_ram": system_ram, "energy": energy}
        if all(v is None for v in provided.values()):
            raise ResourceError("resources 至少需要注入一项；全部未测时不要调用")
        for name, val in provided.items():
            if val is None:
                continue
            self._cur.resources[name] = validate_measurement(name, val)

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
                        "provenance": self.provenance,
                        "unmeasured_provenance": self.unmeasured_provenance})

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
            "unmeasured_provenance": list(self.unmeasured_provenance),
            "component_sum_seconds": round(component_sum, 9),
            "component_exceeds_e2e": bool(cur.e2e is not None and component_sum > cur.e2e + 1e-6),
            "device_memory": cur.resources.get("device_memory"),
            "system_ram": cur.resources.get("system_ram"),
            "energy": cur.resources.get("energy"),
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
            "cpu_thread_env": self.provenance["hardware"]["cpu_thread_env"],
            "unmeasured_provenance": list(self.unmeasured_provenance),
            "resources_present": {k: sum(1 for r in reqs if r.get(k) is not None)
                                  for k in RESOURCE_KEYS},
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


def attach_resources(jsonl_path: str | Path, provider: Callable[[str, dict], dict],
                     out_path: str | Path | None = None) -> dict:
    """后处理器：按 req_id 合并外部实测资源值。

    provider(req_id, row) -> 可含 device_memory / system_ram / energy（缺项视为未测）。
    只覆盖非 null 值；null 保持 null（未测不得写成 0）。
    """
    src = Path(jsonl_path)
    dst = Path(out_path) if out_path else src.with_name(src.name + ".resources.jsonl")
    rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    filled = {k: 0 for k in RESOURCE_KEYS}
    still_null = {k: 0 for k in RESOURCE_KEYS}
    missing_req: list[str] = []
    with dst.open("w", encoding="utf-8") as fh:
        for row in rows:
            if row.get("kind") == "request":
                got = provider(row["req_id"], row) or {}
                if not got:
                    missing_req.append(row["req_id"])
                for name in RESOURCE_KEYS:
                    val = got.get(name)
                    if val is None:
                        if row.get(name) is None:
                            still_null[name] += 1
                        continue
                    row[name] = validate_measurement(name, val)
                    filled[name] += 1
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"in": str(src), "out": str(dst), "rows": len(rows),
            "filled": filled, "still_null": still_null, "missing_req_ids": missing_req}


def _stats(vals: list[float]) -> dict | None:
    if not vals:
        return None
    v = sorted(vals)
    n = len(v)

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return v[idx]

    return {"n": n, "min": round(v[0], 9), "p50": round(pct(0.5), 9),
            "p95": round(pct(0.95), 9) if n >= 20 else None,
            "max": round(v[-1], 9), "mean": round(sum(v) / n, 9),
            "p95_note": None if n >= 20 else "观测数 <20，不报 P95"}


if __name__ == "__main__":
    print(json.dumps(SEGMENTS, indent=2, ensure_ascii=False))
