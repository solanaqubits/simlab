import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import container_watchdog as w

IMAGE = 'sha256:' + 'a' * 64
CID = 'b' * 64


def spec(command=None):
    return dict(image=IMAGE, command=command or ['/bin/true'], timeout_seconds=.1,
                memory_bytes=64 << 20, cpus=.5, pids=32, tmpfs_bytes=8 << 20, binds=[])


class FakeDocker(w.Docker):
    def __init__(self, mode='success'):
        super().__init__(); self.mode=mode; self.exists=False; self.token=None
        self.state={'Running':False, 'Restarting':False, 'Pid':0, 'Status':'created',
                    'ExitCode':0, 'OOMKilled':False}
        self.interrupted=False

    def call(self, args, timeout=5):
        code=0;out='';err=''
        if args[:2]==['image','inspect']:
            if self.mode=='image-error':code=1;err='missing image'
            else:out=IMAGE
        elif args[0]=='create':
            self.token=args[args.index('--label')+1].split('=',1)[1]
            self.exists=True;out=CID
            if self.mode=='ambiguous-create':code=None;err='client deadline'
        elif args[0]=='inspect':
            if not self.exists:code=1;err='missing container'
            elif self.mode=='interrupt' and self.state['Running'] and not self.interrupted:
                self.interrupted=True;raise KeyboardInterrupt
            else:
                token='foreign' if self.mode=='foreign-label' else self.token
                out=json.dumps([{'Id':CID,'Image':IMAGE,'Config':{'Labels':{w.LABEL:token}},'State':self.state}])
        elif args[0]=='start':
            if self.mode=='never-started':pass
            elif self.mode in ('success','nonzero','oom','crash'):
                self.state.update(Status='exited', ExitCode={'nonzero':7,'oom':137,'crash':137}.get(self.mode,0), OOMKilled=self.mode=='oom')
            else:self.state.update(Running=True,Pid=12345,Status='running')
        elif args[0]=='kill':
            if self.mode=='kill-error':code=1;err='kill failure'
            else:self.state.update(Running=False,Pid=0,Status='exited',ExitCode=137)
        elif args[0]=='rm':
            if self.mode=='rm-error':code=1;err='rm failure'
            else:self.exists=False
        else:raise AssertionError(args)
        row={'argv':['docker','--host','unix:///var/run/docker.sock',*args],
             'returncode':code,'stdout':out,'stderr':err,'timed_out':code is None,'elapsed_seconds':0}
        self.calls.append(row);return row


