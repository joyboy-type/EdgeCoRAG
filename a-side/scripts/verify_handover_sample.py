"""交接样例验收: 一次跑完 Schema / ID / 哈希 / 解码 / 顺序 / 数量 / 跨字段 检查。

这是要求三之4的"验证脚本及实际输出"。覆盖:

  A. Schema 合规(自实现的 JSON Schema 子集校验器)
  B. ID 体系: evidence_id 唯一、qid 格式、raw_id 映射可反查
  C. 图片哈希: 文件存在、字节哈希与索引一致、容器格式与扩展名一致
  D. 图片可解码: PIL 能打开、尺寸与索引一致、RGB 可转换
  E. 顺序一致: JSONL 的 evidence_order 与 CSV 索引的 rank 序列一致
  F. 数量正确: num_evidence == 列表长度; 证据数与占位符数匹配协议
  G. 跨字段: 排名/分数与列表等长; 图片路径有效; GT 映射可解析
  H. 隔离性: scoring_only 与 task_payload 不混

用法:
    python scripts/verify_handover_sample.py
    python scripts/verify_handover_sample.py --dir <样例目录> --json   # 机器可读输出
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_config as cfg  # noqa: E402

HANDOVER = cfg.ROOT.parent / "EdgeCoRAG-B-handover"
DEFAULT_DIR = HANDOVER / "samples"
SCHEMA = HANDOVER / "contracts" / "evidence_list.schema.json"
OUT = cfg.ROOT / "outputs" / "handover_verify" / "acceptance_report.json"

MAGIC = [(b"\xff\xd8\xff", "jpeg"), (b"\x89PNG\r\n\x1a\n", "png"),
         (b"GIF87a", "gif"), (b"GIF89a", "gif"), (b"BM", "bmp")]
EXT_OF = {"jpeg": {"jpg", "jpeg"}, "png": {"png"}, "gif": {"gif"}, "bmp": {"bmp"}}


class Report:
    def __init__(self) -> None:
        self.groups: dict[str, list[tuple[str, bool, str]]] = {}

    def add(self, group: str, name: str, ok: bool, detail: str = "") -> None:
        self.groups.setdefault(group, []).append((name, ok, detail))

    def to_dict(self) -> dict:
        out = {}
        for g, items in self.groups.items():
            out[g] = {
                "passed": sum(1 for _, ok, _ in items if ok),
                "failed": sum(1 for _, ok, _ in items if not ok),
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in items],
            }
        return out

    def all_ok(self) -> bool:
        return all(ok for items in self.groups.values() for _, ok, _ in items)

    def print(self) -> None:
        for g, items in self.groups.items():
            nfail = sum(1 for _, ok, _ in items if not ok)
            head = "✅" if nfail == 0 else "❌"
            print(f"\n{head} {g}  ({len(items) - nfail}/{len(items)} 通过)")
            for n, ok, d in items:
                if not ok:
                    print(f"    ❌ {n}  {d}")
                elif d:
                    print(f"    ✅ {n}  {d}")


# ---------------------------------------------------------------- A. schema
def check_schema(obj, node, root, path, rep: Report, group="A. Schema 合规") -> None:
    """递归校验本 schema 用到的子集。"""
    if "$ref" in node:
        ref = node["$ref"]
        if ref.startswith("#/"):
            cur = root
            for part in ref[2:].split("/"):
                cur = cur[part]
            node = cur
    if not isinstance(node, dict):
        return
    if "allOf" in node:
        for sub in node["allOf"]:
            check_schema(obj, sub, root, path, rep, group)
        return

    t = node.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        ok = any(
            (tt == "object" and isinstance(obj, dict)) or
            (tt == "array" and isinstance(obj, list)) or
            (tt == "string" and isinstance(obj, str)) or
            (tt == "integer" and isinstance(obj, int) and not isinstance(obj, bool)) or
            (tt == "number" and isinstance(obj, (int, float)) and not isinstance(obj, bool)) or
            (tt == "boolean" and isinstance(obj, bool)) or
            (tt == "null" and obj is None)
            for tt in types)
        if not ok:
            rep.add(group, f"{path} 类型", False,
                    f"期望 {types}, 实际 {type(obj).__name__}")
            return

    if obj is None:
        return
    if "enum" in node and obj not in node["enum"]:
        rep.add(group, f"{path} 枚举", False, f"{obj!r} 不在 {node['enum']}")
    if "pattern" in node and isinstance(obj, str) and not re.search(node["pattern"], obj):
        rep.add(group, f"{path} 正则", False, f"{obj!r} 不匹配 {node['pattern']!r}")
    if "minimum" in node and isinstance(obj, (int, float)) and obj < node["minimum"]:
        rep.add(group, f"{path} 下界", False, f"{obj} < {node['minimum']}")

    if isinstance(obj, dict):
        props = node.get("properties", {})
        for req in node.get("required", []):
            if req not in obj:
                rep.add(group, f"{path} 必填", False, f"缺 {req!r}")
        if node.get("additionalProperties") is False:
            extra = set(obj) - set(props)
            if extra:
                rep.add(group, f"{path} 未声明字段", False, f"{sorted(extra)}")
        for k, v in obj.items():
            if k in props:
                check_schema(v, props[k], root, f"{path}.{k}", rep, group)
    if isinstance(obj, list):
        items = node.get("items")
        if isinstance(items, dict):
            for i, it in enumerate(obj):
                check_schema(it, items, root, f"{path}[{i}]", rep, group)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()
    base: Path = args.dir
    rep = Report()

    jsonl = base / "evidence_sample.jsonl"
    idx_csv = base / "evidence_index.csv"
    if not jsonl.exists() or not idx_csv.exists():
        print(f"✗ 缺少 {jsonl} 或 {idx_csv}")
        return 1

    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    with idx_csv.open(encoding="utf-8-sig", newline="") as fh:
        idx = list(csv.DictReader(fh))
    index_by_id = {r["evidence_id"]: r for r in idx}

    # ---------------------------------------------------------------- A
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for i, r in enumerate(rows, 1):
        check_schema(r, schema, schema, f"row{i}", rep)
    rep.add("A. Schema 合规", "逐行通过 evidence_list.schema.json",
            not any(not ok for _, ok, _ in rep.groups.get("A. Schema 合规", [])),
            f"{len(rows)} 行")

    # ---------------------------------------------------------------- B
    eids = [r["evidence_id"] for r in idx]
    rep.add("B. ID 体系", "evidence_id 全局唯一", len(set(eids)) == len(eids),
            f"{len(eids)} 条")
    rep.add("B. ID 体系", "qid 前缀格式 mragb:<raw_id>",
            all(re.fullmatch(r"mragb:.+", r["qid"]) for r in rows),
            f"{len(rows)} 题")
    rep.add("B. ID 体系", "raw_id 与 qid 可互推",
            all(r["qid"] == f"mragb:{r['raw_id']}" for r in rows))
    rep.add("B. ID 体系", "evidence_id 含 qid 前缀",
            all(e.startswith(r["qid"] + "#") for r in rows for e in
                [x["evidence_id"] for x in r["evidence_order"]]))
    rep.add("B. ID 体系", "JSONL 内 qid 唯一",
            len({r["qid"] for r in rows}) == len(rows), f"{len(rows)} 题")
    # CSV 与 JSONL 的 evidence_id 集合一致
    # 注意: 索引允许包含 used_in_prompt=false 的条目(Incomplete 截断候选),
    # 但**不允许出现孤儿**: 每条索引条目都必须能在 JSONL 的某个引用区找到。
    jsonl_ids = {r["question_image"]["evidence_id"] for r in rows}
    jsonl_ids |= {e["evidence_id"] for r in rows for e in r["evidence_order"]}
    jsonl_ids |= {e["evidence_id"] for r in rows
                  for e in r["scoring_only"].get("gt_evidence_refs", [])}
    jsonl_ids |= {e["evidence_id"] for r in rows
                  for e in r["scoring_only"].get("gt_evidence_refs", [])}
    # 被截断候选（Incomplete）也算已声明来源
    jsonl_ids |= {e["evidence_id"] for r in rows
                  for e in (r.get("available_evidence_untruncated") or {})
                  .get("retrieved_refs", []) or []}
    jsonl_ids |= {e["evidence_id"] for r in rows
                  for e in (r.get("available_evidence_untruncated") or {})
                  .get("gt_refs", []) or []}
    orphans = set(eids) - jsonl_ids
    rep.add("B. ID 体系", "JSONL 与 CSV 的 evidence_id 集合一致(无孤儿)",
            not orphans, f"JSONL {len(jsonl_ids)} / CSV {len(eids)}"
                         + (f", 孤儿 {len(orphans)}: {sorted(orphans)[:5]}" if orphans else ""))
    rep.add("B. ID 体系", "used_in_prompt=false 的条目有声明来源",
            not orphans, f"孤儿 {len(orphans)}")

    # ---------------------------------------------------------------- C
    miss = bad_hash = bad_ext = 0
    for r in idx:
        p = base / r["path"]
        if not p.exists():
            miss += 1
            continue
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != r["sha256"]:
            bad_hash += 1
        real = next((n for m, n in MAGIC if b.startswith(m)), "unknown")
        if p.suffix.lstrip(".").lower() not in EXT_OF.get(real, set()):
            bad_ext += 1
    rep.add("C. 图片哈希", "索引文件全部存在", miss == 0, f"缺失 {miss}")
    rep.add("C. 图片哈希", "字节 sha256 与索引一致", bad_hash == 0, f"不符 {bad_hash}")
    rep.add("C. 图片哈希", "容器格式与扩展名一致", bad_ext == 0, f"不符 {bad_ext}")

    # ---------------------------------------------------------------- D
    from PIL import Image
    dec_fail = dim_bad = 0
    for r in idx:
        p = base / r["path"]
        try:
            with Image.open(p) as im:
                im.load()
                if (im.width, im.height) != (int(r["w"]), int(r["h"])):
                    dim_bad += 1
                im.convert("RGB")
        except Exception:  # noqa: BLE001
            dec_fail += 1
    rep.add("D. 图片解码", "全部可被 PIL 打开", dec_fail == 0, f"失败 {dec_fail}")
    rep.add("D. 图片解码", "尺寸与索引一致", dim_bad == 0, f"不符 {dim_bad}")
    rep.add("D. 图片解码", "可转为 RGB", dec_fail == 0)

    # ---------------------------------------------------------------- E
    order_bad = 0
    for r in rows:
        csv_ranks = [int(index_by_id[e["evidence_id"]]["rank"])
                     for e in r["evidence_order"] if e["evidence_id"] in index_by_id]
        if csv_ranks != list(range(len(csv_ranks))):
            order_bad += 1
    rep.add("E. 顺序一致", "evidence_order 与索引 rank 序列一致",
            order_bad == 0, f"不符 {order_bad}")

    # ---------------------------------------------------------------- F
    rep.add("F. 数量正确", "num_evidence == len(evidence_order)",
            all(r["num_evidence"] == len(r["evidence_order"]) for r in rows))
    slots_bad = [r["qid"] for r in rows
                 if r["prompt_image_slots"] != len(r["evidence_order"]) + 1]
    rep.add("F. 数量正确", "占位符数 == 证据数 + 1(含查询图)",
            not slots_bad, f"不符 {slots_bad}" if slots_bad else "")
    inc = [r for r in rows if r["scenario"] == "Incomplete"]
    rep.add("F. 数量正确", "Incomplete 场景证据数为 1",
            all(len(r["evidence_order"]) == 1 for r in inc),
            f"{len(inc)} 题 Incomplete")

    # ---------------------------------------------------------------- G
    rep.add("G. 跨字段", "retrieval_ranks 与列表等长",
            all(len(r["retrieval_ranks"]) == len(r["evidence_order"]) for r in rows))
    rep.add("G. 跨字段", "retrieval_scores 与列表等长",
            all(len(r["retrieval_scores"]) == len(r["evidence_order"]) for r in rows))
    rep.add("G. 跨字段", "图片路径全部有效(相对 path_root)",
            all((base / e["path"]).exists()
                for r in rows
                for e in [r["question_image"]] + r["evidence_order"]
                + r["scoring_only"].get("gt_evidence_refs", [])))
    rep.add("G. 跨字段", "GT ID 与 GT refs 一一对应",
            all([x["evidence_id"] for x in r["scoring_only"]["gt_evidence_refs"]]
                == r["scoring_only"]["gt_evidence_ids"] for r in rows))
    rep.add("G. 跨字段", "GT 命中位点在合法范围内",
            all(all(0 <= k < len(r["evidence_order"])
                    for k in r["scoring_only"]["gt_on_official_pool_ranks"])
                for r in rows))
    rep.add("G. 跨字段", "路径以 images/ 为根且按 raw_id 分目录",
            all(e["path"].startswith(f"images/{r['raw_id']}/")
                for r in rows for e in r["evidence_order"]))

    # ---------------------------------------------------------------- H
    rep.add("H. 隔离性", "task_payload 不含答案字段",
            all(not ({"gold_choice", "answer_text", "answer"} &
                     set(r["task_payload"].get("choices") or {})
                     | ({"gold_choice", "answer_text"} & set(r["task_payload"])))
                for r in rows))
    rep.add("H. 隔离性", "scoring_only 含 gold_choice 且取值合法",
            all(r["scoring_only"]["gold_choice"] in ("A", "B", "C", "D") for r in rows))
    rep.add("H. 隔离性", "四个选项完整",
            all(set(r["task_payload"]["choices"]) == {"A", "B", "C", "D"} for r in rows))
    rep.add("H. 隔离性", "is_oracle 全部为 false",
            all(r["is_oracle"] is False for r in rows))

    payload = {
        "script": "scripts/verify_handover_sample.py",
        "sample_dir": str(base),
        "path_root": "samples/ (索引与 JSONL 中的 path 均相对该目录)",
        "rows": len(rows),
        "index_entries": len(idx),
        "checks": rep.to_dict(),
        "overall_pass": rep.all_ok(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"样例目录: {base}")
        print(f"题数 {len(rows)}，索引条目 {len(idx)}")
        rep.print()
        n_total = sum(len(v) for v in rep.groups.values())
        n_fail = sum(1 for v in rep.groups.values() for _, ok, _ in v if not ok)
        print(f"\n{'=' * 62}")
        print(f"总计 {n_total - n_fail}/{n_total} 项通过 -> "
              f"{'✅ 验收通过' if rep.all_ok() else '❌ 验收未通过'}")
        print(f"-> {OUT}")
    return 0 if rep.all_ok() else 1


if __name__ == "__main__":
    sys.exit(main())
