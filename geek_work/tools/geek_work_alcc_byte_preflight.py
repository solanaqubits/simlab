#!/usr/bin/env python3
"""Fixed ALCC Python byte preflight; not Lean verification or full CLI throughput."""
import argparse
from dataclasses import asdict
from pathlib import Path
import platform
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alcc
import geek_work_alcc_tasks as tasks
import geek_work_exact_runner as supervisor
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import knowledge

SCHEMA = 'geek-work-alcc-byte-preflight-1'
ROUNDS = 5
LIMITS = alcc.Limits(arithmetic_seconds=1)
BOOTSTRAP = '''import resource,sys
resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
sys.path.insert(0,sys.argv[1])
from geek_work_alcc_byte_preflight import worker
sys.exit(worker(sys.argv[2]))
'''
STAGES = ('bind_ns', 'residual_ns', 'serialize_ns', 'total_ns')


def bindings():
    paths = [Path(__file__), Path(alcc.__file__), Path(tasks.__file__),
             Path(supervisor.__file__), Path(m.__file__), Path(k.__file__),
             Path(archive.__file__), Path(archive.b.__file__), Path(knowledge.__file__),
             Path(__file__).resolve().parents[1]/'evaluation/alcc-byte-preflight/CONTRACT.md']
    return {p.name: m.sha(p.read_bytes()) for p in paths}


def corpus():
    def poly(terms):
        return [dict(powers=e, coeff=[int(a), int(b)]) for e, a, b in tasks.normalized(terms)]
    cases = []; files = {}
    def add(name, passport, certificate, expected):
        cases.append(dict(id=name, expected=expected))
        files[name+'.passport.json'] = passport
        files[name+'.certificate.json'] = certificate
    for c in tasks.corpus()['cases']:
        p = dict(format_version=alcc.VERSION, profile_id=alcc.PROFILE,
                 variables=['x','y','z'], hypotheses=[dict(id=f'h{i}', poly=poly(h))
                 for i,h in enumerate(c['hypotheses'])], target=dict(poly=poly(c['target'])))
        p['problem_id'] = alcc.passport_id(p)
        cert = dict(format_version=alcc.VERSION, profile_id=alcc.PROFILE,
                    problem_id=p['problem_id'], multipliers=[dict(hypothesis_id=f'h{i}',poly=poly(q))
                    for i,q in enumerate(c['multipliers'])])
        expected = tasks.oracle(c)
        add(c['id'], alcc.canonical(p), alcc.canonical(cert),
            dict(status='residual_zero' if not expected else 'residual_nonzero', residual=expected))
    source = 'identity-x'
    p = files[source+'.passport.json']; c = files[source+'.certificate.json']
    bad = knowledge.strict_json(c); bad['problem_id'] = '0'*64
    add('wrong-problem', p, alcc.canonical(bad), dict(status='PROBLEM_MISMATCH',residual=None))
    add('noncanonical-json', p, c+b'\n', dict(status='INVALID_FORMAT',residual=None))
    bad = knowledge.strict_json(c); bad['multipliers'][0]['poly'][0]['coeff'] = [2,2]
    add('unreduced-rational',p,alcc.canonical(bad),dict(status='INVALID_FORMAT',residual=None))
    return cases, files


def evaluate(passport, certificate):
    start = time.perf_counter_ns(); bind_ns = residual_ns = None
    try:
        t = time.perf_counter_ns(); task = alcc.bind(passport,certificate,LIMITS)
        bind_ns = time.perf_counter_ns()-t
        t = time.perf_counter_ns(); r = alcc.residual(task,LIMITS)
        residual_ns = time.perf_counter_ns()-t
        result = dict(status='residual_zero' if not r else 'residual_nonzero',
                      residual=[[list(e),str(v.numerator),str(v.denominator)]
                                for e,v in sorted(r.items(),reverse=True)])
    except alcc.Refusal as exc:
        if bind_ns is None: bind_ns = time.perf_counter_ns()-t
        else: residual_ns = time.perf_counter_ns()-t
        result = dict(status=exc.status,residual=None)
    t = time.perf_counter_ns(); raw = alcc.canonical(result)
    serialize_ns = time.perf_counter_ns()-t
    return dict(result=result, result_sha256=m.sha(raw), bind_ns=bind_ns,
                residual_ns=residual_ns, serialize_ns=serialize_ns,
                total_ns=time.perf_counter_ns()-start)


def order(cases):
    return [(r,c) for r in range(ROUNDS) for c in (cases if r%2==0 else list(reversed(cases)))]


def validate_rows(raw):
    cases,_ = corpus(); lines = raw.splitlines()
    m.require(len(lines)==len(cases)*ROUNDS,'complete observation row count')
    samples = {c['id']:{s:[] for s in STAGES} for c in cases}
    for line,(round_no,c) in zip(lines,order(cases),strict=True):
        row = knowledge.strict_json(line)
        k.obj(row,'case round result result_sha256 bind_ns residual_ns serialize_ns total_ns')
        m.require(type(row['round']) is int and (row['round'],row['case'])==(round_no,c['id']),'observation order')
        # Canonical bytes distinguish bool/int and reject unexpected result fields.
        m.require(m.encoded(row['result'])==m.encoded(c['expected']),'full residual or refusal mismatch')
        m.require(row['result_sha256']==m.sha(alcc.canonical(c['expected'])),'serialized result hash')
        for s in STAGES:
            nullable = s=='residual_ns' and c['expected']['residual'] is None
            value = row[s]
            m.require(value is None if nullable else type(value) is int and 0<=value<=30_000_000_000,'stage time')
            if round_no>0: samples[c['id']][s].append(value)
        m.require(row['total_ns']>=sum(row[s] or 0 for s in STAGES[:-1]),'inconsistent total time')
    def median(values):
        if all(v is None for v in values): return None
        v=sorted(values);return dict(numerator=v[1]+v[2],denominator=2)
    return dict(status='EXPECTED_PREFLIGHT_CONTROLS',observations=len(lines),warmup_rounds=1,
                measured_observations=len(cases)*(ROUNDS-1),
                cases=[dict(id=c['id'],expected=c['expected'],samples_ns=samples[c['id']],
                            median_ns={s:median(v) for s,v in samples[c['id']].items()}) for c in cases],
                lean_verified=False,independence_verified=False,performance_qualified=False,
                full_cli_throughput_measured=False,token_usage=None,monetary_cost=None,peak_memory_bytes=None)


