#!/usr/bin/env python3
"""Frozen complete typed ALCC tasks and independent rational oracle (not byte bridge)."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(x).hexdigest()


def normalized(terms):
    coefficients={}
    for x,y,z,a,b in terms:
        assert type(b) is int and b>0
        e=(x,y,z);coefficients[e]=coefficients.get(e,Fraction())+Fraction(a,b)
    return [[list(e),str(v.numerator),str(v.denominator)] for e,v in
            sorted(coefficients.items(),reverse=True) if v]


def oracle(case):
    terms=list(case['target'])
    for hyp,mult in zip(case['hypotheses'],case['multipliers'],strict=True):
        for x,y,z,a,b in hyp:
            for u,v,w,c,d in mult:terms.append([x+u,y+v,z+w,-a*c,b*d])
    return normalized(terms)


def product(h,q):
    return [[x+u,y+v,z+w,a*c,b*d] for x,y,z,a,b in h for u,v,w,c,d in q]


def corpus():
    one=[[0,0,0,1,1]];x=[[1,0,0,1,1]]
    cases=[dict(id='empty',hypotheses=[[],[]],multipliers=[[],[]],target=[]),
           dict(id='constant-mismatch',hypotheses=[[],[]],multipliers=[one,[]],target=one),
           dict(id='identity-x',hypotheses=[x,[]],multipliers=[one,[]],target=x)]
    h=[[[2,0,0,1,1],[0,1,0,-1,1]],[[0,2,0,1,1],[0,0,1,-1,1]]]
    q=[[[2,0,0,1,1],[0,1,0,1,1]],one]
    cases.append(dict(id='chain-valid',hypotheses=h,multipliers=q,target=[[4,0,0,1,1],[0,0,1,-1,1]]))
    cases.append(dict(id='chain-invalid',hypotheses=h,multipliers=q,target=[[4,0,0,1,1]]))
    for n in (8,24,48):
        h0=[[i,0,0,(-1)**i*(i+1),i+2] for i in range(n)]
        q0=[[0,j,0,j+1,7] for j in range(4)]
        target=product(h0,q0)
        cases.append(dict(id=f'product-{n}',hypotheses=[h0,[]],multipliers=[q0,[]],target=target))
    cases.append(dict(id='duplicate-cancellation',hypotheses=[x+x,[]],multipliers=[[[0,0,0,1,2]],[]],target=x))
    return dict(schema='geek-work-alcc-tasks-1',dimensions=3,hypotheses_count=2,
                rounds=11,warmup_rounds=3,cases=cases,
                scope='Finite generated typed tasks; excludes JSON binding, SHA, IO and full production pipeline')


def poly(xs):
    return '['+', '.join(f'(⟨[{x}, {y}, {z}], rfl⟩, ({a} : Rat) / {b})' for x,y,z,a,b in xs)+']'


def lean_source(c):
    entries=[]
    for row in c['cases']:
        h,q=row['hypotheses'],row['multipliers']
        entries.append(f'({json.dumps(row["id"])}, '+
          f'{{ hypotheses := fun i => if i.val == 0 then {poly(h[0])} else {poly(h[1])}, target := {poly(row["target"])} }}, '+
          f'{{ multipliers := fun i => if i.val == 0 then {poly(q[0])} else {poly(q[1])} }})')
    return '''import Verification.AlgebraicCertificateNormalizeCached
import Lean.Data.Json.Basic
open AlgebraicCertificateKernel AlgebraicCertificateNormalizeCached
set_option maxRecDepth 4096
set_option maxHeartbeats 2000000
abbrev AlccBenchTask := String × Passport 3 2 × Certificate 3 2

def cases : List AlccBenchTask := [\n''' + ',\n'.join(entries)+''']

@[noinline] def compute (cached : Bool) (p : Passport 3 2) (c : Certificate 3 2) :
    IO (Bool × SparsePoly 3 × Nat) := do
  let r := residual p c
  let result := if cached then normalizeCached r else normalize r
  let accepted := isZero result
  let digest := result.foldl (fun acc t => acc + t.1.val.sum + t.2.den) 0
  return (accepted, result, digest)

def termJson (t : Term 3) : Lean.Json :=
  Lean.Json.arr #[Lean.toJson t.1.val, Lean.toJson (toString t.2.num), Lean.toJson (toString t.2.den)]

def main : IO Unit := do
  for (name, p, c) in cases do
    for round in List.range 11 do
      let order := if round % 2 == 0 then [false, true] else [true, false]
      for cached in order do
        let start ← IO.monoNanosNow
        let (accepted, result, digest) ← compute cached p c
        let stop ← IO.monoNanosNow
        IO.println (Lean.Json.mkObj [
          ("case", Lean.toJson name), ("round", Lean.toJson round),
          ("variant", Lean.toJson (if cached then "cached" else "baseline")),
          ("accepted", Lean.toJson accepted), ("elapsed_ns", Lean.toJson (stop-start)),
          ("force_digest", Lean.toJson digest),
          ("output", Lean.Json.arr (result.map termJson).toArray)]).compress
'''


def validate(c, text):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('duplicate_key')
            out[k]=v
        return out
    rows=[json.loads(line,object_pairs_hook=unique) for line in text.splitlines()]
    if len(rows)!=len(c['cases'])*22:raise ValueError('row_count')
    out=[];pos=0
    for case in c['cases']:
        expected=oracle(case);samples={'baseline':[],'cached':[]}
        for round_no in range(11):
            for variant in (['baseline','cached'] if round_no%2==0 else ['cached','baseline']):
                row=rows[pos];pos+=1
                if set(row)!={'case','round','variant','accepted','elapsed_ns','force_digest','output'}:raise ValueError('schema')
                if type(row['round']) is not int:raise ValueError('round_type')
                if (row['case'],row['round'],row['variant'])!=(case['id'],round_no,variant):raise ValueError('order')
                if type(row['accepted']) is not bool or row['accepted'] != (expected==[]):raise ValueError('verdict')
                if type(row['output']) is not list or any(type(t) is not list or len(t)!=3 or type(t[0]) is not list or len(t[0])!=3 or any(type(e) is not int for e in t[0]) or type(t[1]) is not str or type(t[2]) is not str for t in row['output']):raise ValueError('output_types')
                if row['output']!=expected:raise ValueError('full_residual')
                d=sum(sum(t[0])+int(t[2]) for t in expected)
                if type(row['force_digest']) is not int or row['force_digest']!=d:raise ValueError('digest')
                if type(row['elapsed_ns']) is not int or row['elapsed_ns']<0:raise ValueError('time')
                if round_no>=3:samples[variant].append(row['elapsed_ns'])
        out.append(dict(id=case['id'],accepted=not expected,samples_ns=samples,
                        median_ns={k:statistics.median(v) for k,v in samples.items()}))
    return dict(schema='geek-work-alcc-task-result-1',status='FINITE_CORPUS_MATCH',
                corpus_sha256=digest(canonical(c)),full_outputs_checked=len(rows),cases=out,
                performance_qualified=False,production_replacement=False,
                scope=c['scope'])
