"""计时记录器自检：不依赖 GPU / 模型，验证边界、口径、汇总与外部资源注入。

覆盖的断言（任务 3 + 审阅补充 A1/A2）：
  A 组（原有）
    1. 端到端只能有一个外层计时器（禁止嵌套 request）
    2. 分段时间不会自动被当成端到端；component 之和 > 端到端时被标记
    3. 同一请求内同名段重复会被拒绝（防止无意覆盖）
    4. 未测段进入 unmeasured_segments，不写 0
    5. 离线段与在线段分开，且离线不能混入在线汇总
    6. provenance 必填项缺失时拒绝创建
    7. 观测数 <20 时不报 P95（并给出理由字符串）
    8. 未注入时 device_memory / system_ram / energy 为 null
  B 组（A1：强制线程字段）
    9. hardware.cpu_thread_env 缺失 → 拒绝
   10. "auto" / 空串 / 0 / 负值 / 布尔 → 拒绝
   11. 正整数 8 → 通过，且落盘字段一致（provenance 与 summary 都是 8）
   12. "unfixed" → 通过，且每行 unmeasured_provenance 留痕、summary 也标 unfixed
  C 组（A2：资源注入）
   13. resources() 注入合法值 → 落到当前请求记录
   14. 注入缺 value/unit/method → 拒绝
   15. 注入 method 为分配器口径 → 拒绝（不得冒充整卡）
   16. 注入 None（未测）保持 null，不被写成 0
   17. attach_resources() 按 req_id 合并外部实测值，未提供的仍为 null
    18. attach_resources() 遇到非法值（负值/分配器口径）拒绝

用法: python a-side/scripts/a13_cost_selftest.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a12_cost_recorder import (  # noqa: E402
    CostRecorder, ProvenanceError, ResourceError, attach_resources, normalize_cpu_thread_env,
)


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

    base_prov = {
        "hardware": {"gpu": "selftest-cpu", "vram_gib": None, "cpu_thread_env": 8},
        "encoder": {"model": "dummy", "revision": "dummy"},
        "corpus": {"rows": 0},
        "protocol": "cost_recorder_selftest_v1",
        "warm_state": "n/a",
    }
    tmpdir = Path(tempfile.mkdtemp())

    # ---------------- A6) provenance 必填
    try:
        CostRecorder(tmpdir / "x.jsonl", "r0", {})
        ok("provenance_required", False)
    except ProvenanceError:
        ok("provenance_required", True)

    # ---------------- B9-B12) cpu_thread_env 强制校验
    for label, bad in (("missing", None), ("auto", "auto"), ("empty", ""),
                       ("zero", 0), ("negative", -4), ("bool", True)):
        prov = json.loads(json.dumps(base_prov))
        if bad is None:
            prov["hardware"].pop("cpu_thread_env")
        else:
            prov["hardware"]["cpu_thread_env"] = bad
        try:
            CostRecorder(tmpdir / f"bad_{label}.jsonl", "r", prov)
            ok(f"cpu_thread_env_reject_{label}", False, f"{bad!r} 竟然通过")
        except ProvenanceError as exc:
            ok(f"cpu_thread_env_reject_{label}", True, str(exc)[:80])

    for label, good, expect in (("int8", 8, 8), ("unfixed", "unfixed", "unfixed")):
        prov = json.loads(json.dumps(base_prov))
        prov["hardware"]["cpu_thread_env"] = good
        p = tmpdir / f"good_{label}.jsonl"
        rec = CostRecorder(p, "r", prov)
        with rec.request("q1"):
            with rec.segment("ranking_no_self_seconds"):
                _Dummy().work(2)
        rec.close()
        row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
        s = rec.summary()
        ok(f"cpu_thread_env_accept_{label}",
           row["provenance"]["hardware"]["cpu_thread_env"] == expect
           and s["cpu_thread_env"] == expect,
           f"record={row['provenance']['hardware']['cpu_thread_env']!r} summary={s['cpu_thread_env']!r}")
        if label == "unfixed":
            ok("cpu_thread_env_unfixed_trace",
               any("unfixed" in x for x in row["unmeasured_provenance"]) and s["unmeasured_provenance"],
               str(row["unmeasured_provenance"])[:100])
        else:
            ok("cpu_thread_env_int8_no_trace", row["unmeasured_provenance"] == [])

    ok("normalize_rejects_auto_direct", _raises(lambda: normalize_cpu_thread_env("auto")))

    # ---------------- A2) 正常请求 + 未测段
    d = _Dummy()
    rec = CostRecorder(tmpdir / "cost.jsonl", run_id="selftest", provenance=base_prov)
    with rec.request("q1", strategy="cosine"):
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
    ok("resources_default_null", r["device_memory"] is None and r["system_ram"] is None
       and r["energy"] is None)

    # 1) 嵌套 request 必须报错
    ok("nested_request_rejected", _raises(lambda: _nested(rec)))

    # 3) 同名段重复必须报错
    ok("duplicate_segment_rejected", _raises(lambda: _dup_segment(rec), want="重复段"))

    ok("unknown_segment_rejected", _raises(lambda: _unknown_segment(rec), KeyError))

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

    # 2b) component > e2e 的检测（人为构造）
    r2 = CostRecorder(tmpdir / "c2.jsonl", "selftest2", base_prov)
    with r2.request("x"):
        r2._cur.segments["ranking_no_self_seconds"] = 1.0
        r2._cur.segments["generation_decode_seconds"] = 1.0
    r2.close()
    ok("component_exceeds_e2e_flagged", r2.records[0]["component_exceeds_e2e"] is True)

    # ---------------- C13-C18) 资源注入
    dm = {"value": 7.1, "unit": "GiB", "method": "nvidia-smi memory.used 10Hz"}
    ram = {"value": 12.4, "unit": "GiB", "method": "/usr/bin/time -v Maximum resident set size"}
    r3 = CostRecorder(tmpdir / "c3.jsonl", "r3", base_prov)
    with r3.request("q-ok"):
        with r3.segment("ranking_no_self_seconds"):
            d.work(1)
        r3.resources(device_memory=dm, system_ram=ram)
    with r3.request("q-none"):
        with r3.segment("ranking_no_self_seconds"):
            d.work(1)
    r3.close()
    ok("resources_injected",
       r3.records[0]["device_memory"]["value"] == 7.1
       and r3.records[0]["device_memory"]["unit"] == "GiB"
       and r3.records[0]["energy"] is None,
       json.dumps(r3.records[0]["device_memory"], ensure_ascii=False))
    ok("resources_uninjected_stays_null",
       r3.records[1]["device_memory"] is None and r3.records[1]["system_ram"] is None)
    st = r3.summary()
    ok("summary_resources_present_count", st["resources_present"]["device_memory"] == 1
       and st["resources_present"]["energy"] == 0, json.dumps(st["resources_present"]))

    # 资源注入的拒绝用例用一个未关闭的新记录器（关掉文件后再写会掩盖真正的校验异常）
    r4 = CostRecorder(tmpdir / "c4.jsonl", "r4", base_prov)

    ok("resources_missing_fields_rejected",
       _raises(lambda: _inject(r4, {"value": 1.0, "unit": "GiB"}), want="缺少字段"))
    ok("resources_allocator_rejected",
       _raises(lambda: _inject(r4, {"value": 10.49, "unit": "GiB",
                                    "method": "torch.cuda.max_memory_allocated()"}),
               want="分配器"))
    ok("resources_negative_rejected",
       _raises(lambda: _inject(r4, {"value": -1.0, "unit": "GiB", "method": "nvidia-smi"}),
               want="负"))
    ok("resources_empty_call_rejected", _raises(lambda: _inject_none(r4), want="至少"))

    # 17) attach_resources 后处理
    src = tmpdir / "c3.jsonl"
    merged = attach_resources(
        src,
        lambda req_id, row: {"device_memory": {"value": 6.5, "unit": "GiB",
                                               "method": "nvidia-smi memory.used 10Hz"}}
        if req_id == "q-none" else {},
        out_path=tmpdir / "c3.merged.jsonl",
    )
    rows = [json.loads(x) for x in (tmpdir / "c3.merged.jsonl").read_text(encoding="utf-8").splitlines()]
    ok("attach_resources_merge",
       rows[1]["device_memory"]["value"] == 6.5
       and rows[0]["device_memory"]["value"] == 7.1
       and rows[1]["system_ram"] is None,
       json.dumps(merged["filled"]))
    ok("attach_resources_reports_missing", merged["missing_req_ids"] == ["q-ok"],
       json.dumps(merged["missing_req_ids"]))
    ok("attach_resources_rejects_allocator", _raises(
        lambda: attach_resources(src, lambda rid, row: {"energy": {"value": 1, "unit": "J",
                                                                   "method": "allocator delta"}},
                                 out_path=tmpdir / "bad_merge.jsonl"), want="分配器"))

    passed = sum(c["pass"] for c in checks)
    payload = {"passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    out = Path(__file__).resolve().parent.parent / "reports" / "next_stage_20261020" / "cost_recorder_selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------- 小工具
def _raises(fn, want: str | type | None = None) -> bool:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        if want is None:
            return True
        if isinstance(want, type):
            return isinstance(exc, want)
        return want in str(exc)
    return False


def _nested(rec: CostRecorder) -> None:
    with rec.request("q2"):
        with rec.request("q3"):
            pass


def _dup_segment(rec: CostRecorder) -> None:
    with rec.request("q4"):
        with rec.segment("ranking_no_self_seconds"):
            pass
        with rec.segment("ranking_no_self_seconds"):
            pass


def _unknown_segment(rec: CostRecorder) -> None:
    with rec.request("q5"):
        with rec.segment("not_a_segment"):
            pass


def _inject(rec: CostRecorder, value: dict) -> None:
    with rec.request("q-inject"):
        rec.resources(device_memory=value)


def _inject_none(rec: CostRecorder) -> None:
    with rec.request("q-inject-none"):
        rec.resources()


if __name__ == "__main__":
    sys.exit(main())
