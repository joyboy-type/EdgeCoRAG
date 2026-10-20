import sys,unittest,tempfile,hashlib,io,json,csv,zipfile
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
import pixel_identity as p
class PixelIdentityTests(unittest.TestCase):
 def image_bytes(self,image):
  out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
 def test_rgb_hash_uses_exact_bytes_then_dimension_suffix(self):
  im=Image.new('RGB',(2,1));im.putdata([(1,2,3),(4,5,6)])
  result=p.fingerprint(self.image_bytes(im))
  self.assertEqual(result['pixel_sha'],hashlib.sha256(b'\x01\x02\x03\x04\x05\x06|2x1').hexdigest())
  self.assertEqual((result['w'],result['h']),(2,1))
  self.assertEqual(len(result['gray32']),2048)
 def test_ahash_strict_mean_and_row_major_low_bit(self):
  im=Image.new('RGB',(8,8),(0,0,0));im.putpixel((0,0),(255,255,255))
  self.assertEqual(p.fingerprint(self.image_bytes(im))['ahash'],'0000000000000001')
  flat=p.fingerprint(self.image_bytes(Image.new('RGB',(8,8),(128,128,128))))
  self.assertEqual(flat['ahash'],'0000000000000000')
  self.assertEqual(flat['gray32'],'80'*1024)
 def test_stream_preserves_first_row_on_failure_without_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);raw=self.image_bytes(Image.new('RGB',(1,1),(1,2,3)));rows=[dict(id='image:'+'b'*64,sha256=hashlib.sha256(raw).hexdigest(),archive_path='one.png'),dict(id='image:'+'c'*64,sha256='0'*64,archive_path='two.png')]
   with zipfile.ZipFile(root/'in.zip','w') as z:z.writestr('one.png',raw);z.writestr('two.png',raw)
   result=p.stream(rows,root/'in.zip',root/'out',provenance={'scope':'synthetic'})
   self.assertEqual(result['status'],'failed_partial_no_retry');self.assertEqual(result['completed_rows'],1)
   with (root/'out/pixel_identity_18955.csv').open() as f:records=list(csv.DictReader(f))
   self.assertEqual(len(records),1);self.assertEqual(records[0]['sha256_raw'],rows[0]['sha256'])
   self.assertEqual(records[0]['source'],'zip_original_bytes')
   with self.assertRaises(FileExistsError):p.stream(rows,root/'in.zip',root/'out',{})
