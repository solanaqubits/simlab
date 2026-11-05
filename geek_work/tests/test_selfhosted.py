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
                job=dict(id=12,head_sha='a'*40,conclusion='success',status='queued' if self.polls==1 else 'completed',labels=['self-hosted','geek-work-isolated'],runner_name=self.name)
                if self.fault=='foreign_runner' and self.polls>1:job['runner_name']='unexpected'
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
    def test_attribution_failure_still_cleans_up(self):
        result,fake=self.exercise('foreign_runner')
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['reason'],'job ran on another runner')
        self.assertTrue(result['container_removed'] and result['runner_removed'])

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

class PrivatePRValidationTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40;self.repo='solanaqubits/simlab-private'
        self.pr=dict(number=1,state='open',user={'login':'solanaqubits'},
                     head=dict(sha=self.sha,user={'login':'solanaqubits'},repo={'full_name':self.repo}),
                     base=dict(sha='b'*40,ref='main',repo={'full_name':self.repo}))
        self.run=dict(head_sha=self.sha,event='pull_request',actor={'login':'solanaqubits'},
                      triggering_actor={'login':'solanaqubits'},status='queued',
                      pull_requests=[dict(number=1,head={'sha':self.sha})])
    def validate(self):return r.validate_pr(self.pr,self.repo,1,self.sha)
    def test_private_owner_pr(self):
        r.validate_run(self.run,self.sha,1)
        self.assertEqual(self.validate(),'b'*40)
    def test_pr_requires_explicit_mode(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha)
    def test_wrong_run_association(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,2)
    def test_public_pr_not_allowed(self):
        with self.assertRaises(ValueError):r.validate_pr(self.pr,'solanaqubits/simlab',1,self.sha)
    def test_fork_refused(self):
        self.pr['head']['repo']['full_name']='other/fork'
        with self.assertRaises(ValueError):self.validate()
    def test_pr_head_drift(self):
        self.pr['head']['sha']='c'*40
        with self.assertRaises(ValueError):self.validate()
    def test_closed_pr(self):
        self.pr['state']='closed'
        with self.assertRaises(ValueError):self.validate()
    def test_foreign_author(self):
        self.pr['user']['login']='other'
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_base(self):
        self.pr['base']['ref']='other'
        with self.assertRaises(ValueError):self.validate()

class PrivatePRExecutionTests(unittest.TestCase):
    def exercise(self, fault=None):
        import json
        import tempfile
        from unittest.mock import patch
        fake=FakeHost();pr_reads=0;sha='a'*40;label='geek-work-pr-1-'+sha
        fixture=PrivatePRValidationTests();fixture.setUp()
        def call(args,**kwargs):
            nonlocal pr_reads
            if args[:2]==['gh','api']:
                path=args[-1]
                if path.endswith('/pulls/1'):
                    pr_reads+=1;pr=copy.deepcopy(fixture.pr)
                    if fault=='base_drift' and pr_reads>1:pr['base']['sha']='c'*40
                    return json.dumps(pr)
                if '/compare/' in path:
                    return json.dumps({'merge_base_commit':{'sha':'c'*40 if fault=='missing_main' else 'b'*40}})
                if '/runs/' in path:
                    result=json.loads(fake.call(args,**kwargs))
                    if path.endswith('/jobs'):result['jobs'][0]['labels']=['self-hosted',label]
                    else:result.update(event='pull_request',pull_requests=[dict(number=1,head={'sha':sha})])
                    return json.dumps(result)
            return fake.call(args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r.subprocess,'check_output',side_effect=call),patch.object(r.uuid,'uuid4') as uid:
                uid.return_value.hex='a'*32
                result=r.execute('solanaqubits/simlab-private',1,sha,label,'fixture',Path(tmp)/'out',60,1)
        return result,fake
    def test_reviewed_pr_run(self):
        result,fake=self.exercise()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['pr_base_sha'],'b'*40)
        self.assertTrue(result['container_removed'] and result['runner_removed'])
    def test_current_main_missing_refused_before_container(self):
        result,fake=self.exercise('missing_main')
        self.assertEqual(result['status'],'error')
        self.assertFalse(any(c[:2]==['docker','run'] for c in fake.calls))
    def test_base_advancement_invalidates_receipt(self):
        result,fake=self.exercise('base_drift')
        self.assertEqual(result['status'],'error')
        self.assertIn('base changed',result['reason'])
        self.assertTrue(result['container_removed'] and result['runner_removed'])

class MainPushValidationTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40
        self.run=dict(head_sha=self.sha,event='push',head_branch='main',actor={'login':'solanaqubits'},
                      triggering_actor={'login':'solanaqubits'},status='queued')
        self.ref=dict(ref='refs/heads/main',object={'sha':self.sha})
    def test_main_push(self):
        r.validate_run(self.run,self.sha,main_mode=True)
        r.validate_main(self.ref,'solanaqubits/simlab-private',self.sha)
    def test_explicit_mode_required(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha)
    def test_non_main_push(self):
        self.run['head_branch']='feature'
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,main_mode=True)
    def test_public_main_refused(self):
        with self.assertRaises(ValueError):r.validate_main(self.ref,'solanaqubits/simlab',self.sha)
    def test_main_advancement(self):
        self.ref['object']['sha']='b'*40
        with self.assertRaises(ValueError):r.validate_main(self.ref,'solanaqubits/simlab-private',self.sha)
    def test_modes_cannot_mix(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,1,True)
    def test_pr_not_main_event(self):
        self.run['event']='pull_request'
        with self.assertRaises(ValueError):r.validate_run(self.run,self.sha,main_mode=True)
    def test_wrong_ref(self):
        self.ref['ref']='refs/heads/feature'
        with self.assertRaises(ValueError):r.validate_main(self.ref,'solanaqubits/simlab-private',self.sha)

class MainPushExecutionTests(unittest.TestCase):
    def exercise(self, drift=False):
        import json
        import tempfile
        from unittest.mock import patch
        fake=FakeHost();reads=0;sha='a'*40;label='geek-work-main-'+sha
        def call(args,**kwargs):
            nonlocal reads
            if args[:2]==['gh','api']:
                path=args[-1]
                if path.endswith('/git/ref/heads/main'):
                    reads+=1
                    return json.dumps(dict(ref='refs/heads/main',object={'sha':'b'*40 if drift and reads>1 else sha}))
                if '/runs/' in path:
                    result=json.loads(fake.call(args,**kwargs))
                    if path.endswith('/jobs'):result['jobs'][0]['labels']=['self-hosted',label]
                    else:result.update(event='push',head_branch='main')
                    return json.dumps(result)
            return fake.call(args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r.subprocess,'check_output',side_effect=call),patch.object(r.uuid,'uuid4') as uid:
                uid.return_value.hex='a'*32
                result=r.execute('solanaqubits/simlab-private',1,sha,label,'fixture',Path(tmp)/'out',60,main_mode=True)
        return result
    def test_main_execution(self):
        result=self.exercise()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['source_ref'],'refs/heads/main')
        self.assertTrue(result['container_removed'] and result['runner_removed'])
    def test_main_advances_during_execution(self):
        result=self.exercise(True)
        self.assertEqual(result['status'],'error')
        self.assertIn('main advanced',result['reason'])
        self.assertTrue(result['container_removed'] and result['runner_removed'])


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.job=dict(id=12,head_sha='a'*40,status='completed',conclusion='success',
                      runner_name='expected',labels=['self-hosted','geek-work-isolated'])
    def exercise(self, responses, error=None):
        import tempfile,json
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);fetch=Mock(side_effect=responses);sleep=Mock()
            if error:
                with self.assertRaises(error):
                    r.reconcile_jobs(fetch,out,12,'expected','a'*40,'geek-work-isolated','success',sleep)
            else:
                jobs,n=r.reconcile_jobs(fetch,out,12,'expected','a'*40,'geek-work-isolated','success',sleep)
                self.assertEqual(jobs,[self.job]);self.assertEqual(n,len(responses))
            saved=sorted(out.glob('jobs-observation-*.json'))
            self.assertEqual(len(saved),fetch.call_count)
            for path,response in zip(saved,responses):self.assertEqual(json.loads(path.read_text()),response)
            return fetch.call_count,sleep.call_count
    def test_complete(self):self.assertEqual(self.exercise([{'jobs':[self.job]}]),(1,0))
    def test_missing_runner_recovers(self):
        stale={**self.job,'runner_name':None}
        self.assertEqual(self.exercise([{'jobs':[stale]},{'jobs':[self.job]}]),(2,1))
    def test_running_recovers(self):
        self.exercise([{'jobs':[{**self.job,'status':'in_progress','conclusion':None}]},{'jobs':[self.job]}])
    def test_empty_recovers(self):self.exercise([{'jobs':[]},{'jobs':[self.job]}])
    def test_exhaustion_preserves_all(self):
        self.assertEqual(self.exercise([{'jobs':[]}]*5,TimeoutError),(5,4))
    def test_foreign_runner_not_retried(self):
        self.assertEqual(self.exercise([{'jobs':[{**self.job,'runner_name':'other'}]}],ValueError),(1,0))
    def test_wrong_identity_sha_labels_or_conclusion(self):
        for key,value in [('id',13),('head_sha','b'*40),('labels',[]),('conclusion','failure')]:
            with self.subTest(key=key):self.exercise([{'jobs':[{**self.job,key:value}]}],ValueError)
    def test_extra_or_truncated_listing(self):
        for response in [{'jobs':[self.job]*2},{'jobs':[self.job],'total_count':2}]:
            self.exercise([response],ValueError)
