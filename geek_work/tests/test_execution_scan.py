from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_exact_runner as r


class ExecutionScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def stream(self,kind):
        seen=[]
        class Entry:
            def __init__(self,i):self.name=f'entry{i:04d}'
            def is_symlink(self):return False
            def is_dir(self,follow_symlinks=False):return kind=='directory'
            def is_file(self,follow_symlinks=False):return kind=='file'
        def endless():
            for i in range(10000):seen.append(i);yield Entry(i)
        @contextmanager
        def scan(path):yield endless()
        return scan,seen
    def test_directory_overflow_stops_enumeration_before_sort_or_read(self):
        scan,seen=self.stream('directory')
        with patch.object(r,'MAX_FILES',3),patch.object(r.os,'scandir',scan),patch.object(r.m,'read',side_effect=AssertionError('payload read')):
            with self.assertRaisesRegex(ValueError,'directory count'):r.inventory(self.root)
        self.assertEqual(len(seen),4)
    def test_file_overflow_stops_before_payload_read(self):
        scan,seen=self.stream('file')
        with patch.object(r,'MAX_FILES',3),patch.object(r.os,'scandir',scan),patch.object(r.m,'read',side_effect=AssertionError('payload read')):
            with self.assertRaisesRegex(ValueError,'file count'):r.inventory(self.root)
        self.assertEqual(len(seen),4)
    def test_directory_inspection_also_bounds_file_count(self):
        scan,seen=self.stream('file')
        with patch.object(r,'MAX_FILES',3),patch.object(r.os,'scandir',scan):
            with self.assertRaises(ValueError):r.directories(self.root)
        self.assertEqual(len(seen),4)
    def test_limits_global_across_subdirectories(self):
        for d in ('a','b'):
            (self.root/d).mkdir()
            for n in ('x','y'):(self.root/d/n).write_bytes(b'x')
        with patch.object(r,'MAX_FILES',3),self.assertRaisesRegex(ValueError,'file count'):r.inventory(self.root)
    def test_root_manifest_exemption_and_sorted_output(self):
        for n in ('z','a','manifest.json'):(self.root/n).write_bytes(n.encode())
        with patch.object(r,'MAX_FILES',2):
            files=r.inventory(self.root);self.assertEqual(list(files),['a','z'])
        (self.root/'child').mkdir();(self.root/'child/manifest.json').write_bytes(b'{}')
        with patch.object(r,'MAX_FILES',2),self.assertRaises(ValueError):r.inventory(self.root)
    def test_empty_directories_included_sorted(self):
        for n in ('z','a'):(self.root/n).mkdir()
        self.assertEqual(r.directories(self.root),['a','z']);self.assertEqual(r.inventory(self.root),{})
    def test_remaining_byte_budget_limits_each_read(self):
        (self.root/'a').write_bytes(b'1234');(self.root/'b').write_bytes(b'5678');original=r.m.read;limits=[]
        def read(p,limit):limits.append(limit);return original(p,limit)
        with patch.object(r,'MAX_TOTAL',5),patch.object(r.m,'read',side_effect=read),self.assertRaises(ValueError):r.inventory(self.root)
        self.assertEqual(limits,[5,1])
    def test_fifo_and_symlinks_refused_without_reading(self):
        fifo=self.root/'pipe';os.mkfifo(fifo)
        with patch.object(r.m,'read',side_effect=AssertionError('must not read special file')),self.assertRaises(ValueError):r.inventory(self.root)
        fifo.unlink();(self.root/'link').symlink_to(self.tmp.name,target_is_directory=True)
        with self.assertRaises(ValueError):r.directories(self.root)
    def test_invalid_root_and_unsafe_names(self):
        with self.assertRaises(ValueError):r.inventory(self.root/'absent')
        (self.root/'.hidden').mkdir()
        with self.assertRaises(ValueError):r.directories(self.root)
    def test_native_archive_identity_and_replay_preserved(self):
        plan=self.root/'plan';h=r.pilot.freeze(plan)['manifest_sha256'];out=self.root/'execution';result=r.run(plan,h,out)
        raw=(out/'manifest.json').read_bytes();spec=r.knowledge.strict_json(raw)
        # Independently construct the old canonical listing on this small valid archive.
        old={p.relative_to(out).as_posix():p.read_bytes() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'manifest.json'}
        self.assertEqual(r.inventory(out),old)
        self.assertEqual(spec['files'],{n:r.m.sha(b) for n,b in old.items()})
        self.assertEqual(r.verify(out,result['manifest_sha256'])['status'],'controls_observed')

if __name__=='__main__':unittest.main()
