import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('runner_once',Path(__file__).parents[1]/'ci/self-hosted/run_once.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class SelfhostedValidationTests(unittest.TestCase):
    def setUp(self):
        self.run=dict(head_sha='a'*40,event='workflow_dispatch',actor={'login':'solanaqubits'},
                      triggering_actor={'login':'solanaqubits'},status='queued')
        self.jobs=[dict(status='queued',labels=['self-hosted','geek-work-isolated'])]
    def test_exact_manual_run(self):r.validate_run(self.run,'a'*40)
    def test_wrong_sha(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,'b'*40)
    def test_pr_refused(self):
        self.run['event']='pull_request'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_other_actor(self):
        self.run['triggering_actor']['login']='someone'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_complete_refused(self):
        self.run['status']='completed'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_queued_job(self):r.validate_jobs(self.jobs,'geek-work-isolated')
    def test_already_assigned(self):
        self.jobs[0]['status']='in_progress'
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'geek-work-isolated')
    def test_wrong_labels(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'geek-work-other')
    def test_multiple_jobs(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs*2,'geek-work-isolated')
    def test_label_injection(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'x; bad')

class FakeHost:
    """In-memory Docker/GitHub outcomes, including client failure after side effects."""
    def __init__(self, fault=None):
        self.fault=fault;self.container=False;self.registered=False;self.polls=0;self.calls=[]
        self.name='geek-work-once-'+'a'*16
    def call(self,args,**kwargs):
        import json
        import subprocess
        self.calls.append(args)
        if args[:3]==['docker','image','inspect']:return 'sha256:fixture\n'
        if args[:2]==['docker','run']:
            self.container=True
            if self.fault=='docker_client_timeout':raise subprocess.TimeoutExpired(args,60)
            return 'container-id\n'
        if args[:3]==['docker','exec','-i']:
            self.registered=True
            if self.fault=='partial_registration':raise subprocess.CalledProcessError(1,args,stderr='secret-token')
            return 'configured\n'
        if args[:3]==['docker','exec','-d']:return ''
        if args[:2]==['docker','rm']:
            if self.fault=='remove_failure':raise subprocess.CalledProcessError(1,args)
            self.container=False;return ''
        if args[:2]==['docker','ps']:
            if self.fault=='inspect_failure':raise subprocess.CalledProcessError(1,args)
            return 'still-present\n' if self.container else ''
        if args[:3]==['gh','run','view']:return 'synthetic job log\n'
        if args[:2]==['gh','api']:
            path=args[-1]
            if path.endswith('/registration-token'):return json.dumps({'token':'secret-token'})
            if '/runners/7' in path and 'DELETE' in args:self.registered=False;return ''
            if path.split('?',1)[0].endswith('/runners'):
                if self.fault=='cleanup_api_failure':raise subprocess.CalledProcessError(1,args)
                rows=[{'name':self.name,'id':7}] if self.registered else []
                if self.fault=='runner_on_second_page':
                    rows=[{'name':'other-'+str(i),'id':100+i} for i in range(100)]+rows
                page=2 if path.endswith('page=2') else 1
                return json.dumps({'runners':rows[(page-1)*100:page*100],'total_count':len(rows)})
            if path.endswith('/jobs'):
                job=dict(status='queued' if self.polls==1 else 'completed',labels=['self-hosted','geek-work-isolated'],runner_name=self.name)
                return json.dumps({'jobs':[job]})
            if '/runs/' in path:
                self.polls+=1
                return json.dumps(dict(head_sha='a'*40,event='workflow_dispatch',actor={'login':'solanaqubits'},
                                       triggering_actor={'login':'solanaqubits'},status='queued' if self.polls==1 else 'completed',
                                       conclusion='success',html_url='https://example.invalid/synthetic-run'))
        raise AssertionError(args)


class SelfhostedRecoveryTests(unittest.TestCase):
    def exercise(self, fault=None):
        import tempfile
        from unittest.mock import patch
        fake=FakeHost(fault)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'new'
            with patch.object(r.subprocess,'check_output',side_effect=fake.call),patch.object(r.uuid,'uuid4') as uid:
                uid.return_value.hex='a'*32
                result=r.execute('solanaqubits/simlab',1,'a'*40,'geek-work-isolated','fixture',out,60)
            import json
            self.assertEqual(json.loads((out/'receipt.json').read_text()),result)
            self.assertNotIn('secret-token',(out/'receipt.json').read_text())
            return result,fake
    def test_success_removes_both_resources(self):
        result,fake=self.exercise()
        self.assertEqual(result['status'],'success')
        self.assertFalse(fake.container);self.assertFalse(fake.registered)
        self.assertTrue(result['runner_removed'] and result['container_removed'])
    def test_docker_client_timeout_after_creation(self):
        result,fake=self.exercise('docker_client_timeout')
        self.assertEqual(result['status'],'error')
        self.assertFalse(fake.container)
        self.assertTrue(result['container_removed'])
    def test_partial_registration_cleanup(self):
        result,fake=self.exercise('partial_registration')
        self.assertEqual(result['status'],'error')
        self.assertFalse(fake.container);self.assertFalse(fake.registered)
    def test_remove_failure_not_success(self):
        result,fake=self.exercise('remove_failure')
        self.assertEqual(result['run_conclusion'],'success')
        self.assertEqual(result['status'],'cleanup_failed')
        self.assertFalse(result['container_removed'])
        self.assertTrue(fake.container)
    def test_unconfirmed_container_absence(self):
        result,fake=self.exercise('inspect_failure')
        self.assertFalse(result['container_removed'])
        self.assertEqual(result['status'],'cleanup_failed')
    def test_unavailable_registration_api(self):
        result,fake=self.exercise('cleanup_api_failure')
        self.assertEqual(result['status'],'cleanup_failed')
        self.assertFalse(result['runner_removed'])
        self.assertTrue(result['container_removed'])

    def test_runner_cleanup_paginates(self):
        result,fake=self.exercise('runner_on_second_page')
        self.assertEqual(result['status'],'success')
        self.assertFalse(fake.registered)
        self.assertTrue(any('page=2' in call[-1] for call in fake.calls if call[:2]==['gh','api']))