def request():
    cases,files=corpus()
    # alcc.Limits has legacy floating defaults for unrelated Lean execution fields.
    limits={n:v for n,v in asdict(LIMITS).items() if not n.startswith('lean_')}
    return dict(schema=SCHEMA,attempt_id=uuid.uuid4().hex,bindings=bindings(),
                input_sha256={n:m.sha(b) for n,b in files.items()},rounds=ROUNDS,
                expected_cases=cases,arithmetic_limits=limits,process_limits=supervisor.LIMITS,
                bootstrap_sha256=m.sha(BOOTSTRAP.encode()),python_version=platform.python_version(),
                python_executable_sha256=m.sha(Path(sys.executable).resolve().read_bytes()))


def check_request(req,files):
    expected=request()
    k.obj(req,' '.join(expected))
    for field in expected:
        if field not in ('attempt_id','python_version','python_executable_sha256'):
            m.require(m.encoded(req[field])==m.encoded(expected[field]),'request binding: '+field)
    m.require(type(req['attempt_id']) is str and len(req['attempt_id'])==32 and
              all(c in '0123456789abcdef' for c in req['attempt_id']),'attempt id')
    k.text(req['python_version']);k.digest(req['python_executable_sha256'])
    _,fixed=corpus()
    for name,raw in fixed.items(): m.require(files[name]==raw,'fixed input mismatch')


def worker(root):
    import resource
    root=Path(root);cases,fixed=corpus()
    files={n:m.read(root/n) for n in fixed}
    req=knowledge.strict_json(m.read(root/'request.json'));check_request(req,files)
    m.require(platform.python_version()==req['python_version'] and
              m.sha(Path(sys.executable).resolve().read_bytes())==req['python_executable_sha256'],
              'worker Python changed')
    m.require(resource.getrlimit(resource.RLIMIT_AS)==(supervisor.MEMORY_BYTES,)*2 and
              resource.getrlimit(resource.RLIMIT_CORE)==(0,0),'worker resource limits')
    for round_no,c in order(cases):
        result=evaluate(files[c['id']+'.passport.json'],files[c['id']+'.certificate.json'])
        print(alcc.canonical(dict(case=c['id'],round=round_no,**result)).decode(),flush=True)
        if result['result']!=c['expected']:return 3
    return 0


def derive(process,logs):
    supervisor.validate_process(process,logs)
    if process['outcome']=='exited' and process['returncode']==3:
        return dict(status='unexpected_control',observations_accepted=False)
    if process['outcome']!='exited' or process['returncode']!=0:
        return dict(status='operational_failure',observations_accepted=False)
    try: return validate_rows(logs['stdout.bin'])
    except (ValueError,TypeError,KeyError,RecursionError,UnicodeError):
        return dict(status='invalid_observations',observations_accepted=False)


def run(output):
    m.require(sys.platform=='linux','Linux profile required')
    _,files=corpus();req=request();files['request.json']=m.encoded(req)
    archive.write_tree(output,files)
    command=[sys.executable,'-I','-B','-c',BOOTSTRAP,str(Path(__file__).parent.resolve()),str(output.resolve())]
    process,logs=supervisor.supervise(command,output.resolve())
    report=derive(process,logs)
    files.update(logs);files['process.json']=m.encoded(process);files['report.json']=m.encoded(report)
    for name in ('stdout.bin','stderr.bin','process.json','report.json'):(output/name).write_bytes(files[name])
    meta=m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()}))
    (output/'manifest.json').write_bytes(meta)
    return dict(status=report['status'],manifest_sha256=m.sha(meta))


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'external manifest anchor')
    manifest=knowledge.strict_json(meta);k.obj(manifest,'schema files')
    m.require(manifest['schema']==SCHEMA,'schema')
    _,fixed=corpus();names=set(fixed)|{'request.json','process.json','report.json','stdout.bin','stderr.bin'}
    m.require(type(manifest['files']) is dict and set(manifest['files'])==names,'manifest files')
    archive.b.directory(bundle,names|{'manifest.json'})
    files={n:m.read(bundle/n,supervisor.LOG_BYTES if n.endswith('.bin') else m.MAX_ARTIFACT) for n in names}
    m.require({n:m.sha(b) for n,b in files.items()}==manifest['files'],'file hashes')
    check_request(knowledge.strict_json(files['request.json']),files)
    report=derive(knowledge.strict_json(files['process.json']),files)
    m.require(files['report.json']==m.encoded(report),'report reproduction')
    return dict(status=report['status'],integrity_reproduced=True,subprocess_rerun=False,
                timing_authenticated=False,execution_independently_verified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('run');q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        result=run(a.output) if a.action=='run' else verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0 if result['status']=='EXPECTED_PREFLIGHT_CONTROLS' else 4
    except (ValueError,OSError,KeyError,TypeError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
