import copy
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_exact_pilot as p


class ExactPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=self.root/'plan';self.out=self.root/'run'
        self.anchor=p.freeze(self.plan)['manifest_sha256']
    def candidates(self):return p.generator.candidates(copy.deepcopy(p.TRAINING['samples']))
    def run_pilot(self):return p.run(self.plan,self.anchor,self.out)
    def reseal(self):
        files={str(x.relative_to(self.out)):x.read_bytes() for x in self.out.rglob('*') if x.is_file() and x!=self.out/'manifest.json'}
        raw=p.manifest(files);(self.out/'manifest.json').write_bytes(raw);return p.m.sha(raw)
    def test_interpolation_coefficients_match_known_formula(self):
        rows=self.candidates();self.assertEqual(rows[-1]['coefficients'],['0','1/6','1/2','1/3'])
    def test_control_patterns_and_training_false_acceptance(self):
        report=p.check(self.candidates());self.assertTrue(report['control_suite_passed'])
        self.assertEqual(report['training_only_false_acceptance_ids'],['training-only'])
        self.assertEqual(report['point_evaluations'],32)
        for key in ('holdout_blinding_verified','independence_verified','universal_identity_proved','scientific_verification','model_called_here'):
            self.assertIs(report[key],False)
    def test_direct_oracle_expected_values_not_from_candidate(self):
        report=p.check(self.candidates());points=report['rows'][-1]['assessment']['points']
        self.assertEqual([x['expected'] for x in points],['30','55','140','506'])
        self.assertTrue(all(x['matches'] for x in points))
    def test_overfit_concrete_counterexample(self):
        r=p.check(self.candidates())['rows'][2]
        self.assertTrue(r['training']['matches']);q=r['assessment']['points'][0]
        self.assertEqual((q['n'],q['expected'],q['actual']),(4,'30','54'))
    def test_generation_receives_training_only(self):
        original=p.generator.candidates;calls=[]
        def spy(samples):calls.append(copy.deepcopy(samples));return original(samples)
        with patch.object(p.generator,'candidates',side_effect=spy):self.run_pilot()
        self.assertEqual(calls,[p.TRAINING['samples']])
    def test_replay_never_calls_generator(self):
        r=self.run_pilot()
        with patch.object(p.generator,'candidates',side_effect=AssertionError('no generation')):
            out=p.verify(self.out,r['manifest_sha256'])
        self.assertFalse(out['generator_rerun'])
    def test_positive_mutation_is_failure_not_invalid(self):
        rows=self.candidates();rows[-1]['coefficients'][0]='1'
        report=p.check(rows);self.assertFalse(report['control_suite_passed']);self.assertEqual(report['status'],'control_pattern_mismatch')
    def test_invalid_candidate_shapes(self):
        rows=self.candidates()
        for bad in [rows[:3],rows+[rows[0]],list(reversed(rows)),[{**rows[0],'status':'accepted'},*rows[1:]],['x',*rows[1:]]]:
            with self.assertRaises(ValueError):p.check(bad)
    def test_rational_bounds_and_canonical_form(self):
        for bad in [True,1,'1.0','1/0','2/2','-0','1/1','01','1e99',str(2**128),'9'*90]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):p.rational(bad)
        self.assertEqual(p.rational('-1/6'),Fraction(-1,6))
    def test_degree_and_empty_coefficient_limits(self):
        for coefficients in [[],['0']*10]:
            rows=self.candidates();rows[0]['coefficients']=coefficients
            with self.assertRaises(ValueError):p.check(rows)
    def test_passport_replay_and_current_code_pins(self):
        parent=p.plan_bytes(self.plan,self.anchor);spec=json.loads(parent['spec.json'])
        self.assertEqual(spec['holdout']['exposure'],'previously_inspected');self.assertEqual(spec['budget']['max_attempts'],4)
        with patch.object(p,'implementation',return_value={'checker.py':b'changed','generator.py':b'changed'}),self.assertRaises(ValueError):p.plan_bytes(self.plan,self.anchor)
    def test_ledger_accounts_all_controls_with_unknown_cost(self):
        self.run_pilot();doc=json.loads((self.out/'ledger.json').read_bytes());p.ledger.validate(doc)
        self.assertEqual(doc['tasks'][0]['attempts_count'],4)
        summary=json.loads((self.out/'cost-summary.json').read_bytes())['by_currency']['USD']
        self.assertEqual(summary['attempts'],4);self.assertEqual(summary['accepted_results'],1)
        self.assertIsNone(summary['cost_per_accepted_result']);self.assertEqual(summary['unknown_verification_time_attempts'],4)
    def test_report_and_candidate_tampering_rejected(self):
        for name in ['report.json','candidates.json','ledger.json','cost-summary.json']:
            self.run_pilot();f=self.out/name;f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ValueError):p.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
    def test_changed_well_formed_candidates_preserve_failure_on_replay(self):
        parent=p.plan_bytes(self.plan,self.anchor);rows=self.candidates();rows[-1]['coefficients'][0]='1'
        files,report=p.artifacts(parent,rows);meta=p.manifest(files);p.archive.write_tree(self.out,{**files,'manifest.json':meta})
        self.assertFalse(p.verify(self.out,p.m.sha(meta))['control_suite_passed'])
    def test_extra_file_and_wrong_anchor(self):
        r=self.run_pilot()
        with self.assertRaises(ValueError):p.verify(self.out,'0'*64)
        (self.out/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):p.verify(self.out,self.reseal())
    def test_relocation_without_plan_and_without_subprocess(self):
        r=self.run_pilot();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.plan)
        with patch.object(subprocess,'run',side_effect=AssertionError('no subprocess')):p.verify(moved,r['manifest_sha256'])
    def test_symlink_and_existing_output(self):
        r=self.run_pilot()
        with self.assertRaises(FileExistsError):self.run_pilot()
        raw=(self.out/'candidates.json').read_bytes();source=self.root/'candidates';source.write_bytes(raw)
        (self.out/'candidates.json').unlink();(self.out/'candidates.json').symlink_to(source)
        with self.assertRaises(ValueError):p.verify(self.out,r['manifest_sha256'])
    def test_cli_run_verify_and_exit_codes(self):
        def cli(*args):return subprocess.run([sys.executable,'-B',p.__file__,*map(str,args)],capture_output=True,text=True)
        r=cli('run','--bundle',self.plan,'--sha256',self.anchor,'--output',self.out);self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        anchor=json.loads(r.stdout)['manifest_sha256']
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(cli('verify','--bundle',self.out,'--sha256','0'*64).returncode,2)
        rows=self.candidates();rows[-1]['coefficients'][0]='1';parent=p.plan_bytes(self.plan,self.anchor);files,_=p.artifacts(parent,rows);meta=p.manifest(files)
        failed=self.root/'failed';p.archive.write_tree(failed,{**files,'manifest.json':meta})
        self.assertEqual(cli('verify','--bundle',failed,'--sha256',p.m.sha(meta)).returncode,3)


if __name__=='__main__':unittest.main()
