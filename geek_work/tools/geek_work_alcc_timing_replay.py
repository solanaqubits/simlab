#!/usr/bin/env python3
"""Portable native ALCC timing replay; never executes a recorded command or binary."""
import argparse
import importlib.util
from pathlib import Path
import geek_work_alcc_byte_preflight as corpus
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

STUDY=Path(__file__).resolve().parents[1]/'evaluation/alcc-native-timing'
# Import only the installed trusted validator, not any received source/command.
spec=importlib.util.spec_from_file_location('installed_native_timing',STUDY/'recorded_driver.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
SCHEMA='geek-work-alcc-timing-replay-1'
MAX_TOTAL=8*1024*1024


def order():
    cases,_=corpus.corpus()
    return [(r,c) for r in range(3) for c in (cases if r%2==0 else list(reversed(cases)))]


def names():
    _,inputs=corpus.corpus()
    return {'frozen.json','observations.json'}|{'inputs/'+n for n in inputs}|{
        f'{r}-{c["id"]}-{s}.bin' for r,c in order() for s in ('stdout','stderr')}


def load(root,extra=()):
    required=names()|set(extra)
    archive.b.directory(root,{n for n in required if '/' not in n}|{'inputs'})
    archive.b.directory(root/'inputs',{n.split('/',1)[1] for n in required if n.startswith('inputs/')})
    files={};remaining=MAX_TOTAL
    for n in sorted(required):
        raw=m.read(root/n,min(1024*1024,remaining));remaining-=len(raw);files[n]=raw
    return files


def derive(files):
    frozen=knowledge.strict_json(files['frozen.json']);k.obj(frozen,'build contract_sha256 bootstrap inputs rounds')
    m.require(type(frozen['rounds']) is int and frozen['rounds']==3,'round count')
    m.require(frozen['bootstrap']==driver.BOOTSTRAP,'bootstrap binding')
    m.require(frozen['contract_sha256']==m.sha(m.read(STUDY/'CONTRACT.md')),'contract binding')
    fixed=knowledge.strict_json(m.read(STUDY/'RESULTS.json'))
    build=frozen['build'];k.obj(build,'commands lean_path binary_sha256 source_sha256 import_source_sha new_proofs')
    for key in ('binary_sha256','source_sha256','import_source_sha'):m.require(build[key]==fixed[key],'build binding')
    m.require(build['new_proofs'] is False,'proof promotion')
    commands=build['commands']
    m.require(type(commands) is list and len(commands)==3 and all(type(c) is list and 3<=len(c)<=4096 and all(type(x) is str for x in c) for c in commands),'build commands')
    m.require(type(build['lean_path']) is list and all(type(x) is str for x in build['lean_path']),'Lean path metadata')
    m.require(build['source_sha256']==m.sha(m.read(STUDY/'AlccTimedMain.lean')),'adapter binding')
    _,inputs=corpus.corpus()
    m.require(frozen['inputs']=={n:m.sha(raw) for n,raw in inputs.items()},'frozen input hashes')
    for n,raw in inputs.items():m.require(files['inputs/'+n]==raw,'fixed input bytes')
    rows=knowledge.strict_json(files['observations.json']);k.rows(rows,36,36)
    mapping={'residual_zero':0,'residual_nonzero':2,'PROBLEM_MISMATCH':3,'INVALID_FORMAT':3}
    samples={};prefix=None
    for row,(round_no,c) in zip(rows,order(),strict=True):
        k.obj(row,'case round process command native')
        m.require(type(row['round']) is int and (row['round'],row['case'])==(round_no,c['id']),'case/round order')
        process=row['process'];k.obj(process,'outcome returncode wall_time_ms error stdout_truncated stderr_truncated')
        m.require(process['outcome']=='exited' and type(process['returncode']) is int,'process outcome')
        m.require(type(process['wall_time_ms']) is int and process['wall_time_ms']>=0,'process time')
        m.require(process['error'] is None and process['stdout_truncated'] is False and process['stderr_truncated'] is False,'process incomplete')
        cmd=row['command'];m.require(type(cmd) is list and len(cmd)==8 and all(type(x) is str for x in cmd),'command shape')
        m.require(cmd[1:5]==['-I','-B','-c',driver.BOOTSTRAP],'command profile')
        if prefix is None:prefix=cmd[:6]
        m.require(cmd[:6]==prefix and cmd[5]==commands[2][2],'command changed')
        m.require(cmd[-2].endswith('/inputs/'+c['id']+'.passport.json') and cmd[-1].endswith('/inputs/'+c['id']+'.certificate.json'),'command inputs')
        stdout=files[f'{round_no}-{c["id"]}-stdout.bin'];stderr=files[f'{round_no}-{c["id"]}-stderr.bin']
        m.require(not stderr,'unexpected stderr')
        native=driver.validate(stdout,mapping[c['expected']['status']],process['returncode'],(process['wall_time_ms']+1)*1000000)
        m.require(m.encoded(native)==m.encoded(row['native']),'log/observation mismatch')
        if round_no>0:samples.setdefault(c['id'],[]).append(native)
    cases=[]
    for name,values in sorted(samples.items()):
        data={s:[v[s] for v in values] for s in ('read_ns','verify_ns')}
        cases.append(dict(case=name,code=values[0]['code'],samples=data,
                          medians={s:dict(numerator=sum(v),denominator=2) for s,v in data.items()}))
    return dict(schema='alcc-native-timing-pilot-1',processes=36,warmups=12,measured=24,cases=cases,
                binary_sha256=build['binary_sha256'],source_sha256=build['source_sha256'],
                import_source_sha=build['import_source_sha'],new_theorems=False,performance_qualified=False,
                independence_verified=False,peak_memory_bytes=None,monetary_cost=None)


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(v) for n,v in sorted(files.items())}))


