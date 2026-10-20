"""校验 A 侧索引构建回执（index_receipt）是否符合 schema 与对账规则。

为什么手写而不依赖 jsonschema：B 侧环境不一定装了 jsonschema，而这个脚本要能"拿到文件就能跑"。
因此这里实现的是 schema 的**必要子集**（必填键、枚举、sha256 形态、类型、跨字段一致性），
外加 A 侧独有的对账逻辑（18,955 vs 14,475 / 4,712）。

用法：
    python a-side/scripts/a20_validate_index_receipt.py <receipt.json>
    python a-side/scripts/a20_validate_index_receipt.py --self-check
    python a-side/scripts/a20_validate_index_receipt.py --self-check --json

退出码：0 = 通过（可能带 warning）；1 = 有 error；2 = 文件/参数问题。
"""

from __future__ import annotations

import json
import re
import sys

try:  # Windows 控制台可能是 cp936，统一成 utf-8 输出，避免中文 detail 触发 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

from pathlib import Path

PUBLIC_INSTANCES = 14_475
PUBLIC_UNIQUE = 4_712
CLAIMED_IN_SMOKE_REPORT = 18_955

REQUIRED = ["schema", "generated_at", "builder", "index", "identity", "dedup", "row_order",
            "dtype", "normalization", "corpus_encode", "query_encode", "sources", "counts",
            "reconciliation", "notes"]
ALLOWED_EXTRA = {"_instructions"}