class WatchdogTests(unittest.TestCase):
    def execute(self, mode, assertion):
        clock=[0]
        def tick():clock[0]+=.2;return clock[0]
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'run';d=FakeDocker(mode)
            with patch.object(w.time,'monotonic',side_effect=tick),patch.object(w.time,'sleep'):
                r=w.supervise(spec(),out,docker=d)
            self.assertEqual(w.audit(out),r)
            assertion(r,d,out)

    def test_completed_is_execution_not_certificate_verdict(self):
        def check(r,d,p):
            self.assertEqual(r['status'],'EXEC_COMPLETED');self.assertEqual(r['exit_code'],0)
            self.assertTrue(r['termination_confirmed']);self.assertTrue(r['removed'])
            self.assertNotIn('verdict',r);self.assertFalse(d.exists)
        self.execute('success',check)

    def test_nonzero_is_not_decode_error(self):
        self.execute('nonzero',lambda r,d,p:self.assertEqual((r['status'],r['exit_code']),('EXEC_NONZERO_EXIT',7)))

    def test_created_container_is_not_successful_execution(self):
        self.execute('never-started',lambda r,d,p:self.assertEqual(r['status'],'EXEC_DOCKER_ERROR'))

    def test_timeout_requires_actual_stop(self):
        def check(r,d,p):
            self.assertEqual(r['status'],'EXEC_TIMEOUT');self.assertTrue(r['deadline_exceeded'])
            self.assertEqual(r['final_state']['Pid'],0);self.assertFalse(d.exists)
        self.execute('timeout',check)

    def test_kill_failure_never_claims_timeout_enforced(self):
        self.execute('kill-error',lambda r,d,p:self.assertEqual((r['status'],r['termination_confirmed']),('EXEC_CLEANUP_ERROR',False)))

    def test_rm_failure_is_explicit(self):
        self.execute('rm-error',lambda r,d,p:self.assertEqual((r['status'],r['removed']),('EXEC_CLEANUP_ERROR',False)))

    def test_oom_requires_engine_evidence(self):
        self.execute('oom',lambda r,d,p:self.assertEqual(r['status'],'EXEC_OOM'))

    def test_sigkill_without_oom_is_crash(self):
        self.execute('crash',lambda r,d,p:self.assertEqual(r['status'],'EXEC_CRASH'))

    def test_ambiguous_create_is_cleaned(self):
        self.execute('ambiguous-create',lambda r,d,p:self.assertEqual((r['status'],d.exists),('EXEC_DOCKER_ERROR',False)))

    def test_foreign_label_is_never_killed_or_removed(self):
        def check(r,d,p):
            self.assertEqual(r['status'],'EXEC_CLEANUP_ERROR')
            self.assertFalse(any(c['argv'][3] in ('kill','rm') for c in d.calls))
        self.execute('foreign-label',check)

    def test_interrupt_still_cleans_owned_container(self):
        self.execute('interrupt',lambda r,d,p:self.assertEqual((r['status'],r['removed']),('EXEC_CANCELLED',True)))

    def test_missing_image_does_not_pull_or_create(self):
        self.execute('image-error',lambda r,d,p:self.assertEqual(len(d.calls),1))

    def test_audit_rejects_mutated_timeout_and_exit(self):
        def check(r,d,p):
            for key,value in [('deadline_exceeded',False),('exit_code',0),('termination_confirmed',False),('status','EXEC_COMPLETED')]:
                bad={**r,key:value};(p/'receipt.json').write_bytes(w.canonical(bad))
                with self.assertRaises(ValueError):w.audit(p)
            (p/'receipt.json').write_bytes(w.canonical(r))
            (p/'spec.json').write_text('{}')
            with self.assertRaises(ValueError):w.audit(p)
        self.execute('timeout',check)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileExistsError):w.supervise(spec(),td,docker=FakeDocker())

    def test_rejects_unknown_unbounded_or_mutable_inputs(self):
        for field,value in [('image','alpine:latest'),('timeout_seconds',float('inf')),
                            ('timeout_seconds',True),('memory_bytes',0),('cpus',100),
                            ('pids',True),('command',['']),('binds',[{'source':'/','target':'/','read_only':True}])]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):w.validate_spec({**spec(),field:value})
        with self.assertRaises(ValueError):w.validate_spec({**spec(),'privileged':True})
        with self.assertRaises(ValueError):w.strict_json('{"a":1,"a":2}')

    def test_create_has_fixed_isolation_and_no_swap(self):
        args=w.create_args(spec(['/bin/sh','-c','exit 0']),'name','token')
        for flag in ['--network=none','--read-only','--cap-drop=ALL','--pull=never',
                     '--memory=67108864','--memory-swap=67108864','--restart=no']:
            self.assertIn(flag,args)
        self.assertEqual(args[-5:],['--entrypoint','/bin/sh',IMAGE,'-c','exit 0'])

    def test_bind_validation_and_explicit_mode(self):
        with tempfile.TemporaryDirectory() as td:
            s=spec();s['binds']=[dict(source=td,target='/inputs/corpus',read_only=True)]
            w.validate_spec(s);self.assertIn('type=bind,src='+td+',dst=/inputs/corpus,readonly',w.create_args(s,'n','t'))
            s['binds'][0]['target']='/var/run/docker.sock'
            with self.assertRaises(ValueError):w.validate_spec(s)

    def test_archive_validation_does_not_require_old_bind_sources(self):
        s=spec();s['binds']=[dict(source='/nonexistent/historical/input',target='/inputs/corpus',read_only=True)]
        w.validate_spec(s,check_bind_sources=False)
        with self.assertRaises(ValueError):w.validate_spec(s)


if __name__=='__main__':unittest.main()
