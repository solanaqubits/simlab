from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_execution_series as s
import geek_work_manuscript_batch as b


class SeriesReadBoundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def tiny_capture(self):
        files={'a':b'1234','b':b'5678'}
        for name,raw in files.items():(self.root/name).write_bytes(raw)
        meta=s.m.encoded(dict(files={n:s.m.sha(v) for n,v in files.items()}));(self.root/'manifest.json').write_bytes(meta)
        return meta,s.m.sha(meta)
    def test_capture_read_uses_residual_after_manifest(self):
        meta,h=self.tiny_capture();limits=[];original=s.m.read
        def read(path,limit):limits.append((path.name,limit));return original(path,limit)
        with patch.object(s.runner,'verify'),patch.object(s.m,'read',side_effect=read),self.assertRaises(ValueError):s.capture(self.root,h,len(meta)+5)
        self.assertEqual(limits[-2:],[('a',5),('b',1)])
    def test_exact_capture_boundary(self):
        meta,h=self.tiny_capture()
        with patch.object(s.runner,'verify'):
            files=s.capture(self.root,h,len(meta)+8)
            self.assertEqual(sum(map(len,files.values())),len(meta)+8)
            with self.assertRaises(ValueError):s.capture(self.root,h,len(meta)-1)
    def test_invalid_budgets_do_not_verify(self):
        with patch.object(s.runner,'verify',side_effect=AssertionError('no verification')):
            for v in (0,-1,True,1.5,s.MAX_TOTAL+1):
                with self.assertRaises(ValueError):s.capture(self.root,'0'*64,v)
    def test_build_passes_remaining_budget(self):
        calls=[]
        def capture(path,h,budget):
            calls.append(budget)
            if len(calls)==1:return {'a':b'123'}
            raise ValueError('stop second copy')
        with patch.object(s,'capture',side_effect=capture),self.assertRaisesRegex(ValueError,'second copy'):
            s.build([self.root/'a',self.root/'b'],['0'*64,'1'*64],self.root/'output')
        self.assertEqual(calls,[s.MAX_TOTAL,s.MAX_TOTAL-3])
    def test_verify_passes_remaining_budget(self):
        meta=b'{}';(self.root/'manifest.json').write_bytes(meta);(self.root/'selection.json').write_bytes(s.m.encoded(dict(schema=s.SCHEMA,anchors=['0'*64,'1'*64])))
        calls=[]
        def capture(path,h,budget):
            calls.append(budget)
            if len(calls)==1:return {'a':b'123'}
            raise ValueError('stop second replay')
        with patch.object(s,'capture',side_effect=capture),self.assertRaisesRegex(ValueError,'second replay'):s.verify(self.root,s.m.sha(meta))
        self.assertEqual(calls,[s.MAX_TOTAL,s.MAX_TOTAL-3])
    def test_generated_report_limit_before_write(self):
        with patch.object(s,'summarize',return_value={'large':'x'*100}),patch.object(s.k,'MAX_FILE',50),self.assertRaisesRegex(ValueError,'generated metadata'):
            s.contents([('0'*64,{})])
    def test_manifest_limit(self):
        with patch.object(s.m,'MAX_ARTIFACT',10),self.assertRaisesRegex(ValueError,'manifest byte'):s.manifest({'a':b'x'})
    def test_unexpected_directory_entry_stops_iteration(self):
        seen=[]
        def stream():
            for i in range(10000):seen.append(i);yield SimpleNamespace(name='unexpected'+str(i))
        @contextmanager
        def scan(path):yield stream()
        with patch.object(b.os,'scandir',scan),self.assertRaisesRegex(ValueError,'file set'):b.directory(self.root,{'required'})
        self.assertEqual(seen,[0])
    def test_directory_set_match_missing_and_extra(self):
        (self.root/'a').write_bytes(b'');(self.root/'b').mkdir();b.directory(self.root,{'b','a'})
        with self.assertRaises(ValueError):b.directory(self.root,{'a'})
        with self.assertRaises(ValueError):b.directory(self.root,{'a','b','c'})
    def test_empty_and_unsafe_root(self):
        b.directory(self.root,set())
        with self.assertRaises(ValueError):b.directory(self.root/'missing',set())
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):b.directory(link,{'link'})

if __name__=='__main__':unittest.main()
