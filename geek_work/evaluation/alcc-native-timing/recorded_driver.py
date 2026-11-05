"""Recorded fixed study; historical build inputs required, no arbitrary CLI."""
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import geek_work_alcc_byte_preflight as corpus
import geek_work_exact_runner as supervisor
import knowledge

BOOTSTRAP='''import os,resource,sys
resource.setrlimit(resource.RLIMIT_AS,(2147483648,2147483648))
resource.setrlimit(resource.RLIMIT_CPU,(31,32))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
env={"PATH":"/usr/bin:/bin","LC_ALL":"C","LEAN_NUM_THREADS":"1","LEAN_ABORT_ON_PANIC":"1","LEAN_STACK_SIZE_KB":"65536","MIMALLOC_ARENA_RESERVE":"67108864"}
os.execve(sys.argv[1],sys.argv[1:],env)
'''

def validate(raw,expected,code,outer_ns):
    row=knowledge.strict_json(raw)
    if set(row)!={'schema','evidence_kind','code','read_ns','verify_ns'}:raise ValueError('fields')
    if row['schema']!='alcc-native-timing-1' or row['evidence_kind']!='compiled_execution':raise ValueError('protocol')
    if type(row['code']) is not int or row['code']!=code or code!=expected:raise ValueError('decision')
    for k in ('read_ns','verify_ns'):
        if type(row[k]) is not int or row[k]<0:raise ValueError('timing')
    if row['read_ns']+row['verify_ns']>outer_ns:raise ValueError('interval outside execution')
    return row

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    out=root/'.local/alcc-native-timing-evidence';build=out/'build';binary=build/'alcc-timed'
    meta=json.loads((build/'build.json').read_text());assert sha(binary)==meta['binary_sha256']
    assert sha(Path(__file__).parent/'AlccTimedMain.lean')==meta['source_sha256']
    pilot=out/'pilot';pilot.mkdir();inputs=pilot/'inputs';inputs.mkdir()
    cases,files=corpus.corpus()
    for name,raw in files.items():(inputs/name).write_bytes(raw)
    mapping={'residual_zero':0,'residual_nonzero':2,'PROBLEM_MISMATCH':3,'INVALID_FORMAT':3}
    frozen=dict(build=meta,contract_sha256=sha(Path(__file__).parent/'CONTRACT.md'),
                bootstrap=BOOTSTRAP,inputs={n:sha(inputs/n) for n in files},rounds=3)
    (pilot/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n');observations=[]
    for r in range(3):
        for c in (cases if r%2==0 else list(reversed(cases))):
            name=c['id'];command=[sys.executable,'-I','-B','-c',BOOTSTRAP,str(binary),str(inputs/(name+'.passport.json')),str(inputs/(name+'.certificate.json'))]
            process,logs=supervisor.supervise(command,pilot,wall_seconds=30,log_bytes=1048576)
            row=dict(case=name,round=r,process=process,command=command)
            for stream,raw in logs.items():(pilot/(str(r)+'-'+name+'-'+stream)).write_bytes(raw)
            observations.append(row);(pilot/'observations.json').write_text(json.dumps(observations,indent=2)+'\n')
            assert process['outcome']=='exited' and not logs['stderr.bin']
            # Supervisor reports floored milliseconds; allow its one-ms quantization.
            row['native']=validate(logs['stdout.bin'],mapping[c['expected']['status']],process['returncode'],(process['wall_time_ms']+1)*1000000)
            assert sha(binary)==meta['binary_sha256']
            assert all(sha(inputs/n)==h for n,h in frozen['inputs'].items())
            (pilot/'observations.json').write_text(json.dumps(observations,indent=2)+'\n')
            print(name,r,row['native'],flush=True)

if __name__=='__main__':main()
