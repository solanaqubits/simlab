import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_selfhosted as fixtures

r=fixtures.r


class PendingRunnerTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40
        self.run=dict(head_sha=self.sha,event='workflow_dispatch',status='pending',actor={'login':'solanaqubits'},triggering_actor={'login':'solanaqubits'})

    def test_pending_manual_event_is_observable(self):r.validate_run(self.run,self.sha)

    def test_pending_main_still_requires_exact_push(self):
        self.run.update(event='push',head_branch='main');r.validate_run(self.run,self.sha,main_mode=True)
        self.run['head_branch']='feature'
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,main_mode=True)

    def test_pending_pr_still_requires_explicit_association(self):
        self.run.update(event='pull_request',pull_requests=[dict(number=1,head={'sha':self.sha})]);r.validate_run(self.run,self.sha,1)
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,2)

    def test_pending_does_not_bypass_actor_or_sha(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,'b'*40)
        self.run['triggering_actor']['login']='other'
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha)

    def test_approval_terminal_and_unknown_states_refused(self):
        for status in ('waiting','requested','completed','action_required','cancelled','unknown'):
            with self.subTest(status=status),self.assertRaises(ValueError):r.validate_run(dict(self.run,status=status),self.sha)

    def exercise(self,fault=None):
        fake=fixtures.FakeHost();snapshots={}
        def call(args,**kwargs):
            result=fake.call(args,**kwargs)
            if args[:2]==['gh','api'] and '/runs/' in args[-1]:
                value=json.loads(result)
                if args[-1].endswith('/jobs') and fake.polls==1:
                    value['total_count']=1
                    if fault=='assigned':value['jobs'][0]['status']='in_progress'
                    if fault=='wrong_labels':value['jobs'][0]['labels']=['self-hosted','geek-work-other']
                    if fault=='wrong_job_sha':value['jobs'][0]['head_sha']='b'*40
                    if fault=='incomplete':value['total_count']=2
                    if fault=='missing':value.update(jobs=[],total_count=0)
                elif not args[-1].endswith('/jobs') and fake.polls==1:
                    value['status']='pending'
                    if fault=='wrong_actor':value['actor']['login']='other'
                return json.dumps(value)
            return result
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'evidence'
            with patch.object(r.subprocess,'check_output',side_effect=call),patch.object(r.uuid,'uuid4') as uid:
                uid.return_value.hex='a'*32
                result=r.execute('solanaqubits/simlab',1,self.sha,'geek-work-isolated','fixture',output,60)
            for path in output.glob('*before.json'):snapshots[path.name]=json.loads(path.read_text())
            self.assertNotIn('secret-token',(output/'receipt.json').read_text())
        return result,fake,snapshots

    def test_pending_queued_job_completes_and_preserves_observations(self):
        result,fake,observed=self.exercise();self.assertEqual(result['status'],'success')
        self.assertEqual(result['initial_run_status'],'pending');self.assertEqual(observed['run-before.json']['status'],'pending')
        self.assertEqual(observed['jobs-before.json']['jobs'][0]['status'],'queued');self.assertFalse(fake.container or fake.registered)
        self.assertTrue(result['runner_removed'] and result['container_removed'])

    def test_assigned_pending_job_refused_before_container(self):self.assert_refused('assigned')
    def test_wrong_labels_in_pending_run_refused(self):self.assert_refused('wrong_labels')
    def test_wrong_job_sha_in_pending_run_refused(self):self.assert_refused('wrong_job_sha')
    def test_incomplete_pending_job_listing_refused(self):self.assert_refused('incomplete')
    def test_pending_without_job_refused(self):self.assert_refused('missing')

    def assert_refused(self,fault):
        result,fake,observed=self.exercise(fault);self.assertEqual(result['status'],'error')
        self.assertIn('jobs-before.json',observed);self.assertFalse(any(args[:2]==['docker','run'] for args in fake.calls))
        self.assertFalse(any('/registration-token' in args[-1] for args in fake.calls))
        self.assertTrue(result['runner_removed'] and result['container_removed'])

    def test_rejected_pending_run_observation_retained_without_job_request(self):
        result,fake,observed=self.exercise('wrong_actor');self.assertEqual(result['status'],'error')
        self.assertIn('run-before.json',observed);self.assertNotIn('jobs-before.json',observed)
        self.assertFalse(any(args[:2]==['docker','run'] for args in fake.calls))


if __name__=='__main__':unittest.main()
