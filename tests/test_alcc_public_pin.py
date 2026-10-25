"""Public source pin is content-based, not dependent on private Git objects."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.alcc_compiled_pin import MODULES, KERNEL_BASE, file_hash, validate_kernel_sources


class PublicPinTests(unittest.TestCase):
    def test_content_pin_and_mutations_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [f'Verification/AlgebraicCertificate{x}.lean' for x in MODULES] + ['lean-toolchain', 'lake-manifest.json']
            for name in paths:
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('synthetic '+name)
            manifest = dict(schema_version=1,kernel_base_commit=KERNEL_BASE,sources={n:file_hash(root/n) for n in paths})
            pin = root/'manifest.json'; pin.write_text(json.dumps(manifest))
            self.assertEqual(validate_kernel_sources(root,pin),manifest['sources'])
            for name in paths:
                p=root/name; original=p.read_bytes();p.write_bytes(original+b'changed')
                with self.assertRaises(ValueError):validate_kernel_sources(root,pin)
                p.write_bytes(original)

    def test_schema_and_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'manifest.json'
            for obj in [dict(schema_version=1,kernel_base_commit=KERNEL_BASE,sources={}),
                        dict(schema_version=True,kernel_base_commit=KERNEL_BASE,sources={}),
                        dict(schema_version=1,kernel_base_commit='0'*40,sources={'../bad':'x'})]:
                p.write_text(json.dumps(obj))
                with self.assertRaises(ValueError):validate_kernel_sources(root,p)
