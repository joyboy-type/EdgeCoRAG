"""Retrieve the pinned public score.py as inert text; never execute the scorer.

Reproduce: $PY analysis/next_stage_20261019/fetch_official_source.py --out <NEW_CACHE_FILE>
Network/source mismatch is a blocker. Existing caches are checked, never replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from verify_official_schema import SOURCE_SHA, SOURCE_URL


def check_bytes(data):
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:
        raise ValueError('Pinned official source SHA mismatch')
    return data


def fetch(out):
    out=Path(out)
    if out.exists():
        check_bytes(out.read_bytes());method='verified_existing_cache'
    else:
        with urllib.request.urlopen(SOURCE_URL,timeout=30) as response:
            data=check_bytes(response.read(1024*1024))
        with out.open('xb') as stream:stream.write(data)
        method='downloaded_pinned_public_source'
    return dict(status='verified',method=method,url=SOURCE_URL,sha256=SOURCE_SHA,
                bytes=out.stat().st_size,official_scorer_executed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();print(json.dumps(fetch(args.out),indent=2))
if __name__=='__main__':main()
