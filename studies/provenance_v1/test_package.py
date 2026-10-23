import copy,json,unittest
from pathlib import Path
from check import validate
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parent
        self.m=json.loads((self.root/'manifest.json').read_text())
    def test_current_package(self):self.assertTrue(validate(self.m,self.root)['package_ok'])
    def test_false_acceptance_refused(self):
        for k,v in [('authorization','allowed'),('native_target_acceptance','PASSED'),('external_witness','CONNECTED'),('independent_audit','PASSED'),('public_full_beta',True)]:
            with self.subTest(k=k):
                m=copy.deepcopy(self.m);m[k]=v
                with self.assertRaises(AssertionError):validate(m,self.root)
    def test_commit_url_mismatch_refused(self):
        self.m['leanbook_commit']='0'*40
        with self.assertRaises(AssertionError):validate(self.m,self.root)
    def test_changed_setup_refused(self):
        self.m['setup_sha256']='0'*64
        with self.assertRaises(AssertionError):validate(self.m,self.root)
