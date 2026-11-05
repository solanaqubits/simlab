#!/usr/bin/env python3
"""Supervise the trusted fixed arithmetic pilot; no arbitrary command execution CLI."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import time
import threading
import uuid

import geek_work_exact_pilot as pilot
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA = 'geek-work-exact-execution-1'
WALL_SECONDS = 30
MEMORY_BYTES = 268435456
LOG_BYTES = 65536  # per stream, preserve prefix and explicit truncation
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 128
BOOTSTRAP = '''import resource, sys
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.path.insert(0, sys.argv[1])
from geek_work_exact_runner import worker
sys.exit(worker(*sys.argv[2:]))
'''
LIMITS = dict(wall_time_seconds=WALL_SECONDS, address_space_bytes_per_process=MEMORY_BYTES,
              log_bytes_per_stream=LOG_BYTES, core_dump_bytes=0)


def runtime():
    exe = Path(sys.executable).resolve()
    # Bind all locally installed tool modules, not just the generator. These are
    # recorded identities, not a hermetic Python/stdlib/OS environment archive.
    return dict(python_version=platform.python_version(), implementation=platform.python_implementation(),
                executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), platform=platform.platform(),
                tool_sha256={p.name:m.sha(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))},
                bootstrap_sha256=m.sha(BOOTSTRAP.encode()))


def worker(plan, anchor, output, observation):
    import resource
    observed = dict(address_space=list(resource.getrlimit(resource.RLIMIT_AS)),
                    core_dump=list(resource.getrlimit(resource.RLIMIT_CORE)))
    m.require(observed == dict(address_space=[MEMORY_BYTES]*2, core_dump=[0,0]), 'worker limits not applied')
    request=knowledge.strict_json(m.read(Path(plan).parent/'request.json'))
    m.require(runtime()==request['runtime'], 'worker runtime changed after request capture')
    Path(observation).write_bytes(m.encoded(observed))
    try:
        result = pilot.run(Path(plan), anchor, Path(output))
        print(m.encoded(result).decode(), end='')
        return 0 if result['control_suite_passed'] else 3
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        print(m.encoded(dict(status='rejected', reason=str(exc))).decode(), end='')
        return 2


def supervise(command, cwd, wall_seconds=WALL_SECONDS, log_bytes=LOG_BYTES):
    """Internal trusted-process primitive. CLI never accepts a caller command."""
    start = time.monotonic_ns(); streams = {'stdout':bytearray(), 'stderr':bytearray()}
    truncated = dict(stdout=False, stderr=False); proc = None; reason = None; error = None
    sel = selectors.DefaultSelector()
    previous_term = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame): raise KeyboardInterrupt
    handles_term = threading.current_thread() is threading.main_thread()
    if handles_term: signal.signal(signal.SIGTERM, interrupted)
    def kill():
        if proc is not None:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
    try:
        proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            env={'PATH':os.defpath, 'LANG':'C.UTF-8'})
        for key in streams:
            pipe = getattr(proc,key); os.set_blocking(pipe.fileno(),False); sel.register(pipe,selectors.EVENT_READ,key)
        while sel.get_map() or proc.poll() is None:
            if (time.monotonic_ns()-start)/1e9 >= wall_seconds:
                reason = 'timed_out'; kill(); break
            for event, _ in sel.select(timeout=min(0.05, wall_seconds)):
                raw = os.read(event.fileobj.fileno(),8192); key=event.data
                if not raw: sel.unregister(event.fileobj); continue
                remaining = log_bytes-len(streams[key]); streams[key].extend(raw[:remaining])
                if len(raw)>remaining:
                    truncated[key]=True; reason='output_limit'; kill(); break
            if reason: break
        proc.wait()
        # A trusted worker normally has no descendants. Remove its process group
        # even after leader exit. This is not containment of hostile setsid/fork code.
        kill()
        if reason is None: reason='signalled' if proc.returncode<0 else 'exited'
    except OSError as exc:
        reason='launch_failed' if proc is None else 'supervisor_error'; error=str(exc)[:4000]; kill()
    except KeyboardInterrupt:
        reason='interrupted'; kill()
    finally:
        if proc is not None:
            proc.wait()
            for key in streams: getattr(proc,key).close()
        sel.close()
        if handles_term: signal.signal(signal.SIGTERM, previous_term)
    return dict(outcome=reason,returncode=proc.returncode if proc else None,
                wall_time_ms=(time.monotonic_ns()-start)//1000000,error=error,
                stdout_truncated=truncated['stdout'],stderr_truncated=truncated['stderr']), {n+'.bin':bytes(v) for n,v in streams.items()}


def scan_layout(root):
    """Bound enumeration before sorting or reading payloads; trusted stable paths."""
    root=Path(root)
    m.require(root.is_dir() and not root.is_symlink(),'real archive directory required')
    pending=[root];files=[];dirs=[]
    while pending:
        folder=pending.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                m.require(not entry.is_symlink(),'symlink in execution archive')
                path=folder/entry.name;name=path.relative_to(root).as_posix();k.path_name(name)
                if entry.is_dir(follow_symlinks=False):
                    m.require(len(dirs)<MAX_FILES,'directory count')
                    dirs.append(name);pending.append(path)
                else:
                    m.require(entry.is_file(follow_symlinks=False),'regular archive file required')
                    # One final root manifest is not a payload file; nested manifests are.
                    if name=='manifest.json':continue
                    m.require(len(files)<MAX_FILES,'execution file count')
                    files.append(name)
    return sorted(files),sorted(dirs)


def inventory(root):
    names,_=scan_layout(root);files={};total=0
    for name in names:
        raw=m.read(root/name,min(k.MAX_TOTAL,MAX_TOTAL-total));total+=len(raw)
        m.require(total<=MAX_TOTAL,'execution archive limit');files[name]=raw
    return files


def directories(root):
    return scan_layout(root)[1]


def exact_layout(root, names, dirs):
    m.require(type(dirs) is list and len(dirs)<=MAX_FILES and dirs==sorted(set(dirs)), 'directory list')
    expected={'.':set()}
    for d in dirs:
        k.path_name(d);m.require(d in ('plan','run') or d.startswith(('plan/','run/')), 'unexpected execution directory');expected[d]=set()
    for name in list(names)+dirs:
        k.path_name(name);path=Path(name);parent=path.parent.as_posix()
        m.require(parent in expected, 'missing directory entry');expected[parent].add(path.name)
    for d,children in expected.items():archive.b.directory(root/d,children)


def result_from(bundle, process):
    if process['outcome']!='exited' or process['returncode'] not in (0,3):
        return dict(status=process['outcome'] if process['outcome']!='exited' else 'execution_failed',
                    run_manifest_sha256=None,control_suite_passed=None)
    try:
        anchor=m.sha(m.read(bundle/'run/manifest.json'));result=pilot.verify(bundle/'run',anchor)
        m.require(process['returncode']==(0 if result['control_suite_passed'] else 3),'worker verdict/exit disagreement')
        m.require(m.read(bundle/'worker-limits.json') ==
                  m.encoded(dict(address_space=[MEMORY_BYTES]*2,core_dump=[0,0])),'worker limit observation missing')
        # Ensure nested result belongs to this exact parent, not an unrelated valid pilot.
        request=knowledge.strict_json(m.read(bundle/'request.json'))
        m.require(m.sha(m.read(bundle/'run/plan/manifest.json'))==request['plan_sha256'],'run parent mismatch')
        return dict(status=result['status'],run_manifest_sha256=anchor,control_suite_passed=result['control_suite_passed'])
    except (ValueError,OSError,KeyError,TypeError):
        return dict(status='artifact_invalid',run_manifest_sha256=None,control_suite_passed=None)


def receipt(request,process,result):
    return dict(schema=SCHEMA,request_sha256=m.sha(m.encoded(request)),process=process,result=result,
                execution_independently_verified=False,scientific_verification=False,
                token_usage=None,monetary_cost=None,peak_memory_bytes=None,
                limits='Trusted local worker only; RLIMIT_AS is per-process virtual address space, not aggregate RSS. Wall timeout covers child startup/work, not parent preflight/replay. Receipt integrity is not proof of execution, independence or a theorem.')


def run(plan,anchor,output):
    m.require(sys.platform=='linux','Linux RLIMIT_AS/process-group profile required')
    ops.outside(output,plan);parent=pilot.plan_bytes(plan,anchor)
    request=dict(schema=SCHEMA,attempt_id=uuid.uuid4().hex,plan_sha256=anchor,profile=pilot.PROFILE,
                 limits=LIMITS,runtime=runtime())
    archive.write_tree(output,{'request.json':m.encoded(request),**{'plan/'+n:b for n,b in parent.items()}})
    # Presence of request without a final manifest means incomplete, never success.
    command=[sys.executable,'-I','-B','-c',BOOTSTRAP,str(Path(__file__).resolve().parent),
             str((output/'plan').resolve()),anchor,str((output/'run').resolve()),str((output/'worker-limits.json').resolve())]
    process,logs=supervise(command,output.resolve())
    for name,raw in logs.items():(output/name).write_bytes(raw)
    final=receipt(request,process,result_from(output,process));(output/'receipt.json').write_bytes(m.encoded(final))
    files=inventory(output);meta=m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()},directories=directories(output)))
    (output/'manifest.json').write_bytes(meta)
    return dict(status=final['result']['status'],manifest_sha256=m.sha(meta),process_outcome=process['outcome'])


def validate_process(p,files):
    k.obj(p,'outcome returncode wall_time_ms error stdout_truncated stderr_truncated')
    m.require(p['outcome'] in ('exited','signalled','timed_out','output_limit','launch_failed','supervisor_error','interrupted'),'process outcome')
    m.require(type(p['wall_time_ms']) is int and p['wall_time_ms']>=0,'elapsed time')
    m.require(p['returncode'] is None or type(p['returncode']) is int,'return code')
    m.require(p['error'] is None or type(p['error']) is str and len(p['error'])<=4000,'process error')
    if p['outcome']=='exited':m.require(p['returncode'] is not None and p['returncode']>=0,'exit code')
    if p['outcome']=='signalled':m.require(p['returncode'] is not None and p['returncode']<0,'signal code')
    if p['outcome']=='launch_failed':m.require(p['returncode'] is None and p['error'] is not None,'launch error')
    for key in ('stdout','stderr'):
        m.require(type(p[key+'_truncated']) is bool,'truncation flag')
        m.require(len(files[key+'.bin'])<=LOG_BYTES,'log bound')
        if p[key+'_truncated']:m.require(len(files[key+'.bin'])==LOG_BYTES,'truncated prefix length')
    if p['outcome']=='output_limit':m.require(p['stdout_truncated'] or p['stderr_truncated'],'output limit flag')


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'execution anchor mismatch')
    manifest=knowledge.strict_json(meta);k.obj(manifest,'schema files directories');m.require(manifest['schema']==SCHEMA,'schema')
    m.require(type(manifest['files']) is dict and len(manifest['files'])<=MAX_FILES,'file count')
    for n,h in manifest['files'].items():k.path_name(n);k.digest(h)
    exact_layout(bundle,set(manifest['files'])|{'manifest.json'},manifest['directories'])
    files=inventory(bundle);m.require({n:m.sha(b) for n,b in files.items()}==manifest['files'],'file hashes')
    required={'request.json','receipt.json','stdout.bin','stderr.bin'}
    m.require(required<=set(files),'incomplete execution')
    m.require(all(n in required|{'worker-limits.json'} or n.startswith(('plan/','run/')) for n in files),'unexpected execution file')
    req=knowledge.strict_json(files['request.json']);k.obj(req,'schema attempt_id plan_sha256 profile limits runtime')
    m.require(req['schema']==SCHEMA and req['profile']==pilot.PROFILE and m.encoded(req['limits'])==m.encoded(LIMITS),'request profile/limits')
    m.require(type(req['attempt_id']) is str and len(req['attempt_id'])==32 and all(c in '0123456789abcdef' for c in req['attempt_id']),'attempt id')
    k.digest(req['plan_sha256']);pilot.plan_bytes(bundle/'plan',req['plan_sha256'])
    rt=req['runtime'];k.obj(rt,'python_version implementation executable_sha256 platform tool_sha256 bootstrap_sha256')
    for field in ('python_version','implementation','platform'):k.text(rt[field])
    for field in ('executable_sha256','bootstrap_sha256'):k.digest(rt[field])
    m.require(rt['bootstrap_sha256']==m.sha(BOOTSTRAP.encode()),'bootstrap binding')
    m.require(type(rt['tool_sha256']) is dict and 1<=len(rt['tool_sha256'])<=512,'tool bindings')
    for name,h in rt['tool_sha256'].items():k.path_name(name);k.digest(h)
    for module in (Path(pilot.__file__), Path(pilot.generator.__file__)):
        m.require(rt['tool_sha256'].get(module.name)==m.sha(module.read_bytes()),'pilot runtime binding')
    m.require('geek_work_exact_runner.py' in rt['tool_sha256'],'supervisor binding required')
    recorded=knowledge.strict_json(files['receipt.json']);process=recorded['process'];validate_process(process,files)
    expected=receipt(req,process,result_from(bundle,process))
    m.require(files['receipt.json']==m.encoded(expected),'receipt mismatch')
    return dict(status=expected['result']['status'],integrity_reproduced=True,subprocess_rerun=False,
                execution_independently_verified=False,os_limits_reenforced_here=False)



def inspect_execution(bundle,anchor=None):
    """Read-only inventory of a quiescent directory; never infer process liveness."""
    m.require(bundle.is_dir() and not bundle.is_symlink(),'regular execution directory required')
    files=inventory(bundle);dirs=directories(bundle)
    allowed={'request.json','receipt.json','stdout.bin','stderr.bin','worker-limits.json'}
    m.require(all(n in allowed or n.startswith(('plan/','run/')) for n in files),'unexpected execution file')
    has_manifest=(bundle/'manifest.json').exists()
    exact_layout(bundle,set(files)|({'manifest.json'} if has_manifest else set()),dirs)
    request=None
    if 'request.json' in files:
        request=knowledge.strict_json(files['request.json'])
        k.obj(request,'schema attempt_id plan_sha256 profile limits runtime')
        m.require(request['schema']==SCHEMA and request['profile']==pilot.PROFILE,'request identity schema')
        identity=request['attempt_id']
        m.require(type(identity) is str and len(identity)==32 and all(c in '0123456789abcdef' for c in identity),'attempt id')
        k.digest(request['plan_sha256'])
    observed_anchor=m.sha(m.read(bundle/'manifest.json')) if has_manifest else None
    state='sealed_unverified' if has_manifest else 'incomplete' if request else 'unrecognized'
    result=None;integrity=False
    if anchor is not None:
        # Never downgrade a missing/wrong expected completion anchor into a success.
        checked=verify(bundle,anchor);state='verified_complete';result=checked['status'];integrity=True
    return dict(schema='geek-work-execution-inspection-1',state=state,
        attempt_id=request['attempt_id'] if request else None,
        request_sha256=m.sha(files['request.json']) if request else None,
        plan_sha256=request['plan_sha256'] if request else None,
        observed_manifest_sha256=observed_anchor,external_manifest_checked=integrity,
        result_status=result,process_started=None,process_running=None,
        execution_independently_verified=False,source_modified=False,
        files=[dict(path=n,bytes=len(b),sha256=m.sha(b)) for n,b in sorted(files.items())],
        directories=dirs,receipt_present='receipt.json' in files,
        logs_present={n:n+'.bin' in files for n in ('stdout','stderr')},
        limits='Non-atomic inventory of trusted stable paths. Request identity alone does not validate its runtime, plan or execution. Without an external final anchor no result is accepted, even if a receipt claims success. No PID lookup, kill, resume, retry, cleanup, resealing or automatic recovery.')


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for name in ('run','verify'):
        q=s.add_parser(name);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if name=='run':q.add_argument('--output',type=Path,required=True)
    q=s.add_parser('inspect');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',help='Optional externally retained final manifest SHA')
    a=p.parse_args()
    try:
        if a.action=='inspect':
            result=inspect_execution(a.bundle,a.sha256);print(m.encoded(result).decode(),end='')
            return 0 if result['result_status']=='controls_observed' else 3 if result['result_status']=='control_pattern_mismatch' else 4
        result=run(a.bundle,a.sha256,a.output) if a.action=='run' else verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='')
        return 0 if result['status']=='controls_observed' else 3 if result['status']=='control_pattern_mismatch' else 4
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
