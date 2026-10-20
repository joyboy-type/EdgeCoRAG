"""检查本地 MRAG-Bench parquet 分片的 schema 与图像列存法（只读）。

用于确认可以完全离线读取数据，避免 streaming=True 触发联网解析。
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

DATA = Path(r"E:\EdgeCoRAG-A-store\datasets\mrag_bench\43620fde4044bb150e158c67ad7af6b6b11e1da2\data")


def main() -> int:
    shards = sorted(DATA.glob("test-*.parquet"))
    print(f"shards={len(shards)}")
    sh = shards[0]
    pf = pq.ParquetFile(sh)
    print(f"file={sh.name} rows={pf.metadata.num_rows}")
    print("--- schema ---")
    print(pf.schema_arrow)
    t = pf.read_row_group(0).slice(0, 1)
    row = t.to_pylist()[0]
    print("--- first row keys ---", list(row.keys()))
    for k, v in row.items():
        if isinstance(v, dict):
            print(f"{k}: dict keys={list(v.keys())}")
        elif isinstance(v, list):
            print(f"{k}: list len={len(v)} elem0={type(v[0]).__name__ if v else None}")
            if v and isinstance(v[0], dict):
                print(f"    elem0 keys={list(v[0].keys())}")
        else:
            s = str(v)
            print(f"{k}: {type(v).__name__} {s[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
