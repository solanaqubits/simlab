import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_experiment as e


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        (self.inputs/'numbers.json').write_bytes(b'{"a/b":{"~x":[0.1,0.2]},"depth":500,"cost":"0.00"}')
        (self.inputs/'table.csv').write_bytes(b'name,value\r\n"quoted, cell",0.30\r\nsecond,0.2\r\n')
        (self.inputs/'code.txt').write_bytes(b'raise RuntimeError("NEVER EXECUTE SOURCE")\n')
        self.sources=[dict(id=name.split('.')[0],path=name,sha256=e.m.sha((self.inputs/name).read_bytes()),role='code' if name=='code.txt' else 'data') for name in ('numbers.json','table.csv','code.txt')]
        self.spec=self.root/'spec.json';self.output=self.root/'archive'
    def plan(self):
        p=e.plan_template();p.update(readiness='ready_for_protocol_review',sources=copy.deepcopy(self.sources));return p
    def claims(self,operation='sum',value='0.3'):
        operands=[dict(source_id='numbers',selector={'json_pointer':'/a~1b/~0x/0'}),dict(source_id='numbers',selector={'json_pointer':'/a~1b/~0x/1'})]
        return dict(schema='geek-work-numeric-claims-1',id='fixture',sources=copy.deepcopy(self.sources),claims=[dict(id='claim-1',statement='Exact sum of selected fixture decimals',value=value,unit='dimensionless',uncertainty=None,operation=operation,operands=operands)])
    def capture(self,kind,spec):
        self.spec.write_bytes(e.m.encoded(spec));return e.capture(kind,self.spec,e.m.sha(self.spec.read_bytes()),self.inputs,self.output)
    def report(self):return json.loads((self.output/'report.json').read_bytes())
    def reseal(self):
        path=self.output/'manifest.json';d=json.loads(path.read_bytes());d['files']={n:e.m.sha((self.output/n).read_bytes()) for n in d['files']};path.write_bytes(e.m.encoded(d));return e.m.sha(path.read_bytes())
    def test_freeze_declares_no_execution_blinding_or_budget_enforcement(self):
        with patch.object(subprocess,'run',side_effect=AssertionError('no execution')):result=self.capture('plan',self.plan());e.verify(self.output,result['manifest_sha256'])
        r=self.report();self.assertFalse(r['experiment_executed']);self.assertFalse(r['holdout_blinding_verified']);self.assertFalse(r['chronology_verified']);self.assertFalse(r['budget_enforced']);self.assertEqual((self.output/'sources/code.txt').read_bytes(),(self.inputs/'code.txt').read_bytes())
    def test_draft_and_unpinned_code_refused(self):
        for p in (e.plan_template(),dict(self.plan(),sources=self.sources[:2])):
            with self.assertRaises(ValueError):self.capture('plan',p)
        self.assertFalse(self.output.exists())
    def test_holdout_exposure_is_declaration_not_guarantee(self):
        p=self.plan();p['sources'][0]['role']='holdout';p['holdout']=dict(source_ids=['numbers'],exposure='previously_inspected',note='Already used in selection');self.capture('plan',p);self.assertFalse(self.report()['holdout_blinding_verified'])
    def test_holdout_role_mismatch_refused(self):
        p=self.plan();p['holdout']['source_ids']=['numbers']
        with self.assertRaises(ValueError):self.capture('plan',p)
    def test_budget_bool_negative_float_and_missing_controls_refused(self):
        for key,value in [('max_attempts',True),('memory_bytes',-1),('cost_usd',0.1),('token_limit',True)]:
            p=self.plan();p['budget'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.capture('plan',p)
        p=self.plan();p['controls']=p['controls'][:2]
        with self.assertRaises(ValueError):self.capture('plan',p)
    def test_null_metrics_and_decimal_parameters_preserved(self):
        p=self.plan();p['parameters']={'tolerance':'0.00000001','measured_cost':None};self.capture('plan',p);d=json.loads((self.output/'spec.json').read_bytes());self.assertIsNone(d['budget']['cost_usd']);self.assertIsNone(d['budget']['token_limit'])
    def test_exact_decimal_recompute_avoids_binary_float_artifact(self):
        result=self.capture('claims',self.claims());self.assertEqual(self.report()['claims'][0]['actual'],{'numerator':'3','denominator':'10'});self.assertEqual(self.report()['claims'][0]['status'],'recomputed_here');self.assertFalse(self.report()['scientific_verification']);e.verify(self.output,result['manifest_sha256'])
    def test_csv_identity_and_unknown_uncertainty_are_not_verified(self):
        p=self.claims('identity');p['claims'][0]['operands']=[dict(source_id='table',selector=dict(csv_row=1,column='value'))];p['claims'][0]['uncertainty']='not measured';self.capture('claims',p);self.assertEqual(self.report()['claims'][0]['status'],'number_present');self.assertFalse(self.report()['uncertainty_verified']);self.assertFalse(self.report()['units_verified'])
    def test_mismatch_retained_without_editing_expected(self):
        result=self.capture('claims',self.claims(value='0.4'));self.assertEqual(result['status'],'numeric_map_mismatch');self.assertEqual(self.report()['claims'][0]['expected'],'0.4');self.assertFalse(self.report()['claims'][0]['matches']);self.assertEqual(e.verify(self.output,result['manifest_sha256'])['status'],'numeric_map_mismatch')
    def test_arithmetic_product_difference_ratio_and_zero(self):
        for op,expected in [('product','0.02'),('difference','-0.1'),('ratio','0.5')]:
            with self.subTest(op=op):self.capture('claims',self.claims(op,expected));self.assertTrue(self.report()['claims'][0]['matches']);shutil.rmtree(self.output)
        p=self.claims('ratio');p['claims'][0]['operands'][1]['selector']['json_pointer']='/cost'
        with self.assertRaisesRegex(ValueError,'zero denominator'):self.capture('claims',p)
    def test_duplicate_sources_claim_ids_and_bad_pointers_refused(self):
        p=self.claims();p['claims'].append(copy.deepcopy(p['claims'][0]))
        with self.assertRaises(ValueError):self.capture('claims',p)
        p=self.claims();p['sources'].append(p['sources'][0])
        with self.assertRaises(ValueError):self.capture('claims',p)
        p=self.claims();p['claims'][0]['operands'][0]['selector']['json_pointer']='/a~2b'
        with self.assertRaises(ValueError):self.capture('claims',p)
    def test_nonfinite_booleans_duplicate_keys_and_huge_exponents_refused(self):
        for blob in (b'{"x":NaN}',b'{"x":true}',b'{"x":1,"x":2}',b'{"x":1e999}'):
            with self.subTest(blob=blob),self.assertRaises(ValueError):e.value_at(blob,{'json_pointer':'/x'})
    def test_csv_ragged_duplicate_columns_and_missing_row_refused(self):
        for blob in (b'value,value\n1,2\n',b'value\n1,2\n',b'value\n'):
            with self.subTest(blob=blob),self.assertRaises(ValueError):e.value_at(blob,dict(csv_row=1,column='value'))
    def test_wrong_input_anchor_symlink_and_traversal_refused(self):
        p=self.plan();p['sources'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):self.capture('plan',p)
        p=self.plan();p['sources'][0]['path']='../numbers.json'
        with self.assertRaises(ValueError):self.capture('plan',p)
        (self.inputs/'numbers.json').unlink();(self.inputs/'numbers.json').symlink_to(self.inputs/'code.txt')
        with self.assertRaises(ValueError):self.capture('plan',self.plan())
    def test_output_cannot_replace_sources_or_be_reused(self):
        self.output=self.inputs/'nested'
        with self.assertRaises(ValueError):self.capture('plan',self.plan())
        self.output=self.root/'archive';self.capture('plan',self.plan())
        with self.assertRaises(ValueError):self.capture('plan',self.plan())
    def test_resealed_scientific_promotion_and_extra_file_refused(self):
        self.capture('claims',self.claims());p=self.output/'report.json';d=self.report();d['scientific_verification']=True;p.write_bytes(e.m.encoded(d))
        with self.assertRaises(ValueError):e.verify(self.output,self.reseal())
    def test_relocation_needs_no_original_input_or_external_program(self):
        result=self.capture('claims',self.claims());moved=self.root/'moved';shutil.move(self.output,moved);shutil.rmtree(self.inputs);self.spec.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):self.assertTrue(e.verify(moved,result['manifest_sha256'])['integrity_reproduced'])
    def test_cli_reports_integrity_not_acceptance(self):
        result=self.capture('plan',self.plan());p=subprocess.run([sys.executable,e.__file__,'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True);self.assertEqual(p.returncode,2,p.stderr)

if __name__=='__main__':unittest.main()
