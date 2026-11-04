import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('released_check',Path(__file__).resolve().parents[1]/'check.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'VERSION').write_text('1.0.0\n');(self.root/'tool.py').write_text('# fixture\n')
        self.seal()
    def seal(self):
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.is_file() and p.name!='MANIFEST.json'}
        (self.root/'MANIFEST.json').write_text(json.dumps(dict(schema='geek-work-public-files-2',version='1.0.0',files=files)))
    def test_valid(self):self.assertEqual(c.verify(self.root),2)
    def test_modified_source(self):
        (self.root/'tool.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'digest'):c.verify(self.root)
    def test_extra_file(self):
        (self.root/'private.txt').write_text('unselected')
        with self.assertRaisesRegex(ValueError,'file set'):c.verify(self.root)
    def test_missing_file(self):
        (self.root/'tool.py').unlink()
        with self.assertRaisesRegex(ValueError,'file set'):c.verify(self.root)
    def test_wrong_version(self):
        (self.root/'VERSION').write_text('1.0.1')
        with self.assertRaisesRegex(ValueError,'version'):c.verify(self.root)
    def test_symlink_directory(self):
        (self.root/'alias').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):c.verify(self.root)
