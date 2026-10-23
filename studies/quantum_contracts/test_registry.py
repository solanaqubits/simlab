"""Mutation controls for the publication's boundaries and pinned evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import check

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in check.FILES | {'MANIFEST.json'}:
            shutil.copyfile(Path(__file__).parent / name, self.root / name)

    def mutate(self, callback):
        path = self.root / 'registry.json'
        data = json.loads(path.read_text())
        callback(data)
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            check.validate(self.root, check_manifest=False)

    def test_valid_package(self):
        self.assertEqual(check.validate(self.root)['modules'], 12)
    def test_wrong_source_hash(self):
        self.mutate(lambda r: r['modules'][0].update(source_sha256='0' * 64))
    def test_mixed_commit(self):
        self.mutate(lambda r: r.update(lean_commit='0' * 40))
    def test_missing_limitation(self):
        self.mutate(lambda r: r['modules'][0].update(limitations=''))
    def test_duplicate_module(self):
        self.mutate(lambda r: r['modules'].__setitem__(1, r['modules'][0]))
    def test_obligation_closed(self):
        self.mutate(lambda r: r.update(third_obligation='CLOSED'))
    def test_private_repository(self):
        self.mutate(lambda r: r.update(lean_repository='example/unapproved-repository'))
    def test_invented_audit(self):
        self.mutate(lambda r: r.update(independent_stack_audit='passed'))
    def test_local_evidence_mislabel(self):
        self.mutate(lambda r: r.update(formal_evidence='checked_here'))
    def test_extra_file(self):
        (self.root / 'private.log').write_text('not allowed')
        with self.assertRaises(ValueError):
            check.validate(self.root)
    def test_changed_package_bytes(self):
        (self.root / 'LIMITS.md').write_text('changed')
        with self.assertRaises(ValueError):
            check.validate(self.root)
    def test_checks_hash(self):
        self.mutate(lambda r: r.update(checks_sha256='0' * 64))

if __name__ == '__main__':
    unittest.main()
