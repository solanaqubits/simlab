#!/usr/bin/env python3
"""Run one reviewed queued GitHub job in a disposable Docker runner."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

REPOS={'solanaqubits/simlab-private','solanaqubits/simlab'}


def require(ok, message):
    if not ok: raise ValueError(message)


def validate_run(run, sha):
    require(bool(re.fullmatch('[0-9a-f]{40}',sha)), 'expected SHA must be full hex')
    require(run['head_sha']==sha,'run SHA mismatch')
    require(run['event']=='workflow_dispatch','only manual reviewed runs are allowed')
    require(run['actor']['login']=='solanaqubits' and run['triggering_actor']['login']=='solanaqubits',
            'run actor must be repository owner')
    require(run['status'] in ('queued','in_progress'),'run is not active')


def validate_jobs(jobs, label):
    require(bool(re.fullmatch('geek-work-[a-z0-9-]{1,64}',label)), 'invalid runner label')
    active=[j for j in jobs if j['status'] in ('queued','in_progress')]
    require(len(active)==1,'expected exactly one active job')
    require(active[0]['status']=='queued','job already assigned')
    require(set(active[0]['labels'])=={'self-hosted',label},'job labels mismatch')


def execute(repo, run_id, sha, label, image, output, timeout):
    require(repo in REPOS,'repository not allowlisted')
    require(type(run_id) is int and run_id>0,'invalid run ID')
    require(type(timeout) is int and 60<=timeout<=1200,'timeout must be 60..1200 seconds')
    output.mkdir(parents=True,exist_ok=False)
    def cmd(args, **kw):
        return subprocess.check_output(args,text=True,timeout=60,stderr=subprocess.PIPE,**kw)
    def api(path, method=None):
        return json.loads(cmd(['gh','api',*(['--method',method] if method else []),path]))
    prefix=f'repos/{repo}/actions';name='geek-work-once-'+uuid.uuid4().hex[:16]
    receipt=dict(schema='geek-work-selfhosted-receipt-1',repository=repo,run_id=run_id,
                 expected_sha=sha,runner_name=name,status='starting',runner_removed=False,
                 container_removed=False,limits='Trusted manual revision; Docker and host trusted; GitHub egress allowed.')
    created=False
    try:
        run=api(f'{prefix}/runs/{run_id}');validate_run(run,sha)
        jobs=api(f'{prefix}/runs/{run_id}/jobs')['jobs'];validate_jobs(jobs,label)
        receipt['image_id']=cmd(['docker','image','inspect',image,'--format','{{.Id}}']).strip()
        # No host filesystem/socket mounts; credentials for GH API stay on the host.
        cmd(['docker','run','-d','--name',name,'--cpus','4','--memory','4g','--memory-swap','4g',
             '--pids-limit','512','--cap-drop','ALL','--security-opt','no-new-privileges',image,
             '-c',f'sleep {timeout}']);created=True
        token=api(f'{prefix}/runners/registration-token','POST')['token']
        script=('read -r registration_token; ./config.sh --unattended --url https://github.com/'+repo+
                ' --token "$registration_token" --name '+name+' --labels '+label+
                ' --ephemeral --disableupdate --work _work')
        cmd(['docker','exec','-i',name,'bash','-c',script],input=token+'\n');del token
        cmd(['docker','exec','-d',name,'bash','-c','./run.sh > /tmp/runner-job.log 2>&1'])
        deadline=time.monotonic()+timeout-10
        while time.monotonic()<deadline:
            run=api(f'{prefix}/runs/{run_id}');require(run['head_sha']==sha,'run SHA changed')
            if run['status']=='completed':break
            time.sleep(3)
        else: raise TimeoutError('run exceeded host deadline')
        (output/'run.json').write_text(json.dumps(run,indent=2)+'\n')
        jobs=api(f'{prefix}/runs/{run_id}/jobs')['jobs']
        require(len(jobs)==1 and jobs[0].get('runner_name')==name,'job ran on another runner')
        (output/'jobs.json').write_text(json.dumps(jobs,indent=2)+'\n')
        receipt.update(status=run['conclusion'],url=run['html_url'])
        (output/'job.log').write_text(cmd(['gh','run','view',str(run_id),'--repo',repo,'--log']))
    except Exception as error:
        # Subprocess details can contain credentials; retain only the class, never command/output.
        receipt.update(status='error',error_class=type(error).__name__)
        if isinstance(error,(ValueError,TimeoutError)):receipt['reason']=str(error)
    finally:
        if created:
            try:cmd(['docker','rm','-f',name]);receipt['container_removed']=True
            except Exception:receipt['cleanup_container_error']=True
        else:receipt['container_removed']=True
        try:
            for runner in api(f'{prefix}/runners')['runners']:
                if runner['name']==name:
                    cmd(['gh','api','--method','DELETE',f"{prefix}/runners/{runner['id']}"])
            receipt['runner_removed']=not any(r['name']==name for r in api(f'{prefix}/runners')['runners'])
        except Exception:receipt['cleanup_registration_error']=True
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True);p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--sha',required=True);p.add_argument('--label',default='geek-work-isolated')
    p.add_argument('--image',default='geek-work-runner:20261029');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=600);a=p.parse_args()
    # Serialize this host's operators; other GitHub writers remain outside this lock.
    with open('/tmp/geek-work-selfhosted.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        r=execute(a.repo,a.run_id,a.sha,a.label,a.image,a.output,a.timeout)
    print(json.dumps(r,sort_keys=True))
    return 0 if r['status']=='success' and r['runner_removed'] and r['container_removed'] else 1


if __name__=='__main__':raise SystemExit(main())
