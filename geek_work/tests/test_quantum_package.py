import io
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_quantum_package as q


def archive(entries):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w') as z:
        for n,v in entries:z.writestr(n,v)
    return f.getvalue()


def fixture():
    return [('invsqrt.kmx',b'synthetic'),('dqi.kmb',b'synthetic'),
            ('dfthcsos/angle_k_0.kmx',b'synthetic'),
            ('dfthcsos/submission.npz',archive([(n,b'NOT_A_NUMPY_ARRAY') for n in sorted(q.NPZ_KEYS)]))]


class QuantumPackageTests(unittest.TestCase):
    def inspect(self,rows):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'p.zip';p.write_bytes(archive(rows));return q.inspect(p)
    def test_layout_is_not_semantics(self):
        r=self.inspect(fixture());self.assertEqual(r['status'],'LAYOUT_ONLY')
        self.assertFalse(r['submission_ready']);self.assertFalse(r['numpy_headers_and_values_checked'])
    def test_missing_task(self):
        with self.assertRaisesRegex(ValueError,'ambiguous_dqi'):self.inspect(fixture()[::2])
    def test_two_formats(self):
        with self.assertRaisesRegex(ValueError,'ambiguous_invsqrt'):self.inspect(fixture()+[('invsqrt.kmb',b'x')])
    def test_gap(self):
        with self.assertRaisesRegex(ValueError,'angle_sequence'):self.inspect(fixture()+[('dfthcsos/angle_k_2.kmx',b'x')])
    def test_duplicate_angle_format(self):
        with self.assertRaisesRegex(ValueError,'angle_sequence'):self.inspect(fixture()+[('dfthcsos/angle_k_0.kmb',b'x')])
    def test_traversal(self):
        for n in ('../x','/x','dfthcsos/../x','x\\y','x//y','./x'):
            with self.subTest(n=n),self.assertRaisesRegex(ValueError,'path'):self.inspect(fixture()+[(n,b'x')])
    def test_symlink(self):
        i=zipfile.ZipInfo('link');i.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaisesRegex(ValueError,'special_file'):self.inspect(fixture()+[(i,b'/etc/passwd')])
    def test_resource_bound(self):
        with patch.object(q,'MAX_BYTES',10),self.assertRaisesRegex(ValueError,'resource_limit'):self.inspect(fixture())
    def test_nested_resource_bound(self):
        rows=fixture();rows[-1]=(rows[-1][0],archive([(n,b'x'*10000) for n in q.NPZ_KEYS]))
        with patch.object(q,'MAX_BYTES',len(archive(rows))+100),self.assertRaisesRegex(ValueError,'resource_limit'):self.inspect(rows)
    def test_npz_keys(self):
        rows=fixture();rows[-1]=(rows[-1][0],archive([('evil.npy',b'x')]))
        with self.assertRaisesRegex(ValueError,'npz_keys'):self.inspect(rows)
    def test_unexpected_payload(self):
        with self.assertRaisesRegex(ValueError,'unexpected_file'):self.inspect(fixture()+[('run.py',b'x')])
    def test_empty(self):
        rows=fixture();rows[0]=('invsqrt.kmx',b'')
        with self.assertRaisesRegex(ValueError,'empty_file'):self.inspect(rows)
    def test_allowed_directory(self):
        self.assertEqual(self.inspect(fixture()+[('dfthcsos/',b'')])['angle_count'],1)
    def test_corrupt_zip(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(b'not zip')
            with self.assertRaises(zipfile.BadZipFile):q.inspect(p)
    def test_hash_changes(self):
        a=fixture();r=self.inspect(a);a[0]=(a[0][0],b'changed')
        self.assertNotEqual(r['archive_sha256'],self.inspect(a)['archive_sha256'])