def pack(pilot,frozen_sha,observations_sha,output):
    ops.outside(output,pilot)
    for h in (frozen_sha,observations_sha):k.digest(h)
    files=load(pilot)
    m.require(m.sha(files['frozen.json'])==frozen_sha and m.sha(files['observations.json'])==observations_sha,'source anchors')
    report=derive(files);files['report.json']=m.encoded(report)
    files['selection.json']=m.encoded(dict(frozen_sha256=frozen_sha,observations_sha256=observations_sha))
    m.require(sum(map(len,files.values()))<=MAX_TOTAL,'archive budget')
    meta=manifest(files);m.require(sum(map(len,files.values()))+len(meta)<=MAX_TOTAL,'archive with manifest budget')
    archive.write_tree(output,{**files,'manifest.json':meta})
    return dict(status='packed',manifest_sha256=m.sha(meta),observations=36)


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json',1024*1024);m.require(m.sha(meta)==anchor,'archive anchor')
    files=load(bundle,('report.json','selection.json','manifest.json'));files.pop('manifest.json')
    m.require(meta==manifest(files),'file hashes/manifest')
    selection=knowledge.strict_json(files['selection.json']);k.obj(selection,'frozen_sha256 observations_sha256')
    m.require(selection==dict(frozen_sha256=m.sha(files['frozen.json']),observations_sha256=m.sha(files['observations.json'])),'source selection')
    m.require(files['report.json']==m.encoded(derive(files)),'summary replay')
    return dict(status='reproduced',observations=36,subprocess_rerun=False,timing_authenticated=False,independence_verified=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('pack');q.add_argument('--pilot',type=Path,required=True);q.add_argument('--frozen-sha256',required=True);q.add_argument('--observations-sha256',required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        r=pack(a.pilot,a.frozen_sha256,a.observations_sha256,a.output) if a.action=='pack' else verify(a.bundle,a.sha256)
        print(m.encoded(r).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2

if __name__=='__main__':raise SystemExit(main())
