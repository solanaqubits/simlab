import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_alcc_byte_preflight as b


class AlccBytePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'run'

    def rows(self):
        cases,_=b.corpus()
        return [dict(case=c['id'],round=r,result=c['expected'],
                     result_sha256=b.m.sha(b.alcc.canonical(c['expected'])),
                     bind_ns=10,residual_ns=None if c['expected']['residual'] is None else 20,
                     serialize_ns=5,total_ns=50) for r,c in b.order(cases)]

    def encode(self,rows):return b'\n'.join(b.alcc.canonical(r) for r in rows)+b'\n'

    def test_fixed_corpus_exact_oracle_and_refusals(self):
        cases,files=b.corpus();self.assertEqual(len(cases),12)
        for c in cases:
            result=b.evaluate(files[c['id']+'.passport.json'],files[c['id']+'.certificate.json'])
            self.assertEqual(result['result'],c['expected'],c['id'])
        byid={c['id']:c for c in cases}
        self.assertEqual(byid['chain-invalid']['expected']['residual'],[[[0,0,1],'1','1']])
        self.assertEqual(byid['constant-mismatch']['expected']['residual'],[[[0,0,0],'1','1']])

    def test_summary_rounds_nulls_and_exact_median(self):
        report=b.validate_rows(self.encode(self.rows()))
        self.assertEqual(report['observations'],60);self.assertEqual(report['measured_observations'],48)
        self.assertEqual(report['cases'][0]['median_ns']['bind_ns'],dict(numerator=20,denominator=2))
        self.assertIsNone(report['cases'][-1]['median_ns']['residual_ns'])
        self.assertFalse(report['lean_verified']);self.assertIsNone(report['monetary_cost'])

    def test_missing_order_and_duplicate_key(self):
        rows=self.rows()
        with self.assertRaises(ValueError):b.validate_rows(self.encode(rows[:-1]))
        rows[0],rows[1]=rows[1],rows[0]
        with self.assertRaises(ValueError):b.validate_rows(self.encode(rows))
        raw=self.encode(self.rows()).replace(b'"round":0',b'"round":0,"round":0',1)
        with self.assertRaises(ValueError):b.validate_rows(raw)

    def test_full_residual_not_only_status(self):
        rows=self.rows();rows[1]['result']=dict(status='residual_nonzero',residual=[[[0,0,0],'2','1']])
        with self.assertRaises(ValueError):b.validate_rows(self.encode(rows))

    def test_invalid_times_types_and_serialized_hash(self):
        for field,value in [('bind_ns',True),('residual_ns',None),('round',False),
                            ('total_ns',1),('serialize_ns',-1),('result_sha256','0'*64)]:
            rows=self.rows();rows[0][field]=value
            with self.assertRaises(ValueError,msg=field):b.validate_rows(self.encode(rows))

    def test_rejection_has_no_residual_time(self):
        rows=self.rows();rows[9]['residual_ns']=0
        with self.assertRaises(ValueError):b.validate_rows(self.encode(rows))

    def test_real_bounded_worker_and_relocation_without_child(self):
        result=b.run(self.out);self.assertEqual(result['status'],'EXPECTED_PREFLIGHT_CONTROLS')
        moved=self.root/'moved';shutil.move(self.out,moved)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('no child')):
            self.assertTrue(b.verify(moved,result['manifest_sha256'])['integrity_reproduced'])
        self.assertFalse(json.loads((moved/'report.json').read_bytes())['full_cli_throughput_measured'])

    def test_operational_failure_preserved_and_replayed(self):
        process=dict(outcome='timed_out',returncode=-9,wall_time_ms=30000,error=None,
                     stdout_truncated=False,stderr_truncated=False)
        with patch.object(b.supervisor,'supervise',return_value=(process,{'stdout.bin':b'partial','stderr.bin':b''})):
            result=b.run(self.out)
        self.assertEqual(result['status'],'operational_failure')
        self.assertEqual(b.verify(self.out,result['manifest_sha256'])['status'],'operational_failure')
        self.assertEqual((self.out/'stdout.bin').read_bytes(),b'partial')

    def test_zero_exit_without_rows_is_not_success(self):
        process=dict(outcome='exited',returncode=0,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False)
        self.assertEqual(b.derive(process,{'stdout.bin':b'','stderr.bin':b''})['status'],'invalid_observations')

    def test_control_disagreement_not_operational_failure(self):
        process=dict(outcome='exited',returncode=3,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False)
        self.assertEqual(b.derive(process,{'stdout.bin':b'partial','stderr.bin':b''})['status'],'unexpected_control')

    def test_existing_output_no_launch_and_incomplete(self):
        self.out.mkdir()
        with patch.object(b.supervisor,'supervise',side_effect=AssertionError('no launch')):
            with self.assertRaises(FileExistsError):b.run(self.out)
        with self.assertRaises((ValueError,OSError)):b.verify(self.out,'0'*64)

    def test_runtime_and_inputs_cannot_be_substituted(self):
        req=b.request();_,files=b.corpus();req['bindings']['alcc.py']='0'*64
        with self.assertRaises(ValueError):b.check_request(req,files)
        req=b.request();files['identity-x.passport.json']=files['empty.passport.json']
        with self.assertRaises(ValueError):b.check_request(req,files)

    def test_resealed_report_promotion_is_rejected(self):
        process=dict(outcome='exited',returncode=0,wall_time_ms=1,error=None,stdout_truncated=False,stderr_truncated=False)
        with patch.object(b.supervisor,'supervise',return_value=(process,{'stdout.bin':self.encode(self.rows()),'stderr.bin':b''})):
            b.run(self.out)
        report=json.loads((self.out/'report.json').read_bytes());report['lean_verified']=True
        (self.out/'report.json').write_bytes(b.m.encoded(report))
        meta=json.loads((self.out/'manifest.json').read_bytes())
        meta['files']['report.json']=b.m.sha((self.out/'report.json').read_bytes())
        raw=b.m.encoded(meta);(self.out/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):b.verify(self.out,b.m.sha(raw))

    def test_cli_rejects_supplied_command(self):
        r=subprocess.run([sys.executable,'-B',b.__file__,'run','--command','echo unsafe'],capture_output=True)
        self.assertEqual(r.returncode,2)

    def test_manifest_tamper_and_symlink(self):
        process=dict(outcome='launch_failed',returncode=None,wall_time_ms=1,error='fixture',stdout_truncated=False,stderr_truncated=False)
        with patch.object(b.supervisor,'supervise',return_value=(process,{'stdout.bin':b'','stderr.bin':b''})):
            result=b.run(self.out)
        with self.assertRaises(ValueError):b.verify(self.out,'0'*64)
        target=self.out/'report.json';original=target.read_bytes();target.write_bytes(b'{}')
        with self.assertRaises(ValueError):b.verify(self.out,result['manifest_sha256'])
        target.unlink();(self.root/'external').write_bytes(original);target.symlink_to(self.root/'external')
        with self.assertRaises(ValueError):b.verify(self.out,result['manifest_sha256'])


if __name__=='__main__':unittest.main()
