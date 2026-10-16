"""Read-only verification of A's external per-file hash index. Never downloads or repairs."""
import argparse
import csv
import json
from pathlib import Path
from batch_inputs import sha,external


def verify(root,index_path,decode=False):
    root=root.resolve();errors=[];checked=0;decoded=0;seen=set()
    with index_path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if not rows:raise ValueError('Empty external file index')
    for r in rows:
        name=r['rel_path']
        if name in seen:errors.append({'path':name,'error':'duplicate index path'});continue
        seen.add(name)
        try:
            p=external(root,name)
            if p.stat().st_size!=int(r['bytes']):raise ValueError('byte count differs')
            if sha(p)!=r['sha256']:raise ValueError('SHA-256 differs')
            checked+=1
            if decode and p.suffix.lower() in ['.jpg','.jpeg','.png','.webp']:
                from PIL import Image
                with Image.open(p) as im:im.load()
                decoded+=1
        except Exception as e:errors.append({'path':name,'error':type(e).__name__+': '+str(e)})
    return {'read_only':True,'hash_index_sha256':sha(index_path),'declared_files':len(rows),'verified_files':checked,
            'decoded_images':decoded,'decode_requested':decode,'errors':errors,'passed':not errors,
            'scope':'Per-file transport/decode only; semantic D1 review is a separate A artifact, not inferred from hashes.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--hash-index',type=Path,required=True);p.add_argument('--decode',action='store_true')
    a=p.parse_args();result=verify(a.root,a.hash_index,a.decode);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 2)
