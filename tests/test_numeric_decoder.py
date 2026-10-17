"""Live kernel tests for the AST decoder, never native_decide."""
import os,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(os.environ.get('LEAN_VERIFIER_LIVE_TESTS')=='1','Set LEAN_VERIFIER_LIVE_TESTS=1')
class DecoderLiveTests(unittest.TestCase):
    def test_decoder_kernel(self):
        p=subprocess.run(['lake','env','lean','-DwarningAsError=true','tests/lean/numeric_sql_decoder_regression.lean'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
