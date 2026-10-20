"""把 artifacts.json 的哈希口径统一为 LF（P0 修复：清单行尾口径）。

问题（B 在干净检出 89ddb29 上实测）：清单里的 sha256/bytes 是在 **Windows CRLF 工作树**
上算的，而 git 提交与干净检出是 LF，于是 36 个产物全部 sha+size mismatch
（差值恰好 = rows+1 字节/文件）。产物内容没有损坏，是**清单口径不可复算**。

本脚本做的事（幂等）：
  1. 逐产物读取磁盘字节，做 `\\r\\n -> \\n` 归一化（仅转换 CRLF；孤立 CR 不处理，若存在会报错）；
  2. 用归一化后的字节重算 sha256 与 bytes；
  3. 在 `summary` 写入 `hash_normalization: "LF"`、统计有多少文件原本是 CRLF；
  4. `--apply` 时重写 artifacts.json（其余字段原样保留）。

不碰任何产物文件，只改清单。默认 dry-run。

用法：
    python a-side/scripts/a23_fix_manifest_line_endings.py --iface a-side/retrieval_if_v1            # 只看差异
    python a-side/scripts/a23_fix_manifest_line_endings.py --iface a-side/retrieval_if_v1 --apply    # 写回清单
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import a00_paths  # noqa: E402
except ModuleNotFoundError:  # 本地 scripts/ 布局
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "a-side" / "scripts"))
    import a00_paths  # noqa: E402

LF_NOTE = (
    "清单哈希按 LF 字节计算（与 git 提交内容一致）。工作树若因 core.autocrlf 变成 CRLF，"
    "a17 会先做 \\r\\n->\\n 归一化再比对；--strict-lf 则直接拒绝 CRLF 并给修复提示。"
)


def normalized(path: Path) -> tuple[bytes, bool]:
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    return lf, raw != lf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    iface = a00_paths.iface_root(args.iface)
    man_p = iface / "artifacts.json"
    man = json.loads(man_p.read_text(encoding="utf-8"))

    changed, same, crlf_files, lone_cr = [], [], [], []
    for art in man["artifacts"]:
        p = iface / art["path"]
        if not p.exists():
            print(f"缺文件: {art['path']}", file=sys.stderr)
            return 2
        lf, had_crlf = normalized(p)
        if had_crlf:
            crlf_files.append(art["path"])
        if b"\r" in lf:
            lone_cr.append(art["path"])
        sha = hashlib.sha256(lf).hexdigest()
        rec = {"path": art["path"], "old_sha": art["sha256"][:12], "old_bytes": art["bytes"],
               "new_sha": sha[:12], "new_bytes": len(lf), "had_crlf": had_crlf}
        if sha == art["sha256"] and len(lf) == art["bytes"]:
            same.append(rec)
        else:
            changed.append(rec)
            art["sha256"] = sha
            art["bytes"] = len(lf)

    if lone_cr:
        print(f"发现孤立 \\r（不是 CRLF），拒绝自动处理，请先人工确认: {lone_cr[:5]}", file=sys.stderr)
        return 3

    man.setdefault("summary", {})["hash_normalization"] = "LF"
    man["summary"]["hash_normalization_note"] = LF_NOTE
    man["summary"]["line_endings"] = {
        "policy": "LF",
        "files_that_were_crlf_before_fix": len(crlf_files),
        "files_unchanged": len(same),
        "files_rehashed": len(changed),
    }

    print(f"产物 {len(man['artifacts'])} 个；原本 CRLF 的 {len(crlf_files)} 个；"
          f"与 LF 口径已一致 {len(same)} 个；需重算 {len(changed)} 个")
    for r in changed[:6]:
        print(f"  {r['path']}: {r['old_sha']}/{r['old_bytes']} -> {r['new_sha']}/{r['new_bytes']}")
    if len(changed) > 6:
        print(f"  ... 其余 {len(changed) - 6} 个同型")

    if args.apply:
        already_lf = (man.get("summary") or {}).get("hash_normalization") == "LF"
        if not changed and already_lf:
            # 幂等：口径已是 LF 且没有需要重算的条目时，连计数也不改，保证清单字节稳定
            print("清单已是 LF 口径且无需重算，未写回")
            return 0
        man_p.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"已写回 {man_p}")
    else:
        print("dry-run：未写回（加 --apply 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
