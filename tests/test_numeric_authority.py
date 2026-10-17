import unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class AuthorityKernel(unittest.TestCase):
 def test_authority_kernel(self):
  r=subprocess.run(['lake','env','lean','-DwarningAsError=true','tests/lean/numeric_sql_authority_regression.lean'],cwd=ROOT,capture_output=True,text=True,timeout=120)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
