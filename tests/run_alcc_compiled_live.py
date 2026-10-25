"""Bounded native integration matrix; expectations fixed independently of Lean output."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from tools.alcc_compiled_runner import load_pin, strict_json, verify


def wire(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def term(num, den, powers):
    return {'coeff': [num, den], 'powers': powers}


def task(variables, hypotheses, target, multipliers):
    header = {'format_version': '1.0', 'profile_id': 'ALCC-JSON-1'}
    p = dict(header, variables=variables, hypotheses=[{'id': f'h{i}', 'poly': x} for i, x in enumerate(hypotheses)], target={'poly': target})
    p['problem_id'] = hashlib.sha256(wire(p)).hexdigest()
    c = dict(header, problem_id=p['problem_id'], multipliers=[{'hypothesis_id': f'h{i}', 'poly': x} for i, x in enumerate(multipliers)])
    return p, c


def cases():
    reference = task(['x'], [[term(1,1,[1]), term(-1,1,[0])]],
                     [term(1,1,[2]), term(-1,1,[0])], [[term(1,1,[1]), term(1,1,[0])]])
    rows = []
    def add(name, pair, expected):
        rows.append((name, wire(pair[0]), wire(pair[1]), expected))
    add('difference_of_squares', reference, 'VERIFIED_SUCCESS')
    add('empty', task([], [], [], []), 'VERIFIED_SUCCESS')
    add('rational', task(['z','a'], [[term(-1,2,[0,1])]], [term(3,4,[0,1])], [[term(-3,2,[0,0])]]), 'VERIFIED_SUCCESS')
    p,c = deepcopy(reference); c['multipliers'][0]['poly'][0]['coeff'] = [2,1]
    add('wrong_multiplier', (p,c), 'IDENTITY_MISMATCH')
    add('nonzero_without_hypotheses', task(['x'], [], [term(1,1,[1])], []), 'IDENTITY_MISMATCH')
    for name, edit in [
        ('reducible_fraction', lambda p,c: c['multipliers'][0]['poly'][0].update(coeff=[2,4])),
        ('zero_coefficient', lambda p,c: c['multipliers'][0]['poly'][0].update(coeff=[0,1])),
        ('wrong_hypothesis_id', lambda p,c: c['multipliers'][0].update(hypothesis_id='other')),
        ('missing_multiplier', lambda p,c: c.update(multipliers=[])),
        ('forged_hash', lambda p,c: (p.update(problem_id='0'*64),c.update(problem_id='0'*64))),
        ('foreign_certificate', lambda p,c: c.update(problem_id='f'*64)),
        ('changed_target', lambda p,c: p['target']['poly'][0].update(coeff=[2,1])),
    ]:
        p,c=deepcopy(reference); edit(p,c); add(name,(p,c),'DECODE_ERROR')
    bp,bc = map(wire, reference)
    rows += [('whitespace', b' '+bp, bc, 'DECODE_ERROR'),
             ('non_ascii', bp+b'\xff', bc, 'DECODE_ERROR'),
             ('numeric_float', bp, bc.replace(b'[1,1]', b'[1.0,1]',1), 'DECODE_ERROR')]
    return rows


def main(pin, output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, bp, bc, expected in cases():
        fixture = output / name
        fixture.mkdir()
        pp, cp = fixture/'passport.json', fixture/'certificate.json'
        pp.write_bytes(bp); cp.write_bytes(bc)
        receipt = verify(pp,cp,fixture,pin)
        passed = receipt['status']==expected and receipt['artifact_integrity_verified'] and receipt['snapshot_integrity_verified']
        results.append(dict(name=name,expected=expected,actual=receipt['status'],passed=passed,
                            receipt=str(Path(receipt['run_directory'])/'receipt.json')))
        if not passed:
            print(json.dumps(receipt, indent=2))
    binary = load_pin(pin)['artifacts']['binary']['path']
    # Exercise the native CLI IO boundary directly, independently of the runner's snapshots.
    proc = subprocess.run([binary, '--passport', str(output/'missing'), '--certificate', str(output/'missing2')],
                          capture_output=True, timeout=10)
    obj = strict_json(proc.stdout)
    passed = proc.returncode == 74 and obj['verdict']=='EXEC_IO_ERROR'
    results.append(dict(name='native_missing_file',expected='EXEC_IO_ERROR',actual=obj['verdict'],passed=passed,
                        exit_code=proc.returncode, stdout=proc.stdout.decode(),stderr=proc.stderr.decode()))
    report = dict(cases=results, total=len(results), passed=sum(x['passed'] for x in results),
                  evidence_kind='compiled_execution', skipped=0)
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if all(x['passed'] for x in results) else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    raise SystemExit(main(args.pin,args.output))
