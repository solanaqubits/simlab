import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_alcc_tasks as a


def rows(c):
    out=[]
    for case in c['cases']:
        e=a.oracle(case)
        for r in range(11):
            for v in (['baseline','cached'] if r%2==0 else ['cached','baseline']):
                out.append(dict(case=case['id'],round=r,variant=v,accepted=not e,elapsed_ns=3,
                                force_digest=sum(sum(t[0])+int(t[2]) for t in e),output=e))
    return out

def encode(xs):return '\n'.join(json.dumps(x) for x in xs)

class AlccTaskTests(unittest.TestCase):
    def test_committed_corpus_and_adapter_match(self):
        p=Path(__file__).resolve().parents[1]/'evaluation/alcc-full-task'
        self.assertEqual(json.loads((p/'corpus.json').read_text()),a.corpus())
        self.assertEqual((p/'AlccFullTaskBench.lean').read_text(),a.lean_source(a.corpus()))
    def test_known_identity_and_rejection(self):
        c=a.corpus()['cases'];self.assertEqual(a.oracle(c[3]),[])
        self.assertEqual(a.oracle(c[4]),[[[0,0,1],'1','1']])
    def test_rational_cancellation(self):
        self.assertEqual(a.normalized([[1,0,0,1,3],[1,0,0,1,6]]),[[[1,0,0],'1','2']])
    def test_full_output_not_verdict_only(self):
        c=a.corpus();r=rows(c);r[22]['output']=[]
        with self.assertRaisesRegex(ValueError,'full_residual'):a.validate(c,encode(r))
    def test_order(self):
        c=a.corpus();r=rows(c);r[0],r[1]=r[1],r[0]
        with self.assertRaisesRegex(ValueError,'order'):a.validate(c,encode(r))
    def test_all_rounds_required(self):
        c=a.corpus()
        with self.assertRaisesRegex(ValueError,'row_count'):a.validate(c,encode(rows(c)[:-1]))
    def test_bad_time(self):
        c=a.corpus();r=rows(c);r[0]['elapsed_ns']=True
        with self.assertRaisesRegex(ValueError,'time'):a.validate(c,encode(r))
    def test_digest(self):
        c=a.corpus();r=rows(c);r[0]['force_digest']=1
        with self.assertRaisesRegex(ValueError,'digest'):a.validate(c,encode(r))
    def test_duplicate_keys(self):
        c=a.corpus();r=encode(rows(c));r=r.replace('"round": 0','"round": 0, "round": 0',1)
        with self.assertRaisesRegex(ValueError,'duplicate_key'):a.validate(c,r)
    def test_round_bool(self):
        c=a.corpus();r=rows(c);r[0]['round']=False
        with self.assertRaisesRegex(ValueError,'round_type'):a.validate(c,encode(r))
    def test_float_exponent(self):
        c=a.corpus();r=rows(c);r[22]['output'][0][0][0]=0.0
        with self.assertRaisesRegex(ValueError,'output_types'):a.validate(c,encode(r))
    def test_samples_scope(self):
        c=a.corpus();v=a.validate(c,encode(rows(c)));self.assertEqual(v['full_outputs_checked'],198)
        self.assertEqual(len(v['cases'][0]['samples_ns']['baseline']),8)
        self.assertFalse(v['performance_qualified'])
