"""校验交接产物是否符合 contracts/*.schema.json。

**为什么需要它**: schema 与生成器分处两地,极易漂移。
实际已经踩过一次: 生成器一度写出 role="ret" / evidence_id="mragb:0#ret0",
而 schema 的枚举是 "official_retrieved"、pattern 要求 "mragb:0#official_retrieved0"。
靠肉眼比对不可靠,故用程序校验。

用法:
    python scripts/validate_schema.py                      # 校验 samples/
    python scripts/validate_schema.py --path <目录或文件>
    python scripts/validate_schema.py --schema evidence   # 只校验某一份 schema

实现说明: 不依赖 jsonschema 包,自行实现本 schema 用到的子集
(type/required/enum/pattern/additionalProperties/items/$ref/allOf/minItems/maxItems/minimum/default)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

HANDOVER = cfg.ROOT.parent / "EdgeCoRAG-B-handover"
SCHEMA_DIR = HANDOVER / "contracts"
SAMPLES = HANDOVER / "samples"

SCHEMAS = {
    "evidence": ("evidence_list.schema.json", "evidence_sample.jsonl"),
    "result": ("result_row.schema.json", None),
}


def resolve(node: dict, root: dict) -> dict:
    """展开 $ref。"""
    seen = 0
    while "$ref" in node and seen < 10:
        ref = node["$ref"]
        if not ref.startswith("#/"):
            break
        cur = root
        for part in ref[2:].split("/"):
            cur = cur[part]
        node = cur
        seen += 1
    return node


def check(value, node: dict, root: dict, path: str, errors: list[str]) -> None:
    node = resolve(node, root)
    if not isinstance(node, dict):
        return

    # allOf: 逐个校验(常见于 evidenceRef)
    if "allOf" in node:
        for sub in node["allOf"]:
            check(value, sub, root, path, errors)
        return

    t = node.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            if tt == "object" and isinstance(value, dict):
                ok = True
            elif tt == "array" and isinstance(value, list):
                ok = True
            elif tt == "string" and isinstance(value, str):
                ok = True
            elif tt == "integer" and isinstance(value, int) and not isinstance(value, bool):
                ok = True
            elif tt == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                ok = True
            elif tt == "boolean" and isinstance(value, bool):
                ok = True
            elif tt == "null" and value is None:
                ok = True
        if not ok:
            errors.append(f"{path}: 类型应为 {types},实为 {type(value).__name__} ({value!r:.40})")
            return

    if value is None:
        return

    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: 值 {value!r} 不在枚举 {node['enum']}")

    if "pattern" in node and isinstance(value, str):
        if not re.search(node["pattern"], value):
            errors.append(f"{path}: 值 {value!r} 不匹配 pattern {node['pattern']!r}")

    if "minimum" in node and isinstance(value, (int, float)):
        if value < node["minimum"]:
            errors.append(f"{path}: {value} < minimum {node['minimum']}")

    if isinstance(value, dict):
        props = node.get("properties", {})
        for req in node.get("required", []):
            if req not in value:
                errors.append(f"{path}: 缺少必需字段 {req!r}")
        if node.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                errors.append(f"{path}: 出现未声明的字段 {sorted(extra)}")
        for k, v in value.items():
            if k in props:
                check(v, props[k], root, f"{path}.{k}", errors)

    if isinstance(value, list):
        items = node.get("items")
        if "minItems" in node and len(value) < node["minItems"]:
            errors.append(f"{path}: 长度 {len(value)} < minItems {node['minItems']}")
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(f"{path}: 长度 {len(value)} > maxItems {node['maxItems']}")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                check(item, items, root, f"{path}[{i}]", errors)


def validate_file(schema_name: str, data_file: Path) -> tuple[int, list[str]]:
    schema_path = SCHEMA_DIR / schema_name
    if not schema_path.exists():
        return 0, [f"schema 不存在: {schema_path}"]
    if not data_file.exists():
        return 0, [f"数据文件不存在: {data_file}"]

    root = json.loads(schema_path.read_text(encoding="utf-8"))
    n = 0
    all_errors: list[str] = []
    for lineno, line in enumerate(data_file.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            all_errors.append(f"第 {lineno} 行 JSON 解析失败: {exc}")
            continue
        errs: list[str] = []
        check(obj, root, root, f"line{lineno}", errs)
        all_errors.extend(errs)
        n += 1
    return n, all_errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=None,
                    help="目录或 jsonl 文件;默认校验 samples/")
    ap.add_argument("--schema", choices=list(SCHEMAS), default=None)
    args = ap.parse_args()

    targets: list[tuple[str, Path]] = []
    base = args.path or SAMPLES
    for key, (schema_name, default_file) in SCHEMAS.items():
        if args.schema and key != args.schema:
            continue
        if base.is_file():
            targets.append((schema_name, base))
        else:
            f = base / (default_file or "result_sample.jsonl")
            if f.exists():
                targets.append((schema_name, f))

    if not targets:
        print(f"未找到可校验的文件(目录: {base})")
        return 0

    rc = 0
    for schema_name, data_file in targets:
        n, errors = validate_file(schema_name, data_file)
        status = "✅ 通过" if not errors else f"❌ {len(errors)} 处不符"
        print(f"{status}  {data_file.name}  ({n} 行)  <- {schema_name}")
        for e in errors[:25]:
            print(f"    - {e}")
        if len(errors) > 25:
            print(f"    ... 另有 {len(errors) - 25} 处")
        if errors:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
