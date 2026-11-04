import importlib.util
import json
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'evaluation/alcc-native-timing/recorded_driver.py'
spec=importlib.util.spec_from_file_location('alcc_timing_driver',path)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class NativeTimingTests(unittest.TestCase):
    def row(self):return dict(schema='alcc-native-timing-1',evidence_kind='compiled_execution',code=0,read_ns=10,verify_ns=20)
    def test_three_expected_decisions(self):
        for code in (0,2,3):
            row=self.row();row['code']=code
            self.assertEqual(a.validate(json.dumps(row).encode(),code,code,30),row)
    def test_verdict_exit_mismatch(self):
        with self.assertRaises(ValueError):a.validate(json.dumps(self.row()).encode(),2,0,30)
    def test_time_and_code_types(self):
        for field,value in [('code',False),('read_ns',True),('verify_ns',-1),('read_ns',1.5),('verify_ns','20')]:
            row=self.row();row[field]=value
            with self.assertRaises(ValueError):a.validate(json.dumps(row).encode(),0,0,30)
    def test_interval_bound(self):
        with self.assertRaises(ValueError):a.validate(json.dumps(self.row()).encode(),0,0,29)
    def test_protocol_and_extra_field(self):
        for key,value in [('schema','wrong'),('evidence_kind','kernel_proof'),('extra',0)]:
            row=self.row();row[key]=value
            with self.assertRaises(ValueError):a.validate(json.dumps(row).encode(),0,0,30)
    def test_duplicate_json(self):
        raw=json.dumps(self.row()).replace('"code": 0','"code": 0, "code": 0').encode()
        with self.assertRaises(ValueError):a.validate(raw,0,0,30)

if __name__=='__main__':unittest.main()
