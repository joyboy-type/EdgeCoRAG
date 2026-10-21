import sys,unittest,tempfile,csv,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
import export_pixel_keys as e
class PixelKeysTests(unittest.TestCase):
 def test_quantization_matches_literal_formula_and_nibble_order(self):
  raw=bytes(range(256))*4
  expected=bytes((round(raw[i]/255*11)&15)<<4 | (round(raw[i+1]/255*11)&15) for i in range(0,1024,2))
  self.assertEqual(e.pack_gray32(raw),expected)
  self.assertEqual(len(expected),512)
  self.assertEqual(e.pack_gray32(bytes([0,255])*512),b'\x0b'*512)
  self.assertEqual(e.pack_gray32(bytes([255,0])*512),b'\xb0'*512)
 def test_export_only_three_columns_preserves_source_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'main.csv'
   with source.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['sha256_raw','sha256_q95','gray32','pixel_sha','ahash']);w.writeheader()
    w.writerow(dict(sha256_raw='a'*64,sha256_q95='b'*64,gray32='00ff'*512,pixel_sha='x',ahash='y'))
   original=source.read_bytes();pin=hashlib.sha256(original).hexdigest()
   receipt=e.export(source,root/'keys.csv',pin,expected_rows=1)
   with (root/'keys.csv').open() as f:
    reader=csv.DictReader(f);self.assertEqual(reader.fieldnames,['sha256_raw','sha256_q95','l1b']);row=next(reader)
   self.assertEqual(row,{'sha256_raw':'a'*64,'sha256_q95':'b'*64,'l1b':hashlib.sha256(b'\x0b'*512).hexdigest()})
   self.assertEqual(source.read_bytes(),original);self.assertEqual(receipt['rows'],1)
   with self.assertRaises(FileExistsError):e.export(source,root/'keys.csv',pin,expected_rows=1)
 def test_bad_source_hash_count_and_gray32_fail_before_output(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'main.csv';p.write_text('sha256_raw,sha256_q95,gray32\n'+'a'*64+','+'b'*64+','+'00'*1024+'\n')
   pin=hashlib.sha256(p.read_bytes()).hexdigest()
   for wanted,rows in [('0'*64,1),(pin,2)]:
    with self.subTest(wanted=wanted,rows=rows),self.assertRaises(ValueError):e.export(p,root/'out.csv',wanted,expected_rows=rows)
    self.assertFalse((root/'out.csv').exists())
   with self.assertRaises(ValueError):e.pack_gray32(b'\x00'*1023)
   p.write_text(p.read_text().replace('00'*1024,'zz'*1024))
   with self.assertRaises(ValueError):e.export(p,root/'out.csv',hashlib.sha256(p.read_bytes()).hexdigest(),expected_rows=1)
   self.assertFalse((root/'out.csv').exists())
