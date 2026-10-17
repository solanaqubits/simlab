"""Kernel regression for caller-selected SQL instances, no native_decide."""
import os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('LEAN_VERIFIER_LIVE_TESTS')=='1','Set LEAN_VERIFIER_LIVE_TESTS=1')
class ExpectedInstanceLiveTests(unittest.TestCase):
    def test_instance_binding(self):
        p=subprocess.run(['lake','env','lean','-DwarningAsError=true','tests/lean/numeric_sql_expected_instance_regression.lean'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
