"""Stream B original ZIP images into A f597650 pixel-fingerprint columns.

Use: $PY b-side/pixel_identity.py --project "$PROJECT" --spec "$A_SPEC" \
 --spec-commit f59765069e4f069e8b84974adb33e2fb5188efb3 --out "$NEW_PRIVATE_OUT"
No images/RGB files are copied or materialized on disk; one decoded image lives
in memory at a time. Each completed CSV row is flushed and fsynced. First error
preserves partial output, no retries, and any existing output directory is refused.
Algorithm: PIL open original bytes, first frame, no EXIF transpose/ICC transform,
convert RGB; SHA256(rgb.tobytes()+b'|'+f'{w}x{h}'.encode()); LANCZOS8x8 L hash,
strict >mean with row-major bit i shifted LEFT i; LANCZOS32x32 L bytes.hex().
Source is explicitly ZIP-original bytes, NOT A's parquet source. Version mismatch
or lossy JPEG reencoding forbids assuming exact pixel hashes are invariant. This
tool computes B descriptors only; it does not compare to A or claim source parity.
Actual CSV is private (>5MiB, contains derived gray32 images); never auto-publish.
"""
import argparse,csv,hashlib,io,json,os,shutil,time,warnings,zipfile
from pathlib import Path
from collections import Counter
from PIL import Image,features
import PIL

FIELDS=['sha256_q95','sha256_raw','pixel_sha','ahash','gray32','w','h','pillow','libjpeg','source']

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def save(path,data):
 temp=path.with_name(path.name+'.next')
 with temp.open('w') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 temp.replace(path)

def fingerprint(raw):
 with Image.open(io.BytesIO(raw)) as image:
  image.load()
  with image.convert('RGB') as rgb:
   w,h=rgb.size;digest=hashlib.sha256(rgb.tobytes());digest.update(f'|{w}x{h}'.encode())
   with rgb.convert('L') as gray:
    with gray.resize((8,8),Image.Resampling.LANCZOS) as small:values=list(small.get_flattened_data())
    mean=sum(values)/64;bits=sum((value>mean)<<i for i,value in enumerate(values))
    with gray.resize((32,32),Image.Resampling.LANCZOS) as small:gray32=small.tobytes().hex()
 return dict(pixel_sha=digest.hexdigest(),ahash=f'{bits:016x}',gray32=gray32,w=w,h=h)

