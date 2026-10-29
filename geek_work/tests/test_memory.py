import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import geek_work_memory as m
import knowledge as k
sys.path.pop(0)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'source.txt').write_text('Pinned conditional model, not a physical guarantee.')
        template = dict(id='claim:synthetic',revision=1,kind='claim',
                        title='Synthetic statement',text='If x = 0 then x + 1 = 1.',
                        scope='Synthetic integer example only',assumptions=['x = 0'],
                        domains=['mathematics'],directions=[],tags=[],categories=['knowledge_graph'],
                        projects=['synthetic'],status='conditional_statement',provenance=[],
                        evidence={name:dict(state='none',refs=[],limits='Synthetic test; no external audit')
                                  for name in ('formal','computational','empirical')},
                        detail={'summary':'Synthetic fixture'},review={})
        self.g = dict(schema=k.SCHEMA, cards=[], links=[], events=[])
        for cid in ('claim:premise', 'claim:result', 'claim:objection'):
            c = copy.deepcopy(template)
            c.update(id=cid, kind='claim', revision=1, detail={'summary': 'Synthetic fixture, not knowledge'},
                     provenance=[dict(ref='source.txt', locator='whole fixture',
                                      sha256=k.digest((self.root/'source.txt').read_bytes()))])
            c['review'] = dict(state='reviewed', as_of='2026-10-28', applicability='Fixture only', dependencies={})
            self.g['cards'].append(c)
        self.g['links'] = [dict(**{'from':'claim:result', 'to':'claim:premise'}, relation='depends_on', scope='Conditional premise')]
        self.g['cards'][1]['review']['dependencies'] = {'claim:premise':1}
        self.req = dict(schema='geek-work-memory-request-1', expected_graph_sha256=k.digest(k.canonical(self.g)),
                        cards=[dict(id='claim:result', revision=1)])
        self.profile = dict(model_id='fixture-approved', configuration={'temperature':None})
        self.policy = dict(schema='geek-work-review-policy-1', profiles=[dict(profile=self.profile,
                           task_classes=['complex_review'], basis='Test-only policy, not empirical qualification')],
                           machine_checkers=[dict(sha256='b'*64, task_classes=['identity'], basis='Fixture checker')])
        self.attempt = dict(schema='geek-work-review-attempt-1', policy_sha256=k.digest(k.canonical(self.policy)),
                            task_class='complex_review', kind='model_review', expected_profile=self.profile,
                            observed_profile=self.profile, artifact_sha256='a'*64, verifier_receipt=None)

    def retrieve(self): return m.retrieve(self.g, self.root, self.req)
    def qualify(self): return m.qualify(self.policy, self.attempt, self.root)

    def machine(self, result='pass'):
        receipt = dict(schema='geek-work-machine-receipt-1', artifact_sha256='a'*64,
                       checker_sha256='b'*64, task_class='identity', result=result)
        raw = k.canonical(receipt); (self.root/'receipt.json').write_bytes(raw)
        self.attempt.update(kind='machine_check', task_class='identity', observed_profile=None,
                            verifier_receipt=dict(path='receipt.json', sha256=k.digest(raw)))

    def test_context_preserves_full_card_scope_evidence_and_dependency(self):
        old = copy.deepcopy(self.g); r = self.retrieve()
        self.assertEqual(r['disposition'], 'context_ready')
        self.assertEqual({row['card']['id'] for row in r['cards']}, {'claim:result','claim:premise'})
        self.assertEqual(r['cards'][1]['card'], self.g['cards'][1])
        self.assertEqual(self.g, old)
        self.assertFalse(r['truth_status_changed'])

    def test_revision_and_snapshot_drift_remain_history(self):
        c = copy.deepcopy(self.g['cards'][0]); c['revision'] = 2
        self.g = k.revise(self.g, c, 'Fixture premise changed', '2026-10-28')
        r = self.retrieve()
        self.assertIn('snapshot_changed', r['issues'])
        self.assertIn('review_needs_review', r['issues'])
        self.assertEqual(r['cards'][1]['card']['status'], self.g['cards'][1]['status'])
        self.assertEqual(len(self.g['events']), 1)

    def test_selected_revision_pin_checked(self):
        self.req['cards'][0]['revision'] = 99
        self.assertIn('revision_changed', self.retrieve()['issues'])

    def test_source_missing_and_changed_are_visible(self):
        (self.root/'source.txt').write_text('Changed')
        self.assertIn('source_hash_mismatch', self.retrieve()['issues'])
        (self.root/'source.txt').unlink()
        self.assertIn('source_missing', self.retrieve()['issues'])

    def test_objection_is_returned_not_silently_resolved(self):
        self.g['links'].append(dict(**{'from':'claim:objection','to':'claim:result'},
                                    relation='contradicts', scope='Unresolved scope conflict'))
        self.req['expected_graph_sha256'] = k.digest(k.canonical(self.g))
        r = self.retrieve()
        self.assertEqual(len(r['cards']),3)
        self.assertIn('linked_objection_requires_review',r['issues'])

    def test_pending_and_superseded_not_ready(self):
        self.g['cards'][0]['review']['state'] = 'pending'
        self.g['cards'][0]['status'] = 'superseded'
        self.assertIn('review_pending', self.retrieve()['issues'])
        self.assertIn('superseded', self.retrieve()['issues'])

    def test_cycles_terminate_and_caps_refuse_truncation(self):
        self.g['links'].append(dict(**{'from':'claim:premise','to':'claim:result'}, relation='depends_on',scope='Fixture cycle'))
        self.g['cards'][0]['review']['dependencies'] = {'claim:result':1}
        self.assertEqual(len(self.retrieve()['cards']),2)
        self.req['cards'] *= 33
        with self.assertRaises(k.Refusal): self.retrieve()

    def test_source_traversal_and_symlink_refused(self):
        for ref in ('../outside','/etc/passwd'):
            with self.assertRaises(k.Refusal): m.file_check(self.root, ref, 'a'*64)
        (self.root/'link').symlink_to(self.root/'source.txt')
        with self.assertRaises(k.Refusal): m.file_check(self.root,'link','a'*64)

    def test_known_profile_is_only_eligible_not_accepted(self):
        r = self.qualify()
        self.assertEqual(r['disposition'],'eligible_for_review')
        self.assertFalse(r['accepted_result'])

    def test_fallback_cannot_inherit_complex_review_permission(self):
        self.attempt['observed_profile'] = dict(model_id='fixture-fallback', configuration={})
        self.assertIn('profile_changed',self.qualify()['issues'])
        self.assertIn('profile_not_qualified_for_task',self.qualify()['issues'])

    def test_changed_configuration_not_same_model_profile(self):
        self.attempt['observed_profile'] = copy.deepcopy(self.profile)
        self.attempt['observed_profile']['configuration']['temperature'] = 'unknown'
        self.assertEqual(self.qualify()['transition'],'changed')

    def test_unknown_profile_blocked(self):
        self.attempt['observed_profile'] = None
        self.assertEqual(self.qualify()['transition'],'unknown')
        self.assertEqual(self.qualify()['disposition'],'blocked')

    def test_policy_task_and_capability_substitution_blocked(self):
        self.attempt['task_class'] = 'formal_audit'
        self.assertIn('profile_not_qualified_for_task',self.qualify()['issues'])
        self.policy['profiles'][0]['task_classes'].append('formal_audit')
        self.assertIn('policy_changed',self.qualify()['issues'])

    def test_machine_check_does_not_depend_on_author_model(self):
        self.machine()
        self.assertEqual(self.qualify()['disposition'],'eligible_for_review')
        self.assertEqual(self.qualify()['transition'],'unknown')

    def test_verifier_rejection_or_error_is_never_acceptance(self):
        for outcome in ('reject','error'):
            self.machine(outcome)
            self.assertIn('verifier_'+outcome,self.qualify()['issues'])

    def test_missing_or_modified_receipt_blocked(self):
        self.machine(); (self.root/'receipt.json').write_text('{}')
        self.assertIn('verifier_hash_mismatch',self.qualify()['issues'])
        self.attempt['verifier_receipt'] = None
        self.assertIn('verifier_missing',self.qualify()['issues'])

    def test_wrong_artifact_binding_and_unknown_checker_blocked(self):
        self.machine(); self.attempt['artifact_sha256'] = 'c'*64
        self.assertIn('artifact_mismatch',self.qualify()['issues'])
        self.policy['machine_checkers'] = []
        self.attempt['policy_sha256'] = k.digest(k.canonical(self.policy))
        self.assertIn('checker_not_qualified_for_task',self.qualify()['issues'])

    def test_duplicate_profile_and_malformed_policy_refused(self):
        self.policy['profiles'] *= 2
        with self.assertRaises(k.Refusal): self.qualify()

    def test_cli_no_overwrite_and_structured_block(self):
        for name, value in [('graph',self.g),('request',self.req)]:
            (self.root/(name+'.json')).write_bytes(k.canonical(value))
        cmd = [sys.executable,'-B',str(TOOLS/'geek_work_memory.py'),'retrieve',
               str(self.root/'graph.json'),str(self.root/'request.json'),
               '--root',str(self.root),'--output',str(self.root/'context.json')]
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        before = (self.root/'context.json').read_bytes()
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
        self.assertEqual((self.root/'context.json').read_bytes(),before)


if __name__ == '__main__': unittest.main()