ENUMS = {
    "index.kind": ["flat_bruteforce", "ivf", "hnsw", "other"],
    "identity.rule": ["sha256_raw_bytes", "sha256_jpeg_q95", "other"],
    "row_order.rule": ["sha256_asc", "insertion_order", "question_order", "filesystem_order", "other"],
    "dtype.storage": ["float32", "float16", "bfloat16", "int8", "other"],
    "normalization.locus": ["model_internal", "post_cast_float32", "none", "other"],
    "normalization.applied_to": ["corpus_and_query", "corpus_only", "query_only", "none", "other"],
    "reconciliation.verdict": ["matches_instances", "matches_unique", "matches_neither",
                               "pending", "not_comparable"],
}
SOURCE_ROLES = ["corpus", "questions", "scores", "candidates", "other"]
NESTED_REQUIRED = {
    "builder": ["repo", "commit", "entrypoint", "operator"],
    "index": ["entries", "artifact_files", "kind"],
    "identity": ["rule", "hash_algorithm", "notes"],
    "dedup": ["by_identity", "kept_duplicates", "notes"],
    "row_order": ["rule", "explicit_tiebreak_key", "notes"],
    "dtype": ["storage", "compute", "tf32"],
    "normalization": ["locus", "applied_to", "vector_norms_observed"],
    "corpus_encode": ["images", "batch_size", "device", "seconds", "notes"],
    "query_encode": ["batch_size", "composition", "per_request_batching"],
    "counts": ["questions", "image_instances", "unique_contents"],
    "reconciliation": ["claimed_entries", "public_instances", "public_unique",
                       "delta_vs_instances", "delta_vs_unique", "verdict", "notes"],
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
BOOLEANISH = ("by_identity", "explicit_tiebreak_key", "per_request_batching", "tf32")


def _get(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def validate(receipt: dict, *, recompute_reconciliation: bool = True) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    computed: dict = {}

    if not isinstance(receipt, dict):
        return {"ok": False, "errors": ["顶层必须是对象"], "warnings": [], "computed": {}}

    extra = set(receipt) - set(REQUIRED) - ALLOWED_EXTRA
    for k in sorted(extra):
        errors.append(f"未知顶层字段 {k!r}（schema 不允许 additionalProperties）")
    for k in REQUIRED:
        if k not in receipt:
            errors.append(f"缺少必填顶层字段 {k!r}")
    if receipt.get("schema") != "a_side_index_receipt/v1":
        errors.append(f"schema 必须为 a_side_index_receipt/v1，收到 {receipt.get('schema')!r}")

    for parent, keys in NESTED_REQUIRED.items():
        node = receipt.get(parent)
        if not isinstance(node, dict):
            errors.append(f"{parent} 必须是对象")
            continue
        for key in keys:
            if key not in node:
                errors.append(f"缺少必填字段 {parent}.{key}")

    for dotted, allowed in ENUMS.items():
        val = _get(receipt, dotted)
        if val is not None and val not in allowed:
            errors.append(f"{dotted}={val!r} 不在允许值 {allowed}")

    for name in BOOLEANISH:
        for parent in ("dedup", "row_order", "query_encode", "dtype"):
            if name in (receipt.get(parent) or {}):
                v = receipt[parent][name]
                if v is not None and not isinstance(v, bool):
                    errors.append(f"{parent}.{name} 必须是布尔或 null，收到 {type(v).__name__}")

    pairs = [((receipt.get("index") or {}).get("artifact_files"), "index.artifact_files"),
             (receipt.get("sources"), "sources")]
    for arr, where in pairs:
        if arr is None:
            continue
        if not isinstance(arr, list):
            errors.append(f"{where} 必须是数组")
            continue
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                errors.append(f"{where}[{i}] 必须是对象")
                continue
            sha = item.get("sha256")
            if not isinstance(sha, str) or not HEX64.match(sha):
                errors.append(f"{where}[{i}].sha256 必须是 64 位小写十六进制")
            if not isinstance(item.get("bytes"), int) or isinstance(item.get("bytes"), bool) or item["bytes"] < 0:
                errors.append(f"{where}[{i}].bytes 必须是 >=0 的整数")
            if where == "sources" and item.get("role") not in SOURCE_ROLES:
                errors.append(f"sources[{i}].role={item.get('role')!r} 不在 {SOURCE_ROLES}")

    entries = (receipt.get("index") or {}).get("entries")
    counts = receipt.get("counts") or {}
    inst, uniq = counts.get("image_instances"), counts.get("unique_contents")
    dedup = receipt.get("dedup") or {}

    if inst is not None and inst != PUBLIC_INSTANCES:
        warnings.append(f"counts.image_instances={inst} 与 A 侧基线 {PUBLIC_INSTANCES} 不同；请说明口径")
    if uniq is not None and uniq != PUBLIC_UNIQUE:
        warnings.append(f"counts.unique_contents={uniq} 与 A 侧基线 {PUBLIC_UNIQUE} 不同；请说明口径")

    kept = dedup.get("kept_duplicates")
    if dedup.get("by_identity") is True:
        if kept not in (0, None):
            errors.append(f"按内容去重时 dedup.kept_duplicates 必须为 0，收到 {kept}")
        if isinstance(entries, int) and isinstance(uniq, int) and entries != uniq:
            warnings.append(
                f"索引条目 {entries} != counts.unique_contents {uniq}：若确为按内容去重，"
                "请说明索引为何多于唯一内容（例如并入了其他图池）"
            )
    elif dedup.get("by_identity") is False:
        if kept is not None and isinstance(inst, int) and isinstance(uniq, int):
            expect = max(0, inst - uniq)
            if kept != expect:
                errors.append(
                    f"不去重时 dedup.kept_duplicates 应等于 实例数-唯一数={expect}，收到 {kept}"
                )

    rec = receipt.get("reconciliation") or {}
    if rec.get("verdict") == "pending":
        note = rec.get("notes")
        if not (isinstance(note, str) and note.strip()):
            errors.append(
                "reconciliation.verdict=pending 时必须在 reconciliation.notes 写明在等什么"
                "（例如『等 A 侧按 14,475/4,712 口径对账』），不能留空"
            )
    claimed = rec.get("claimed_entries") if rec.get("claimed_entries") is not None else entries
    computed["claimed_entries"] = claimed
    computed["public_instances"] = PUBLIC_INSTANCES
    computed["public_unique"] = PUBLIC_UNIQUE
    if claimed is None:
        computed["verdict"] = "pending"
    else:
        computed["delta_vs_instances"] = claimed - PUBLIC_INSTANCES
        computed["delta_vs_unique"] = claimed - PUBLIC_UNIQUE
        if claimed == PUBLIC_INSTANCES:
            computed["verdict"] = "matches_instances"
        elif claimed == PUBLIC_UNIQUE:
            computed["verdict"] = "matches_unique"
        else:
            computed["verdict"] = "matches_neither"

    if recompute_reconciliation and claimed is not None:
        if rec.get("claimed_entries") is not None and entries is not None and rec["claimed_entries"] != entries:
            errors.append(f"reconciliation.claimed_entries={rec['claimed_entries']} 与 index.entries={entries} 不一致")
        if rec.get("verdict") not in (None, computed["verdict"]) and rec.get("verdict") != "not_comparable":
            warnings.append(f"回执写的 verdict={rec.get('verdict')!r}，A 侧重算为 {computed['verdict']!r}")
    computed["verdict_a_side"] = computed.get("verdict")

    if computed.get("verdict") == "matches_neither":
        warnings.append(
            f"索引 {claimed} 条既不等于实例数 {PUBLIC_INSTANCES} 也不等于唯一内容数 {PUBLIC_UNIQUE}"
            f"（与 smoke 报告写的 {CLAIMED_IN_SMOKE_REPORT} {'一致' if claimed == CLAIMED_IN_SMOKE_REPORT else '不一致'}）："
            "在 B 给出差额来源前，两批结果不得配对"
        )

    if not receipt.get("sources"):
        warnings.append("sources 为空：无法核对语料/题目/排序缓存的输入身份")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "computed": computed}


def _filled(entries: int, *, by_identity=True, kept=0) -> dict:
    return {
        "schema": "a_side_index_receipt/v1",
        "generated_at": "2026-10-21T00:00:00Z",
        "builder": {"repo": "joyboy-type/EdgeCoRAG", "commit": "abc1234",
                    "entrypoint": "a-side/scripts/build_index.py", "operator": "b"},
        "index": {"entries": entries, "kind": "flat_bruteforce",
                  "artifact_files": [{"path": "scores.npy", "bytes": 1024, "sha256": "a" * 64}]},
        "identity": {"rule": "sha256_jpeg_q95", "hash_algorithm": "sha256", "notes": "PIL 12.3.0"},
        "dedup": {"by_identity": by_identity, "kept_duplicates": kept, "notes": None},
        "row_order": {"rule": "sha256_asc", "explicit_tiebreak_key": True, "notes": None},
        "dtype": {"storage": "float32", "compute": "float32", "tf32": False},
        "normalization": {"locus": "post_cast_float32", "applied_to": "corpus_and_query",
                          "vector_norms_observed": "1.000"},
        "corpus_encode": {"images": 4712, "batch_size": 16, "device": "cuda", "seconds": 1576.0, "notes": None},
        "query_encode": {"batch_size": 1, "composition": "单题", "per_request_batching": True},
        "sources": [{"role": "corpus", "path": "corpus_manifest.csv", "sha256": "b" * 64, "bytes": 10}],
        "counts": {"questions": 1353, "image_instances": PUBLIC_INSTANCES, "unique_contents": PUBLIC_UNIQUE},
        "reconciliation": {"claimed_entries": None, "public_instances": PUBLIC_INSTANCES,
                           "public_unique": PUBLIC_UNIQUE, "delta_vs_instances": None,
                           "delta_vs_unique": None, "verdict": "pending",
                           "notes": "等 A 裁定"},
        "notes": [],
    }


def self_check() -> int:
    checks: list[dict] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(cond), "detail": detail})

    # 1) 模板（未填）→ 通过但 pending + 有 warning
    tmpl = json.loads((Path(__file__).resolve().parent.parent / "contracts" /
                       "index_receipt.example.json").read_text(encoding="utf-8"))
    r = validate(tmpl)
    ok("template_ok_pending", r["ok"] and r["computed"]["verdict"] == "pending",
       json.dumps(r["computed"]))

    # 2) 完整且 entries == 实例数 → matches_instances
    r = validate(_filled(PUBLIC_INSTANCES))
    ok("entries_equals_instances", r["ok"] and r["computed"]["verdict"] == "matches_instances")

    # 3) entries == 唯一数 → matches_unique
    r = validate(_filled(PUBLIC_UNIQUE))
    ok("entries_equals_unique", r["ok"] and r["computed"]["verdict"] == "matches_unique")

    # 4) entries == 18,955 → matches_neither + 阻断性 warning
    r = validate(_filled(CLAIMED_IN_SMOKE_REPORT))
    ok("entries_18955_flagged", r["ok"] and r["computed"]["verdict"] == "matches_neither"
       and any("不得配对" in w for w in r["warnings"]), json.dumps(r["computed"]))

    # 5) 缺字段 → error
    bad = _filled(PUBLIC_INSTANCES)
    bad.pop("normalization")
    ok("missing_key_rejected", not validate(bad)["ok"])

    # 6) 非法 sha → error
    bad = _filled(PUBLIC_INSTANCES)
    bad["sources"][0]["sha256"] = "xyz"
    ok("bad_sha_rejected", not validate(bad)["ok"])

    # 7) 非法枚举 → error
    bad = _filled(PUBLIC_INSTANCES)
    bad["normalization"]["locus"] = "somewhere"
    ok("bad_enum_rejected", not validate(bad)["ok"])

    # 8) 去重一致性 → error（按内容去重却保留了重复）
    bad = _filled(PUBLIC_INSTANCES, by_identity=True, kept=10)
    ok("dedup_inconsistent_rejected", not validate(bad)["ok"])

    # 9) claimed_entries 与 index.entries 矛盾 → error
    bad = _filled(PUBLIC_INSTANCES)
    bad["reconciliation"]["claimed_entries"] = PUBLIC_UNIQUE
    ok("claimed_entries_mismatch_rejected", not validate(bad)["ok"])

    # 10) 布尔字段类型错 → error
    bad = _filled(PUBLIC_INSTANCES)
    bad["row_order"]["explicit_tiebreak_key"] = "yes"
    ok("bool_type_rejected", not validate(bad)["ok"])

    # 11) pending + notes → 通过
    r = validate(_filled(PUBLIC_INSTANCES))
    ok("pending_with_notes_ok", r["ok"], json.dumps(r["errors"])[:120])

    # 12) pending 缺 notes → 必须报错
    bad = _filled(PUBLIC_INSTANCES)
    bad["reconciliation"]["notes"] = None
    r = validate(bad)
    ok("pending_without_notes_rejected", (not r["ok"])
       and any("pending" in e and "notes" in e for e in r["errors"]),
       json.dumps(r["errors"])[:160])

    passed = sum(c["pass"] for c in checks)
    payload = {"passed": passed, "total": len(checks), "checks": checks}
    if "--json" in sys.argv:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for c in checks:
            print(("PASS " if c["pass"] else "FAIL ") + c["check"] + ("" if c["pass"] else " | " + c["detail"]))
        print(f"\n{passed}/{len(checks)}")
    out = Path(__file__).resolve().parent.parent / "reports" / "next_stage_20261020" / "index_receipt_validator_selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if passed == len(checks) else 1


def main(argv: list[str]) -> int:
    if "--self-check" in argv:
        return self_check()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    p = Path(args[0])
    if not p.exists():
        print(f"找不到回执文件：{p}", file=sys.stderr)
        return 2
    r = validate(json.loads(p.read_text(encoding="utf-8")))
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