def stream(rows,archive,out,provenance):
 out=Path(out)
 if out.exists():raise FileExistsError(out)
 if shutil.disk_usage(out.parent).free<512*1024**2+len(rows)*4096:raise ValueError('Insufficient disk reserve for descriptor-only streaming')
 out.mkdir();start=time.monotonic();completed=0;formats=Counter();warning_counts=Counter();pixels=set();error=None
 receipt={'status':'started','expected_rows':len(rows),'completed_rows':0,'source':'zip_original_bytes','Pillow':PIL.__version__,
  'libjpeg':features.version('jpg'),'libjpeg_turbo':features.version_feature('libjpeg_turbo') if features.check_feature('libjpeg_turbo') else 'not_used',
  'decode_policy':'first frame; RGB; no EXIF transpose, ICC or resize before pixel_sha','provenance':provenance,
  'source_matches_A_parquet_requirement':False,'A_B_intersection_computed':False,
  'limits':['B source is ZIP original bytes, not parquet; source deviation explicit, needs A acknowledgement.',
            'B libjpeg differs from A8.0; no cross-version calibration, no cross-version intersection permitted.',
            'JPEG lossy reencoding is not guaranteed pixel-hash invariant.']}
 save(out/'receipt.json',receipt)
 try:
  with zipfile.ZipFile(archive) as z,(out/'pixel_identity_18955.csv').open('x',newline='') as f,(out/'warnings.jsonl').open('x') as warning_file:
   writer=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');writer.writeheader();f.flush();os.fsync(f.fileno())
   for i,r in enumerate(rows):
    if i%250==0 and shutil.disk_usage(out).free<512*1024**2:raise ValueError('Disk reserve below512MiB')
    raw=z.read(r['archive_path']) # ZipFile verifies original-member CRC; never reads q95 cache.
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=r['sha256']:raise ValueError('Original archive member SHA differs at row '+str(i+1))
    with warnings.catch_warnings(record=True) as observed:
     warnings.simplefilter('always');values=fingerprint(raw)
    for warning in observed:
     warning_counts[warning.category.__name__+': '+str(warning.message)]+=1
     warning_file.write(json.dumps({'row':i+1,'category':warning.category.__name__,'message':str(warning.message)})+'\n');warning_file.flush()
    row={'sha256_q95':r['id'].removeprefix('image:'),'sha256_raw':digest,**values,'pillow':PIL.__version__,'libjpeg':features.version('jpg'),'source':'zip_original_bytes'}
    writer.writerow(row);f.flush();os.fsync(f.fileno());completed+=1;pixels.add(values['pixel_sha'])
    if completed%250==0 or completed==len(rows):
     progress={'completed_rows':completed,'expected_rows':len(rows),'elapsed_seconds':time.monotonic()-start,'free_bytes':shutil.disk_usage(out).free}
     save(out/'progress.json',progress);print(json.dumps(progress),flush=True)
 except Exception as e:error={'type':type(e).__name__,'message':str(e),'row':completed+1}
 receipt.update(status='failed_partial_no_retry' if error else 'completed_descriptors',completed_rows=completed,
  elapsed_seconds=time.monotonic()-start,unique_pixel_sha=len(pixels),warnings=dict(warning_counts),error=error if error else 'none',
  output={'path':'pixel_identity_18955.csv','rows':completed,'sha256':sha(out/'pixel_identity_18955.csv'),'bytes':(out/'pixel_identity_18955.csv').stat().st_size},
  output_source_bytes_verified=completed,full_RGB_files_written=0,disk_free_bytes=shutil.disk_usage(out).free)
 save(out/'receipt.json',receipt);return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--spec-commit',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 project=a.project.resolve();base=project/'work/pre-experiment-20261018/mrag-independent-corpus'
 controls=project/'work/instance394-preflight/formal-retrieval-embeddinggemma2-backup/controls/retrieval-formal.approved.json'
 raw=json.loads(controls.read_text())['corpus'];index_path=base/'image-index.complete.private.jsonl';index={str((base/r['path']).resolve()):r for r in map(json.loads,index_path.read_text().splitlines())}
 integrity=json.loads((base/'corpus-integrity-complete.json').read_text())
 if sha(index_path)!=integrity['index_sha256']:raise ValueError('Archived raw index SHA drift')
 rows=[]
 for r in raw:
  source=index[str((project/r['path']).resolve())]
  if r['sha256']!=source['sha256'] or r['id']!='image:'+source['jpeg95_rgb_sha256']:raise ValueError('Raw/q95 identity mapping differs')
  rows.append(dict(r,archive_path=source['archive_path']))
 if len(rows)!=18955:raise ValueError('Expected18955 frozen index rows')
 ar=json.loads((base/'archive-receipt.json').read_text());archive=Path(ar['archive_path'])
 archive_digest=sha(archive)
 if archive.stat().st_size!=ar['bytes'] or archive_digest!=ar['sha256']:raise ValueError('Original ZIP binding differs')
 provenance={'controls_sha256':sha(controls),'image_index_sha256':sha(index_path),'archive_sha256':archive_digest,
  'archive_bytes':archive.stat().st_size,'spec_commit':a.spec_commit,'spec_sha256':sha(a.spec),'code_sha256':sha(__file__),
  'q95_column':'historical frozen alias suffix, verified against archived jpeg95_rgb_sha256; not newly reencoded',
  'raw_column':'new SHA256 over original ZIP member bytes, checked against archive source index'}
 result=stream(rows,archive,a.out,provenance)
 (a.out/'pixel_identity_spec_f597650.md').write_bytes(a.spec.read_bytes())
 print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='completed_descriptors' else 1)

if __name__=='__main__':main()
