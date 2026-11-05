from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_study_executions as a


class StudySnapshotBoundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def sample(self):
        (self.root/'a').write_bytes(b'abc');meta=a.m.encoded(dict(files={'a':a.m.sha(b'abc')}));(self.root/'manifest.json').write_bytes(meta);return a.m.sha(meta)
    def test_early_entry_refusal_before_reading(self):
        seen=[]
        class Entry:
            def __init__(self,i):self.name=str(i)
            def is_symlink(self):return False
            def is_dir(self,follow_symlinks=False):return False
            def is_file(self,follow_symlinks=False):return True
        def generate():
            for i in range(10000):seen.append(i);yield Entry(i)
        @contextmanager
        def scan(path):yield generate()
        with patch.object(a.os,'scandir',scan),patch.object(a.m,'read',side_effect=AssertionError('no payload read')):
            with self.assertRaisesRegex(ValueError,'entry limit'):a.snapshot(self.root,'0'*64,entry_budget=3)
        self.assertEqual(len(seen),4)
    def test_combined_directory_file_count(self):
        (self.root/'a').mkdir();(self.root/'a/b').write_bytes(b'x');(self.root/'z').mkdir()
        with self.assertRaisesRegex(ValueError,'entry limit'):a.snapshot(self.root,'0'*64,entry_budget=2)
    def test_budget_capped_reads(self):
        (self.root/'a').write_bytes(b'1234');(self.root/'b').write_bytes(b'5678');limits=[];original=a.m.read
        def read(path,limit):limits.append(limit);return original(path,limit)
        with patch.object(a.m,'read',side_effect=read),self.assertRaises(ValueError):a.snapshot(self.root,'0'*64,byte_budget=5)
        self.assertEqual(limits,[5,1])
    def test_exact_boundary_and_canonical_content(self):
        h=self.sample();size=sum(p.stat().st_size for p in self.root.iterdir());files,dirs=a.snapshot(self.root,h,byte_budget=size,entry_budget=2)
        self.assertEqual(list(files),['a','manifest.json']);self.assertEqual(dirs,[])
        with self.assertRaises(ValueError):a.snapshot(self.root,h,byte_budget=size-1)
    def test_fifo_symlink_and_bad_names(self):
        p=self.root/'fifo';os.mkfifo(p)
        with patch.object(a.m,'read',side_effect=AssertionError('no read')),self.assertRaises(ValueError):a.snapshot(self.root,'0'*64)
        p.unlink();p.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):a.snapshot(self.root,'0'*64)
        p.unlink();(self.root/'.hidden').mkdir()
        with self.assertRaises(ValueError):a.snapshot(self.root,'0'*64)
    def test_invalid_budget_types_and_empty_root(self):
        for budget in (-1,True,1.5,a.MAX_TOTAL+1):
            with self.assertRaises(ValueError):a.snapshot(self.root,'0'*64,byte_budget=budget)
        for budget in (-1,True,1.5,a.MAX_FILES+1):
            with self.assertRaises(ValueError):a.snapshot(self.root,'0'*64,entry_budget=budget)
        with self.assertRaisesRegex(ValueError,'manifest missing'):a.snapshot(self.root,'0'*64)
    def test_hashes_and_empty_directories(self):
        h=self.sample();(self.root/'empty').mkdir();files,dirs=a.snapshot(self.root,h)
        self.assertEqual(dirs,['empty']);(self.root/'a').write_bytes(b'changed')
        with self.assertRaises(ValueError):a.snapshot(self.root,h)
    def test_derive_passes_remaining_budgets(self):
        # Isolated wiring fixture: fail at the second capture, before any purported report.
        report={'nodes':[{'id':'base'}]};blobs={'report.json':a.m.encoded(report),'manifest.json':b'{}'};calls=[]
        def capture(path,anchor,**kwargs):
            calls.append(kwargs)
            if len(calls)==1:return blobs,[]
            raise ValueError('stop at second snapshot')
        with patch.object(a.study,'verify'),patch.object(a.series,'verify'),patch.object(a,'snapshot',side_effect=capture):
            with self.assertRaisesRegex(ValueError,'second snapshot'):a.derive(self.root,'0'*64,[('base',self.root,'1'*64)])
        self.assertEqual(calls[0]['entry_budget'],a.MAX_FILES-2)
        self.assertEqual(calls[1]['byte_budget'],a.MAX_TOTAL-sum(map(len,blobs.values())))
        self.assertEqual(calls[1]['entry_budget'],a.MAX_FILES-len(blobs)-3)

if __name__=='__main__':unittest.main()
