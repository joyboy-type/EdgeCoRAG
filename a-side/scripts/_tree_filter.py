"""在远端 tree 清单里按子串/前缀筛选文件（只读分析辅助）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    tree = Path(sys.argv[1])
    pats = sys.argv[2:]
    d = json.loads(tree.read_text(encoding="utf-8"))
    rows = [
        (e.get("size"), e["path"])
        for e in d["entries"]
        if e["type"] == "blob" and (not pats or any(p.lower() in e["path"].lower() for p in pats))
    ]
    for size, path in rows:
        print(f"{size if size is not None else ''} {path}")
    print(f"-- {len(rows)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
