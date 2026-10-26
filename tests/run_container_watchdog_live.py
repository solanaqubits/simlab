"""Explicit offline host/Docker integration tests. No skip or mock substitution.

Run with WATCHDOG_EVIDENCE pointing to a new evidence directory. The image must
already exist locally; neither the test nor the supervisor pulls images.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import container_watchdog as w
IMAGE='sha256:a40c03cbb81c59bfb0e0887ab0b1859727075da7b9cc576a1cec2c771f38c5fb'
DOCKER=['docker','--host','unix:///var/run/docker.sock']


def identity(pid):
    try:
        values=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
        return {'pid':pid,'starttime':values[19],'state':values[0]}
    except FileNotFoundError:return None


class ContainerLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=Path(os.environ['WATCHDOG_EVIDENCE']).resolve()
        cls.evidence.mkdir(parents=True,exist_ok=False)
        p=subprocess.run([*DOCKER,'image','inspect',IMAGE],capture_output=True,text=True,timeout=5)
        (cls.evidence/'image-inspect.json').write_text(p.stdout)
        if p.returncode:raise RuntimeError('Pinned local image unavailable: '+p.stderr)
        cls.original_names=subprocess.check_output([*DOCKER,'ps','-aq','--no-trunc'],text=True,timeout=5).splitlines()
        (cls.evidence/'containers-before.json').write_text(json.dumps(cls.original_names,indent=2)+'\n')

    def run_case(self,name,command,expected,exit_code,timeout=10,interrupt=False):
        out=self.evidence/name
        spec=dict(image=IMAGE,command=command,timeout_seconds=timeout,memory_bytes=64<<20,
                  cpus=.5,pids=32,tmpfs_bytes=8<<20,binds=[])
        spec_path=self.evidence/(name+'-spec.json');spec_path.write_bytes(w.canonical(spec))
        args=[sys.executable,'-B','-m','tools.container_watchdog','run','--spec',str(spec_path),'--output',str(out)]
        proc=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        observed=[];container=None
        try:
            if expected in ('EXEC_TIMEOUT','EXEC_CANCELLED'):
                limit=time.monotonic()+10
                while time.monotonic()<limit:
                    marker=out/'container.json'
                    if marker.exists():
                        container=json.loads(marker.read_text())
                        top=subprocess.run([*DOCKER,'top',container['id'],'-eo','pid'],capture_output=True,text=True,timeout=5)
                        if top.returncode==0:
                            observed=[v for pid in top.stdout.splitlines()[1:] if (v:=identity(int(pid.strip())))]
                            if len(observed)>=2:break
                    if proc.poll() is not None:break
                    time.sleep(.05)
                self.assertGreaterEqual(len(observed),2,'Did not observe parent and child on the host')
                (out/'host-processes-before.json').write_text(json.dumps(observed,indent=2)+'\n')
                if interrupt:proc.send_signal(signal.SIGINT)
            stdout,stderr=proc.communicate(timeout=30)
            (out/'host-cli.json').write_text(json.dumps({'argv':args,'returncode':proc.returncode,'stdout':stdout,'stderr':stderr},indent=2)+'\n')
            self.assertEqual(proc.returncode,exit_code,stdout+stderr)
            r=w.audit(out);self.assertEqual(r['status'],expected)
            self.assertTrue(r['termination_confirmed']);self.assertTrue(r['removed'])
            self.assertFalse(r['final_state']['Running']);self.assertEqual(r['final_state']['Pid'],0)
            raw=json.loads((out/'final-inspect.json').read_text());hc=raw['HostConfig']
            self.assertEqual(hc['Memory'],64<<20);self.assertEqual(hc['MemorySwap'],64<<20)
            self.assertEqual(hc['NanoCpus'],500000000);self.assertEqual(hc['PidsLimit'],32)
            self.assertEqual(hc['NetworkMode'],'none');self.assertTrue(hc['ReadonlyRootfs'])
            after=subprocess.run([*DOCKER,'inspect',r['container_id']],capture_output=True,text=True,timeout=5)
            (out/'host-absence.json').write_text(json.dumps({'returncode':after.returncode,'stdout':after.stdout,'stderr':after.stderr},indent=2)+'\n')
            self.assertEqual(after.returncode,1);self.assertIn('No such object',after.stderr)
            now=[identity(x['pid']) for x in observed]
            (out/'host-processes-after.json').write_text(json.dumps(now,indent=2)+'\n')
            for old,new in zip(observed,now):
                self.assertTrue(new is None or new['starttime']!=old['starttime'],(old,new))
            if expected=='EXEC_TIMEOUT':
                self.assertEqual(r['exit_code'],137)
                calls=json.loads((out/'docker-calls.json').read_text())
                self.assertTrue(any(c['argv'][3:]==['kill','--signal=KILL',r['container_id']] and c['returncode']==0 for c in calls))
            return r
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:proc.communicate(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.communicate(timeout=5)
            # Recovery only for this test's labelled container, never global prune.
            marker=out/'container.json'
            if marker.exists():
                owned=json.loads(marker.read_text())
                d=w.Docker()
                try:row=d.inspect(owned['id'],owned['run_id'])
                except w.DockerError:pass
                else:
                    d.call(['kill','--signal=KILL',row['Id']]);d.call(['rm',row['Id']])

    def test_success(self):
        self.run_case('success',['/bin/sh','-c','exit 0'],'EXEC_COMPLETED',0)

    def test_nonzero(self):
        r=self.run_case('nonzero',['/bin/sh','-c','exit 7'],'EXEC_NONZERO_EXIT',1)
        self.assertEqual(r['exit_code'],7)

    def test_timeout_kills_parent_and_child_then_writes_receipt(self):
        self.run_case('timeout',['/bin/sh','-c','trap "" TERM; sleep 120 & wait'],
                      'EXEC_TIMEOUT',124,timeout=3)

    def test_host_interrupt_cleans_container(self):
        self.run_case('interrupt',['/bin/sh','-c','trap "" TERM; sleep 120 & wait'],
                      'EXEC_CANCELLED',130,timeout=20,interrupt=True)

    @classmethod
    def tearDownClass(cls):
        after=subprocess.check_output([*DOCKER,'ps','-aq','--no-trunc'],text=True,timeout=5).splitlines()
        (cls.evidence/'containers-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if set(after)!=set(cls.original_names):
            raise AssertionError('Docker container inventory changed during isolated live checks')


if __name__=='__main__':unittest.main(verbosity=2)
