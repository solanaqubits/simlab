#!/usr/bin/env python3
"""Run one reviewed queued GitHub job in a disposable Docker runner."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

REPOS={'solanaqubits/simlab-private','solanaqubits/simlab'}


def require(ok, message):
    if not ok: raise ValueError(message)


def validate_run(run, sha, pr_number=None, main_mode=False):
    require(bool(re.fullmatch('[0-9a-f]{40}',sha)), 'expected SHA must be full hex')
    require(run['head_sha']==sha,'run SHA mismatch')
    require(not (main_mode and pr_number is not None),'main and PR modes are exclusive')
    if main_mode:
        require(run['event']=='push' and run['head_branch']=='main','expected main push event')
    elif pr_number is None:
        require(run['event']=='workflow_dispatch','PR mode must be explicitly selected')
    else:
        require(type(pr_number) is int and pr_number>0,'invalid PR number')
        require(run['event']=='pull_request','expected PR event')
        require(any(p['number']==pr_number and p['head']['sha']==sha for p in run.get('pull_requests',[])),
                'run is not associated with the expected PR head')
    require(run['actor']['login']=='solanaqubits' and run['triggering_actor']['login']=='solanaqubits',
            'run actor must be repository owner')
    # GitHub can expose a pending workflow while its exact runner job is queued.
    # This permits observation only; validate_jobs must still authorize a free job.
    require(run['status'] in ('pending','queued','in_progress'),'run is not active')


def validate_pr(pr, repo, number, sha):
    require(repo=='solanaqubits/simlab-private','PR mode is private-repository only')
    require(pr['number']==number and pr['state']=='open','PR is not open or number changed')
    require(pr['user']['login']=='solanaqubits' and pr['head']['user']['login']=='solanaqubits',
            'PR must belong to repository owner')
    require(pr['head']['repo']['full_name']==repo and pr['base']['repo']['full_name']==repo,
            'fork or foreign repository refused')
    require(pr['head']['sha']==sha,'PR head changed')
    require(pr['base']['ref']=='main' and bool(re.fullmatch('[0-9a-f]{40}',pr['base']['sha'])),
            'unexpected PR base')
    return pr['base']['sha']


def validate_main(ref, repo, sha):
    require(repo=='solanaqubits/simlab-private','main mode is private-repository only')
    require(ref['ref']=='refs/heads/main' and ref['object']['sha']==sha,'main advanced or ref changed')


def validate_jobs(jobs, label):
    require(bool(re.fullmatch('geek-work-[a-z0-9-]{1,64}',label)), 'invalid runner label')
    active=[j for j in jobs if j['status'] in ('queued','in_progress')]
    require(len(active)==1,'expected exactly one active job')
    require(active[0]['status']=='queued','job already assigned')
    require(set(active[0]['labels'])=={'self-hosted',label},'job labels mismatch')


def reconcile_jobs(fetch, output, job_id, name, sha, label, conclusion, sleep=time.sleep):
    """Retry only incomplete attribution; contradictory identity fails closed."""
    for attempt in range(1, 6):
        response=fetch()
        # Preserve the response BEFORE validation, including rejected observations.
        (output/f'jobs-observation-{attempt}.json').write_text(json.dumps(response,indent=2)+'\n')
        jobs=response['jobs']
        require(response.get('total_count',len(jobs))==len(jobs),'incomplete job listing')
        require(len(jobs)<=1,'unexpected additional jobs')
        if jobs:
            job=jobs[0]
            require(job.get('id')==job_id,'job identity changed')
            require(job.get('head_sha')==sha,'job SHA mismatch')
            require(set(job.get('labels',[]))=={'self-hosted',label},'job labels changed')
            require(job.get('runner_name') in (None,'',name),'job ran on another runner')
            if job.get('status')=='completed':
                require(job.get('conclusion')==conclusion,'job conclusion mismatch')
                if job.get('runner_name')==name:
                    return jobs,attempt
            else:
                require(job.get('status') in ('queued','in_progress'),'invalid job status')
        if attempt<5:sleep(2)
    raise TimeoutError('runner attribution remained incomplete after 5 observations')


def execute(repo, run_id, sha, label, image, output, timeout, pr_number=None, main_mode=False):
    require(repo in REPOS,'repository not allowlisted')
    require(type(run_id) is int and run_id>0,'invalid run ID')
    require(type(timeout) is int and 60<=timeout<=1200,'timeout must be 60..1200 seconds')
    output.mkdir(parents=True,exist_ok=False)
    def cmd(args, **kw):
        return subprocess.check_output(args,text=True,timeout=60,stderr=subprocess.PIPE,**kw)
    def api(path, method=None):
        return json.loads(cmd(['gh','api',*(['--method',method] if method else []),path]))
    prefix=f'repos/{repo}/actions';name='geek-work-once-'+uuid.uuid4().hex[:16]
    def runners():
        result=[]
        for page in range(1,21):
            response=api(f'{prefix}/runners?per_page=100&page={page}')
            result.extend(response['runners'])
            if len(result)>=response['total_count']:return result
            require(bool(response['runners']),'incomplete runner listing')
        raise ValueError('runner listing exceeds cleanup limit')
    receipt=dict(schema='geek-work-selfhosted-receipt-1',repository=repo,run_id=run_id,
                 expected_sha=sha,runner_name=name,status='starting',runner_removed=False,
                 container_removed=False,limits='Trusted manual revision; Docker and host trusted; GitHub egress allowed.')
    container_attempted=False
    try:
        run=api(f'{prefix}/runs/{run_id}')
        (output/'run-before.json').write_text(json.dumps(run,indent=2)+'\n')
        validate_run(run,sha,pr_number,main_mode)
        receipt['initial_run_status']=run['status']
        if main_mode:
            validate_main(api(f'repos/{repo}/git/ref/heads/main'),repo,sha)
            require(label==f'geek-work-main-{sha}','main label is not bound to SHA')
            receipt['source_ref']='refs/heads/main'
        if pr_number is not None:
            pr=api(f'repos/{repo}/pulls/{pr_number}')
            base_sha=validate_pr(pr,repo,pr_number,sha)
            require(label==f'geek-work-pr-{pr_number}-{sha}','PR label is not bound to head SHA')
            comparison=api(f'repos/{repo}/compare/{base_sha}...{sha}')
            require(comparison['merge_base_commit']['sha']==base_sha,'PR must include current main')
            receipt.update(pr_number=pr_number,pr_base_sha=base_sha)
            (output/'pr-before.json').write_text(json.dumps(pr,indent=2)+'\n')
        job_response=api(f'{prefix}/runs/{run_id}/jobs')
        (output/'jobs-before.json').write_text(json.dumps(job_response,indent=2)+'\n')
        jobs=job_response['jobs'];validate_jobs(jobs,label)
        require(job_response.get('total_count',len(jobs))==len(jobs),'incomplete job listing')
        require(len(jobs)==1,'expected exactly one job')
        require(jobs[0].get('head_sha')==sha,'job SHA mismatch')
        job_id=jobs[0]['id']
        receipt['job_id']=job_id
        receipt['image_id']=cmd(['docker','image','inspect',image,'--format','{{.Id}}']).strip()
        # No host filesystem/socket mounts; credentials for GH API stay on the host.
        container_attempted=True
        cmd(['docker','run','-d','--name',name,'--cpus','4','--memory','4g','--memory-swap','4g',
             '--pids-limit','512','--cap-drop','ALL','--security-opt','no-new-privileges',image,
             '-c',f'sleep {timeout}'])
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
        if main_mode:
            validate_main(api(f'repos/{repo}/git/ref/heads/main'),repo,sha)
        if pr_number is not None:
            fresh=api(f'repos/{repo}/pulls/{pr_number}')
            require(validate_pr(fresh,repo,pr_number,sha)==base_sha,'PR base changed during check')
            (output/'pr-after.json').write_text(json.dumps(fresh,indent=2)+'\n')
        (output/'run.json').write_text(json.dumps(run,indent=2)+'\n')
        jobs,observations=reconcile_jobs(lambda:api(f'{prefix}/runs/{run_id}/jobs'),
                                        output,job_id,name,sha,label,run['conclusion'])
        receipt['attribution_observations']=observations
        (output/'jobs.json').write_text(json.dumps(jobs,indent=2)+'\n')
        receipt.update(status=run['conclusion'],run_conclusion=run['conclusion'],url=run['html_url'])
        (output/'job.log').write_text(cmd(['gh','run','view',str(run_id),'--repo',repo,'--log']))
    except Exception as error:
        # Subprocess details can contain credentials; retain only the class, never command/output.
        receipt.update(status='error',error_class=type(error).__name__)
        if isinstance(error,(ValueError,TimeoutError)):receipt['reason']=str(error)
    finally:
        if container_attempted:
            # A timed-out Docker client may still have created the container.
            try:cmd(['docker','rm','-f',name])
            except Exception:pass
            try:
                remaining=cmd(['docker','ps','-a','--filter',f'name=^{name}$','--format','{{.ID}}']).strip()
                receipt['container_removed']=not bool(remaining)
                if remaining:receipt['cleanup_container_error']=True
            except Exception:receipt['cleanup_container_error']=True
        else:receipt['container_removed']=True
        try:
            for runner in runners():
                if runner['name']==name:
                    cmd(['gh','api','--method','DELETE',f"{prefix}/runners/{runner['id']}"])
            receipt['runner_removed']=not any(r['name']==name for r in runners())
        except Exception:receipt['cleanup_registration_error']=True
        if receipt['status']=='success' and not (receipt['container_removed'] and receipt['runner_removed']):
            receipt['status']='cleanup_failed'
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True);p.add_argument('--run-id',type=int,required=True)
    p.add_argument('--sha',required=True);p.add_argument('--label')
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--pr',type=int);mode.add_argument('--main',action='store_true')
    p.add_argument('--image',default='geek-work-runner:20261029');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=600);a=p.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError('operator termination')
    signal.signal(signal.SIGTERM, interrupted)
    # Serialize this host's operators; other GitHub writers remain outside this lock.
    with open('/tmp/geek-work-selfhosted.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        label=a.label or (f'geek-work-main-{a.sha}' if a.main else f'geek-work-pr-{a.pr}-{a.sha}' if a.pr is not None else 'geek-work-isolated')
        r=execute(a.repo,a.run_id,a.sha,label,a.image,a.output,a.timeout,a.pr,a.main)
    print(json.dumps(r,sort_keys=True))
    return 0 if r['status']=='success' and r['runner_removed'] and r['container_removed'] else 1


if __name__=='__main__':raise SystemExit(main())
