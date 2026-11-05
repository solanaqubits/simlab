import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_alcc_replay as r
import geek_work_alcc_tasks as a


def save(path,value):path.write_bytes(a.canonical(value)+b'\n')

def fixture(root):
    root.mkdir();c=a.corpus()
    (root/'binary').write_bytes(b'fixture, never executable')
    for name in ['generated.c','link-input-hashes.json','kernel.lean','cached.lean','lean-toolchain','lake-manifest.json']:(root/name).write_text('fixture, never used as code')
    (root/'original-oracle.py').write_bytes(b'fixture, never imported')
    (root/'current-oracle.py').write_bytes(Path(a.__file__).read_bytes())
    save(root/'corpus.json',c);(root/'adapter.lean').write_text(a.lean_source(c));(root/'contract.md').write_text('fixture')
    plan=dict(pins={'.local/quantum-alcc-evidence/alcc-full-task':r.sha(root/'binary'),
        'digital-brain/tools/geek_work_alcc_tasks.py':r.sha(root/'original-oracle.py'),
        r.PREFIX+'corpus.json':r.sha(root/'corpus.json'),r.PREFIX+'AlccFullTaskBench.lean':r.sha(root/'adapter.lean'),r.PREFIX+'CONTRACT.ru.md':r.sha(root/'contract.md')},image='sha256:'+'a'*64,repeats=2)
    save(root/'plan.json',plan)
    save(root/'build.json',dict(binary_sha256=r.sha(root/'binary'),source_sha256=r.sha(root/'adapter.lean')))
    save(root/'origin.json',dict(source_commit=r.SOURCE_COMMIT,archive_manifest_sha256='b'*64))
    for i in (1,2):
        p=root/f'run-{i:03}';p.mkdir();rows=[]
        for case in c['cases']:
            e=a.oracle(case)
            for j in range(11):
                for v in (['baseline','cached'] if j%2==0 else ['cached','baseline']):
                    rows.append(dict(case=case['id'],round=j,variant=v,accepted=not e,output=e,elapsed_ns=5,force_digest=sum(sum(t[0])+int(t[2]) for t in e)))
        raw='\n'.join(json.dumps(row) for row in rows)
        (p/'stdout.jsonl').write_text(raw);(p/'stderr.txt').write_bytes(b'')
        save(p/'result.json',a.validate(c,raw));save(p/'transport.json',dict(exit_code=0,issue=None,wall_time_ms=20))
        host=copy.deepcopy(r.LIMITS);host.update(Mounts=[dict(Type='bind',Source='/fixture/bench',Target='/app/bench',ReadOnly=True)],OomKillDisable=False)
        cfg=dict(User='65534:65534',Entrypoint=['/usr/local/bin/python3'],Cmd=['-I','-c',r.LAUNCHER],Env=['LEAN_NUM_THREADS=0','LEAN_STACK_SIZE_KB=8192'])
        before=dict(Id=f'fixture-{i}',Name=f'/fixture-{i}',Image=plan['image'],HostConfig=host,Config=cfg,State=dict(Status='created',Running=False))
        after=copy.deepcopy(before);after['State']=dict(Status='exited',Running=False,OOMKilled=False,ExitCode=0);after['HostConfig']['OomKillDisable']=None
        save(p/'inspect-before.json',before);save(p/'inspect-after.json',after)
        save(p/'cleanup.json',dict(name=f'fixture-{i}',removed=True))
    return r.seal(root)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'bundle';self.anchor=fixture(self.root)
    def tearDown(self):self.tmp.cleanup()
    def reseal(self):
        (self.root/'manifest.json').unlink();self.anchor=r.seal(self.root)
    def mutate(self,path,fn):
        p=self.root/path;d=r.json_load(p);fn(d);save(p,d);self.reseal()
    def check(self):return r.verify(self.root,self.anchor)
    def test_success_is_only_replay(self):
        d=self.check();self.assertEqual(d['full_outputs_checked'],396);self.assertEqual(d['native_executions'],0);self.assertFalse(d['independent_audit_completed'])
    def test_external_anchor(self):
        with self.assertRaisesRegex(ValueError,'external_anchor'):r.verify(self.root,'0'*64)
    def test_changed_bytes(self):
        (self.root/'binary').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):self.check()
    def test_resealed_binary_breaks_plan(self):
        (self.root/'binary').write_bytes(b'changed');self.reseal()
        with self.assertRaisesRegex(ValueError,'plan_binding'):self.check()
    def test_changed_correctness(self):
        p=self.root/'run-001/stdout.jsonl';s=p.read_text().replace('"accepted": true','"accepted": false',1);p.write_text(s);self.reseal()
        with self.assertRaisesRegex(ValueError,'verdict'):self.check()
    def test_false_saved_result(self):
        self.mutate('run-001/result.json',lambda d:d.update(performance_qualified=True))
        with self.assertRaisesRegex(ValueError,'saved_result'):self.check()
    def test_missing_cleanup(self):
        self.mutate('run-001/cleanup.json',lambda d:d.update(removed=False))
        with self.assertRaisesRegex(ValueError,'cleanup'):self.check()
    def test_oom(self):
        self.mutate('run-001/inspect-after.json',lambda d:d['State'].update(OOMKilled=True))
        with self.assertRaisesRegex(ValueError,'final_state'):self.check()
    def test_transport_failure(self):
        self.mutate('run-001/transport.json',lambda d:d.update(issue='timeout'))
        with self.assertRaisesRegex(ValueError,'transport_failure'):self.check()
    def test_wall_budget(self):
        self.mutate('run-001/transport.json',lambda d:d.update(wall_time_ms=180001))
        with self.assertRaisesRegex(ValueError,'wall_limit'):self.check()
    def test_weakened_limits(self):
        self.mutate('run-001/inspect-before.json',lambda d:d['HostConfig'].update(Privileged=True))
        with self.assertRaisesRegex(ValueError,'container_limits'):self.check()
    def test_writable_binary(self):
        self.mutate('run-001/inspect-before.json',lambda d:d['HostConfig']['Mounts'][0].update(ReadOnly=False))
        with self.assertRaisesRegex(ValueError,'writable_mount'):self.check()
    def test_wrong_launcher(self):
        self.mutate('run-001/inspect-before.json',lambda d:d['Config'].update(Cmd=['-c','print(1)']))
        with self.assertRaisesRegex(ValueError,'launcher'):self.check()
    def test_oom_disable_not_tolerated(self):
        self.mutate('run-001/inspect-before.json',lambda d:d['HostConfig'].update(OomKillDisable=True))
        with self.assertRaisesRegex(ValueError,'oom_kill_disabled'):self.check()
    def test_unexpected_file(self):
        (self.root/'payload').write_text('x')
        with self.assertRaisesRegex(ValueError,'unexpected_files'):self.check()
    def test_symlink(self):
        p=self.root/'binary';b=p.read_bytes();p.unlink();q=Path(self.tmp.name)/'outside';q.write_bytes(b);p.symlink_to(q)
        with self.assertRaisesRegex(ValueError,'symlink'):self.check()
    def test_duplicate_json(self):
        p=self.root/'origin.json';p.write_text('{"a":1,"a":2}');self.reseal()
        with self.assertRaisesRegex(ValueError,'duplicate_key'):self.check()
    def test_path_traversal(self):
        with self.assertRaisesRegex(ValueError,'unsafe_path'):r.file_at(self.root,'../outside')
    def test_pack_bad_anchor_no_output(self):
        archive=Path(self.tmp.name)/'archive';archive.mkdir();(archive/'MANIFEST.sha256').write_text('')
        output=Path(self.tmp.name)/'new'
        with self.assertRaisesRegex(ValueError,'archive_anchor'):r.pack(archive,'0'*64,Path('.'),output)
        self.assertFalse(output.exists())
    def test_pack_no_overwrite(self):
        with self.assertRaisesRegex(ValueError,'output_exists'):r.pack(Path('none'),'0'*64,Path('.'),self.root)
