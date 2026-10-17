import unittest,subprocess,struct,json
from codec import decode
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Standalone(unittest.TestCase):
 def run_case(self,name):
  raw=(ROOT/'tests/fixtures'/name).read_bytes()
  p=subprocess.run([str(ROOT/'.lake/build/bin/sql_stream_reader'),'--context',str(ROOT/'tests/fixtures/minimum-context.json'),'--budget','1'],input=len(raw).to_bytes(4,'big')+raw,capture_output=True,timeout=10,cwd='/')
  self.assertEqual(p.returncode,0,p.stderr)
  bs=p.stdout;self.assertEqual(bs[:5],b'\0\0\0\1\1');n=int.from_bytes(bs[5:9],'big');self.assertEqual(len(bs),9+n);return decode(bs[9:])
 def test_minimum(self):self.assertEqual(self.run_case('minimum-request.json')['status'],'accepted');self.assertEqual(self.run_case('minimum-request.json')['result_bits'],'0000000000000000')
 def test_wrong_instance(self):self.assertEqual(self.run_case('other-request.json')['status'],'instance_mismatch')
 def test_partition(self):
  p=subprocess.run([str(ROOT/'.lake/build/bin/sql_stream_probe')],input=b'4 1 0 1,0 1\n',capture_output=True,timeout=5,cwd='/');self.assertEqual(p.stdout,b'done:0,1,0,1\n')
