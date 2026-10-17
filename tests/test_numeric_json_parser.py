"""Kernel regressions for the exact byte decoder."""
import os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('LEAN_VERIFIER_LIVE_TESTS')=='1','Set LEAN_VERIFIER_LIVE_TESTS=1')
class JSONParserLiveTests(unittest.TestCase):
    def test_json_parser_kernel(self):
        p=subprocess.run(['lake','env','lean','-DwarningAsError=true','tests/lean/numeric_sql_json_parser_regression.lean'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
