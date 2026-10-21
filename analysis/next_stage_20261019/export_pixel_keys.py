"""Export only byte-hash columns and coarse gray32 key from an existing CSV.

Reproduce: $PY analysis/next_stage_20261019/export_pixel_keys.py \
 --source "$LOCAL_PIXEL_TABLE" --source-sha256 "$PIXEL_TABLE_SHA256" \
 --out "$NEW_KEYS_CSV" --receipt "$NEW_RECEIPT_JSON"
No image/Pillow/model/vector imports; no pixel recomputation.
Quantization q=round(v/255*11) is evaluated with exact integer arithmetic:
floor((22*v+255)/510); no uint8 v lies exactly on a half boundary.
Pack two low nibbles per byte: first pixel HIGH4 bits, second pixel LOW4 bits.
1024 row-major gray bytes become512 packed bytes, then SHA256 lowercase hex.
This bit order is explicit for A to replicate; do not infer a different packing.
raw/q95 are copied unchanged. l1b inherits upstream gray32 decoder sensitivity;
coarse quantization does NOT establish cross-decoder invariance or equivalence.
"""
import argparse,csv,hashlib,io,json,re
from pathlib import Path

FIELDS=['sha256_raw','sha256_q95','l1b']
LUT=bytes((22*v+255)//510 for v in range(256))
LIMIT=5*1024**2

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()

def pack_gray32(raw):
 if len(raw)!=1024:raise ValueError('gray32 must be1024 uint8 row-major bytes')
 q=raw.translate(LUT)
 return bytes(((q[i]&15)<<4)|(q[i+1]&15) for i in range(0,1024,2))

def export(source,out,source_sha256,expected_rows=18955):
 source,out=Path(source),Path(out)
 if out.exists():raise FileExistsError(out)
 if not re.fullmatch('[0-9a-f]{64}',source_sha256 or '') or sha(source)!=source_sha256:
  raise ValueError('Source table SHA mismatch')
 rows=[]
 with source.open(newline='',encoding='utf-8-sig') as f:
  reader=csv.DictReader(f)
  if not {'sha256_raw','sha256_q95','gray32'}.issubset(reader.fieldnames or []):raise ValueError('Missing source columns')
  for r in reader:
   if any(not re.fullmatch('[0-9a-f]{64}',r[k] or '') for k in ['sha256_raw','sha256_q95']):raise ValueError('Invalid byte hash')
   if not re.fullmatch('[0-9a-f]{2048}',r['gray32'] or ''):raise ValueError('Invalid gray32 hex')
   digest=hashlib.sha256(pack_gray32(bytes.fromhex(r['gray32']))).hexdigest()
   rows.append(dict(sha256_raw=r['sha256_raw'],sha256_q95=r['sha256_q95'],l1b=digest))
 if len(rows)!=expected_rows:raise ValueError('Fixed row count mismatch')
 if sha(source)!=source_sha256:raise ValueError('Source changed during export')
 text=io.StringIO(newline='');writer=csv.DictWriter(text,fieldnames=FIELDS,lineterminator='\n');writer.writeheader();writer.writerows(rows)
 data=text.getvalue().encode('utf-8')
 if len(data)>=LIMIT:raise ValueError('Key table must be strictly below5MiB')
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('xb') as f:f.write(data)
 return dict(rows=len(rows),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),columns=FIELDS,
  source_sha256=source_sha256,source_bytes=source.stat().st_size,under_5MiB=len(data)<LIMIT,
  quantization='round(v/255*11), exact uint8 integer implementation (22*v+255)//510; no ties possible',
  packing='row-major; first quantized pixel high nibble, second low nibble; each q masked0x0f',
  packed_bytes_per_image=512,raw_q95_copied_unchanged=True,source_pixels_recomputed=False,
  raw_provenance='ZIP original member bytes; same origin as A parquet bytes: 未验证',
  decoder_versions='B Pillow12.3.0/libjpeg6.2(turbo3.1.4.1); A libjpeg8.0',
  decoder_effect='raw/q95 copied keys are decoder-independent during export; l1b derives from gray32 and may change across decoder versions; no invariance claimed',
  l1b_scope='Coarse candidate matching only; quantization may merge different gray32 arrays and does not guarantee semantic or pixel equivalence',
  input_images_or_vectors_read=False,output_contains_gray32_ahash_pixelsha=False)

def main():
 p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
 p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True)
 p.add_argument('--out',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 if a.receipt.exists() or a.receipt.resolve()==a.out.resolve():raise FileExistsError('New separate receipt required')
 result=export(a.source,a.out,a.source_sha256)
 result['local_source_table_path']=str(a.source.resolve())
 result['private_source_not_published']=True
 a.receipt.parent.mkdir(parents=True,exist_ok=True)
 with a.receipt.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
