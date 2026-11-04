import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import geek_work_proposer as p
sys.path.pop(0)


class Engine:
    def __init__(self, output):
        self.output = output; self.issue = None; self.cleanup = True; self.inputs = []

    def preflight(self, plan): return {'fixture': True}

    def execute(self, plan, snapshot, request, wall_ms):
        self.inputs.append(copy.deepcopy(request))
        return (dict(stdout=self.output, stderr=b'', exit_code=0, issue=self.issue, wall_time_ms=1),
                dict(config_checked=True, cleanup_confirmed=self.cleanup,
                     stopped_before_removal=True, oom_killed=False))


class ProposerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.baseline = b'import json,sys\nprint(json.dumps(sum(json.load(sys.stdin))))\n'
        self.proposer = b'# Fixture proposer bytes, never executed by fake engine.\n'
        self.corpus = dict(schema='geek-work-tool-corpus-1', cases=[dict(id='secret-case', input=[2, 3], expected=5)])
        self.plan = p.plan(self.corpus, self.baseline, self.proposer, 'Preserve JSON sum behavior.',
                           'sha256:' + 'a' * 64, repetitions=1)
        self.doc = dict(schema='geek-work-proposal-1', baseline_sha256=p.ev.digest(self.baseline),
                        files=[dict(path='candidate.py', content=self.baseline.decode())])
        self.engine = Engine(p.ev.encoded(self.doc))

    def sha(self): return p.ev.digest(p.ev.encoded(self.plan))

    def propose(self, name='proposal'):
        return p.propose(self.plan, self.baseline, self.proposer, self.sha(), self.root / name, self.engine)

    def verify(self): return p.verify_proposal(self.root / 'proposal', self.sha())

    def reseal(self, root=None):
        root = root or self.root / 'proposal'; (root / 'seal.json').unlink(); p.seal(root)

    def test_public_request_withholds_private_plan_and_gold(self):
        self.assertEqual(self.propose()['status'], 'PROPOSAL_READY')
        public = self.engine.inputs[0]
        self.assertEqual(set(public), {'schema', 'task', 'baseline', 'output_contract'})
        self.assertNotIn('secret-case', json.dumps(public))
        self.assertNotIn('expected', json.dumps(public)); self.assertNotIn('evaluation', public)
        self.assertEqual(self.verify()['execution_kind'], 'fixture')

    def test_ready_is_only_protocol_acceptance(self):
        r = self.propose(); cost = p.g.parse((self.root / 'proposal/ledger.json').read_bytes())
        self.assertEqual(cost['result_unit'], 'proposal_protocol_only')
        self.assertIsNone(cost['tasks'][0]['attempts'][0]['monetary_cost'])
        self.assertIsNone(r['model_invocations_inside_proposer'])
        self.assertFalse((self.root / 'proposal/report.json').exists())

    def test_path_traversal_absolute_nested_and_case_variants_rejected(self):
        for i, path in enumerate(['../outside', '/tmp/outside', 'x/candidate.py', './candidate.py', 'Candidate.py']):
            d = copy.deepcopy(self.doc); d['files'][0]['path'] = path; self.engine.output = p.ev.encoded(d)
            r = self.propose(str(i)); self.assertEqual(r['status'], 'INVALID_PROPOSAL')
            self.assertFalse((self.root / str(i) / 'candidate.py').exists())
        self.assertFalse((self.root / 'outside').exists())

    def test_link_mode_or_extra_metadata_rejected(self):
        for i, key in enumerate(['symlink', 'target', 'mode', 'permissions']):
            d = copy.deepcopy(self.doc); d['files'][0][key] = '/host/grader'; self.engine.output = p.ev.encoded(d)
            self.assertEqual(self.propose(str(i))['status'], 'INVALID_PROPOSAL')

    def test_extra_file_and_deleting_baseline_rejected(self):
        for i, files in enumerate([[], self.doc['files'] * 2]):
            d = copy.deepcopy(self.doc); d['files'] = files; self.engine.output = p.ev.encoded(d)
            self.assertEqual(self.propose(str(i))['status'], 'INVALID_PROPOSAL')

    def test_stale_baseline_and_evaluation_override_rejected(self):
        d = copy.deepcopy(self.doc); d['baseline_sha256'] = 'b' * 64; self.engine.output = p.ev.encoded(d)
        self.assertEqual(self.propose('stale')['status'], 'INVALID_PROPOSAL')
        d = copy.deepcopy(self.doc); d['evaluation'] = {'criterion': 'always_pass'}; self.engine.output = p.ev.encoded(d)
        self.assertEqual(self.propose('override')['status'], 'INVALID_PROPOSAL')

    def test_empty_nul_oversized_and_nontext_source_rejected(self):
        for i, content in enumerate(['', '\x00', 'x' * (p.MAX_SOURCE + 1), 4]):
            d = copy.deepcopy(self.doc); d['files'][0]['content'] = content; self.engine.output = p.ev.encoded(d)
            self.assertEqual(self.propose(str(i))['status'], 'INVALID_PROPOSAL')

    def test_duplicate_keys_and_invalid_json_rejected(self):
        for i, output in enumerate([b'{"files":[],"files":[]}', b'not JSON', b'\xff']):
            self.engine.output = output
            self.assertEqual(self.propose(str(i))['status'], 'INVALID_OUTPUT')

    def test_timeout_cannot_publish_valid_partial_proposal(self):
        self.engine.issue = 'EXEC_TIMEOUT'
        self.assertEqual(self.propose()['status'], 'EXEC_TIMEOUT')
        self.assertFalse((self.root / 'proposal/candidate.py').exists())
        self.assertEqual(self.verify()['status'], 'EXEC_TIMEOUT')

    def test_cleanup_unconfirmed_cannot_publish(self):
        self.engine.cleanup = False
        self.assertEqual(self.propose()['status'], 'CLEANUP_UNCONFIRMED')
        with self.assertRaisesRegex(ValueError, 'proposal_not_ready'):
            p.evaluate(self.root / 'proposal', self.sha(), self.root / 'evaluation', Engine(b'5'))
        self.assertFalse((self.root / 'evaluation').exists())

    def test_plan_gold_drift_refused_before_launch(self):
        old = self.sha(); self.plan['evaluation']['corpus']['cases'][0]['expected'] = 999
        with self.assertRaisesRegex(ValueError, 'expected_plan_mismatch'):
            p.propose(self.plan, self.baseline, self.proposer, old, self.root / 'proposal', self.engine)
        self.assertFalse(self.engine.inputs)

    def test_baseline_proposer_or_tools_drift_refused(self):
        original = copy.deepcopy(self.plan)
        for field in ['baseline', 'proposer', 'tools']:
            self.plan = copy.deepcopy(original)
            baseline, proposer = self.baseline, self.proposer
            if field == 'baseline': baseline += b'# drift'
            elif field == 'proposer': proposer += b'# drift'
            else: self.plan['tools']['geek_work_proposer.py'] = 'b' * 64
            with self.assertRaisesRegex(ValueError, 'proposal_plan_drift'):
                p.propose(self.plan, baseline, proposer, self.sha(), self.root / field, self.engine)
        self.assertFalse(self.engine.inputs)

    def test_no_overwrite_and_no_unsealed_replay(self):
        self.propose()
        with self.assertRaises(FileExistsError): self.propose()
        (self.root / 'proposal/seal.json').unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_changed_candidate_even_after_reseal_rejected(self):
        self.propose(); (self.root / 'proposal/candidate.py').chmod(0o600)
        (self.root / 'proposal/candidate.py').write_bytes(b'print(999)')
        self.reseal()
        with self.assertRaisesRegex(ValueError, 'candidate_changed'): self.verify()

    def test_resealed_false_verdict_rejected(self):
        self.engine.issue = 'EXEC_TIMEOUT'; self.propose()
        path = self.root / 'proposal/receipt.json'; r = p.g.parse(path.read_bytes()); r['status'] = 'PROPOSAL_READY'
        path.write_bytes(p.ev.encoded(r)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'verdict_changed'): self.verify()

    def test_extra_file_and_symlink_bundle_rejected(self):
        self.propose(); (self.root / 'proposal/extra').write_bytes(b'x'); self.reseal()
        with self.assertRaisesRegex(ValueError, 'artifact_set'): self.verify()
        (self.root / 'proposal/extra').unlink(); (self.root / 'proposal/extra').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlink'): self.verify()

    def test_ledger_change_cannot_fabricate_zero_cost(self):
        self.propose(); path = self.root / 'proposal/ledger.json'; d = p.g.parse(path.read_bytes())
        d['tasks'][0]['attempts'][0]['monetary_cost'] = '0'; path.write_bytes(p.ev.encoded(d)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'ledger_changed'): self.verify()

    def test_lifecycle_budget_blocks_ready(self):
        with mock.patch.object(p.time, 'monotonic_ns', side_effect=[0, 0, 999999999999]): r = self.propose()
        self.assertEqual(r['status'], 'PROPOSAL_BUDGET_EXCEEDED')
        self.assertFalse((self.root / 'proposal/candidate.py').exists())

    def test_handoff_uses_frozen_corpus_and_replays_complete_result(self):
        self.propose(); engine = Engine(b'5')
        r = p.evaluate(self.root / 'proposal', self.sha(), self.root / 'evaluation', engine)
        self.assertEqual(r['status'], 'CORRECTNESS_PRESERVED')
        self.assertFalse(r['automatic_promotion']); self.assertFalse(r['comparison']['performance_qualified'])
        self.assertEqual(engine.inputs, [[2, 3], [2, 3]])
        self.assertEqual(p.verify_evaluation(self.root / 'evaluation', self.sha()), r)
        self.assertEqual(set(r['cost_by_result_unit']), {'proposal_protocol', 'case_verification'})

    def test_bad_candidate_not_accepted_just_because_proposal_ready(self):
        self.propose(); engine = Engine(b'5'); count = [0]; execute = engine.execute
        def run(*args):
            count[0] += 1
            engine.output = b'5' if count[0] == 1 else b'6'
            return execute(*args)
        engine.execute = run
        r = p.evaluate(self.root / 'proposal', self.sha(), self.root / 'evaluation', engine)
        self.assertEqual(r['status'], 'EVALUATION_FAILED')
        self.assertEqual(p.verify_evaluation(self.root / 'evaluation', self.sha()), r)

    def test_failed_baseline_cleanup_stops_candidate_launch(self):
        self.propose(); engine = Engine(b'5'); engine.cleanup = False
        with self.assertRaisesRegex(ValueError, 'infrastructure_failure'):
            p.evaluate(self.root / 'proposal', self.sha(), self.root / 'evaluation', engine)
        self.assertEqual(len(engine.inputs), 1)
        self.assertFalse((self.root / 'evaluation/seal.json').exists())

    def test_nested_output_refused_without_touching_proposal(self):
        self.propose(); old = (self.root / 'proposal/seal.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'output_inside_proposal'):
            p.evaluate(self.root / 'proposal', self.sha(), self.root / 'proposal/evaluation', Engine(b'5'))
        self.assertEqual((self.root / 'proposal/seal.json').read_bytes(), old); self.verify()

    def test_resealed_evaluation_report_forgery_rejected(self):
        self.propose(); root = self.root / 'evaluation'
        p.evaluate(self.root / 'proposal', self.sha(), root, Engine(b'5'))
        path = root / 'report.json'; r = p.g.parse(path.read_bytes()); r['automatic_promotion'] = True
        path.write_bytes(p.ev.encoded(r)); self.reseal(root)
        with self.assertRaisesRegex(ValueError, 'evaluation_report_changed'): p.verify_evaluation(root, self.sha())

    def test_independently_rewritten_nested_evaluation_plan_rejected(self):
        self.propose(); root = self.root / 'evaluation'
        p.evaluate(self.root / 'proposal', self.sha(), root, Engine(b'5'))
        path = root / 'candidate/plan.json'; plan = p.g.parse(path.read_bytes())
        plan['corpus']['cases'][0]['expected'] = 6
        path.write_bytes(p.ev.encoded(plan)); self.reseal(root)
        with self.assertRaisesRegex(ValueError, 'evaluation_plan_changed'):
            p.verify_evaluation(root, self.sha())

    def test_bad_utf8_baseline_and_task_size_refused(self):
        with self.assertRaises(UnicodeError):
            p.plan(self.corpus, b'\xff', self.proposer, 'task', self.plan['evaluation']['image_id'])
        with self.assertRaisesRegex(ValueError, 'task_size'):
            p.plan(self.corpus, self.baseline, self.proposer, 'x'*8193, self.plan['evaluation']['image_id'])

    def test_missing_public_request_or_added_gold_cannot_verify(self):
        self.propose(); path = self.root / 'proposal/request.json'
        request = p.g.parse(path.read_bytes()); request['gold'] = self.corpus
        path.write_bytes(p.ev.encoded(request)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'public_request_changed'): self.verify()


if __name__ == '__main__': unittest.main()
