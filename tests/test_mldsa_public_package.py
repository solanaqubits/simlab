"""Public frozen source replay and rejection of corrupted package inputs."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'studies/mldsa44_arithmetic'
spec = importlib.util.spec_from_file_location('mldsa_public_check', ROOT / 'check_package.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class MlDsaPublicPackageTests(unittest.TestCase):
    def test_selected_source_replay(self):
        result = checker.check(ROOT)
        self.assertTrue(result['ok'])
        self.assertEqual(result['source_paths_replayed'], 12)
        self.assertFalse(result['fresh_benchmark'])
        self.assertFalse(result['full_upstream_checkout'])

    def corrupt(self, name, expected):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'package'
            shutil.copytree(ROOT, root)
            with (root / name).open('ab') as f:
                f.write(b'\n')
            with self.assertRaisesRegex(ValueError, expected):
                checker.check(root)

    def test_modified_patch_rejected(self):
        self.corrupt('candidate.patch', 'Wrong selected Stage 11 patch')

    def test_modified_candidate_rejected(self):
        self.corrupt('candidate/crates/ml_dsa_44/src/k2.cairo', 'Changed package file')

    def test_modified_baseline_rejected(self):
        self.corrupt('baseline/crates/ml_dsa_44/src/lib.cairo', 'Changed package file')

    def test_unexpected_production_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'package'
            shutil.copytree(ROOT, root)
            p = root / 'manifest.json'
            manifest = json.loads(p.read_text())
            manifest['paths']['../outside.cairo'] = manifest['paths'].pop(checker.PREFIX + 'k2.cairo')
            p.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unexpected production paths'):
                checker.check(root)
