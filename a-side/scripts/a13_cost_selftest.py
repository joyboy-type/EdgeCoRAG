"""计时记录器自检：不依赖 GPU / 模型，验证边界、口径与汇总规则。

覆盖的断言（对应本轮任务 3 的可验证部分）：
  1. 端到端只能有一个外层计时器（禁止嵌套 request）
  2. 分段时间不会自动被当成端到端；component 之和 > 端到端时被标记
  3. 同一请求内同名段重复会被拒绝（防止无意覆盖）
  4. 未测段写 null 并列入 unmeasured，不写 0
  5. 离线段与在线段分开，且离线不能混入在线汇总
  6. provence 必填项缺失时拒绝创建
  7. 观测数 <20 时不报 P95（并给出理由字符串）
  8. 设备显存 / 系统 RAM / 能耗默认 null（本模块不产生）

用法: python a-side/scripts/a13_cost_selftest.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a12_cost_recorder import CostRecorder  # noqa: E402


class _Dummy:
    """一个可测量的假分段负载（真实 CPU 计算 + 少量等待）。"""

    def __init__(self) -> None:
        import numpy as np
        self.np = np
        self.A = np.random.default_rng(42).normal(size=(256, 256)).astype("float32")

    def work(self, ms: float = 5.0) -> None:
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) * 1000 < ms:
            self.A @ self.A


def main() -> int:
    checks: list[dict] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(cond), "detail": detail})

    prov = {
        "hardware": {"gpu": "selftest-cpu", "vram_gib": None},
        "encoder": {"model": "dummy", "revision": "dummy"},
        "corpus": {"rows": 0},
        "protocol": "cost_recorder_selftest_v1",
        "warm_state": "n/a",
    }

    # 6) provenance 必填
    try:
        CostRecorder(Path(tempfile.gettempdir()) / "x.jsonl", "r0", {})
        ok("provenance_required", False)
    except ValueError:
        ok("provenance_required", True)

    tmp = Path(tempfile.mkdtemp()) / "cost.jsonl"
    d = _Dummy()
    rec = CostRecorder(tmp, run_id="selftest", provenance=prov)

    # 2) 正常请求 + 未测段
    with rec.request("q1", strategy="cosine") as cur:
        with rec.segment("query_decode_encode_seconds"):
            d.work(5)
        with rec.segment("ranking_no_self_seconds"):
            d.work(3)
        with rec.segment("selection_request_build_seconds"):
            d.work(1)
        rec.unmeasured("utility_scoring_seconds", "generation_decode_seconds")
    r = rec.records[0]
    ok("segments_recorded", set(r["segments"]) == {"query_decode_encode_seconds",
                                                   "ranking_no_self_seconds",
                                                   "selection_request_build_seconds"})
    ok("e2e_ge_component_sum", r["end_to_end_seconds"] >= r["component_sum_seconds"] - 1e-6,
       f"e2e={r['end_to_end_seconds']:.6f} sum={r['component_sum_seconds']:.6f}")
    ok("unmeasured_not_zero", "utility_scoring_seconds" in r["unmeasured_segments"]
       and "utility_scoring_seconds" not in r["segments"])
    ok("device_memory_null", r["device_memory"] is None and r["system_ram"] is None and r["energy"] is None)

    # 1) 嵌套 request 必须报错
    err = None
    try:
        with rec.request("q2"):
            with rec.request("q3"):
                pass
    except RuntimeError as exc:
        err = str(exc)
    ok("nested_request_rejected", err is not None and "嵌套" in str(err))

    # 3) 同名段重复必须报错
    err = None
    try:
        with rec.request("q4"):
            with rec.segment("ranking_no_self_seconds"):
                d.work(1)
            with rec.segment("ranking_no_self_seconds"):
                d.work(1)
    except RuntimeError as exc:
        err = str(exc)
    ok("duplicate_segment_rejected", err is not None and "重复段" in str(err))

    # 未定义段名必须报错
    err = None
    try:
        with rec.request("q5"):
            with rec.segment("not_a_segment"):
                pass
    except KeyError as exc:
        err = str(exc)
    ok("unknown_segment_rejected", err is not None)

    # 7) 观测数 <20 不报 P95
    for i in range(4):
        with rec.request(f"r{i}"):
            with rec.segment("ranking_no_self_seconds"):
                d.work(1)
    s = rec.summary()
    ok("p95_suppressed_small_n", s["segments"]["ranking_no_self_seconds"]["p95"] is None,
       str(s["segments"]["ranking_no_self_seconds"].get("p95_note")))

    # 5) 离线段
    with rec.offline_segment("corpus_encode_seconds"):
        d.work(4)
    with rec.offline_segment("index_build_seconds"):
        d.work(2)
    s = rec.summary()
    ok("offline_separate", set(s["offline_segments"]) == {"corpus_encode_seconds", "index_build_seconds"}
       and all(k not in s["segments"] for k in s["offline_segments"]))
    rec.close()

    # 2b) component > e2e 的检测（人为构造：不真跑）
    r2 = CostRecorder(Path(tempfile.mkdtemp()) / "c2.jsonl", "selftest2", prov)
    with r2.request("x"):
        r2._cur.segments["ranking_no_self_seconds"] = 1.0
        r2._cur.segments["generation_decode_seconds"] = 1.0
    r2.close()
    ok("component_exceeds_e2e_flagged", r2.records[0]["component_exceeds_e2e"] is True)

    passed = sum(c["pass"] for c in checks)
    print(json.dumps({"passed": passed, "total": len(checks), "checks": checks},
                     indent=2, ensure_ascii=False))
    out = Path(__file__).resolve().parent.parent / "reports" / "next_stage_20261020" / "cost_recorder_selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "total": len(checks), "checks": checks},
                             indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
