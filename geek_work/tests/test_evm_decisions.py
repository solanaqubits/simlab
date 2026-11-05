import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_evm_decisions as d
from geek_work_evm_decisions import audit as a


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.packet=self.root/'packet';self.packet.mkdir()
        self.evidence=self.root/'materials';self.evidence.mkdir();self.out=self.root/'record'
        source={'schema':'geek-work-evm-audit-source-1','commit':'a'*40,
                'sources':[{'path':a.PREFIX+n,'text':'line\n','sha256':a.sha(b'line\n')} for n in a.SOURCE_NAMES],
                'execution_evidence_included':False,'dependency_sources_included':False,'independent_audit_completed':False,'production_ready':False}
        files={'packet.json':a.encode(source),'REVIEW.md':b'fixture','RESPONSE.template.json':b'{}'}
        for n,b in files.items():(self.packet/n).write_bytes(b)
        manifest=a.encode({'schema':'geek-work-evm-audit-manifest-1','files':{n:a.sha(b) for n,b in files.items()}})
        (self.packet/'MANIFEST.json').write_bytes(manifest);self.anchor=a.sha(manifest)
        self.response={'schema':'geek-work-evm-audit-response-1','packet_sha256':a.sha(files['packet.json']),
            'reviewer':{'id':'fixture','prior_exposure':'synthetic test only'},'integrity_checks':[],
            'findings':[{'id':'f1','kind':'defect','severity':'high','summary':'Synthetic defect','rationale':'Fixture only',
                         'citations':[{'path':a.PREFIX+a.SOURCE_NAMES[0],'line_start':1,'line_end':1,'quote':'line'}]}],
            'open_questions':['Unresolved fixture question'],'overall_assessment':None,'independence_verified':False,'accepted_as_gold':False}
        self.rpath=self.root/'response.json';self.rpath.write_bytes(a.encode(self.response));self.rsha=a.sha(self.rpath.read_bytes())
        self.decisions={'schema':'geek-work-evm-decisions-1','packet_sha256':self.response['packet_sha256'],
                        'response_sha256':self.rsha,'adjudicator':{'id':'fixture-author','prior_participation':'implementation author'},
                        'decisions':[{'finding_id':'f1','state':'open','rationale':'Needs investigation','fix_commit':None,'evidence':[]}]}
        self.dpath=self.root/'decisions.json'
    def run_record(self):
        self.dpath.write_bytes(a.encode(self.decisions))
        return d.record(self.packet,self.anchor,self.rpath,self.rsha,self.dpath,a.sha(self.dpath.read_bytes()),self.evidence,self.out)
    def material(self,state='resolved_claimed'):
        b=b'Synthetic reproduction report, not a real audit.\n';(self.evidence/'repro.txt').write_bytes(b)
        self.decisions['decisions'][0].update(state=state,fix_commit='b'*40,evidence=[{'file':'repro.txt','sha256':a.sha(b),'purpose':'synthetic supporting material'}])
    def reject(self):
        with self.assertRaises(ValueError):self.run_record()
        self.assertFalse(self.out.exists())
    def test_open_record_preserves_response_and_question(self):
        r=self.run_record();self.assertEqual(r['states']['open'],1);self.assertEqual(r['open_questions'],1)
        self.assertEqual((self.out/'response.json').read_bytes(),self.rpath.read_bytes())
        self.assertFalse(r['assessment_present']);self.assertFalse(r['production_ready'])
    def test_resolution_claim_is_not_verified(self):
        self.material();r=self.run_record();self.assertEqual(r['states']['resolved_claimed'],1)
        for field in ('findings_verified','resolutions_verified','fix_commits_checked','adjudicator_identity_verified','independence_verified','independent_audit_completed','production_ready'):self.assertIs(r[field],False)
        self.assertEqual((self.out/'evidence/repro.txt').read_bytes(),(self.evidence/'repro.txt').read_bytes())
    def test_unknown_missing_and_duplicate_findings(self):
        row=copy.deepcopy(self.decisions['decisions'][0])
        for rows in [[],[row,row],[{**row,'finding_id':'unknown'}]]:
            self.decisions['decisions']=rows;self.reject()
    def test_wrong_packet_response_and_input_hashes(self):
        original=copy.deepcopy(self.decisions)
        for field in ('packet_sha256','response_sha256'):
            self.decisions=copy.deepcopy(original);self.decisions[field]='0'*64;self.reject()
        self.decisions=original;self.rsha='0'*64;self.reject()
    def test_resolution_requires_evidence_and_commit(self):
        row=self.decisions['decisions'][0];row['state']='resolved_claimed';self.reject()
        self.material();row['fix_commit']=None;self.reject();row['fix_commit']='abc';self.reject()
    def test_bad_evidence_hash_or_traversal(self):
        self.material();ref=self.decisions['decisions'][0]['evidence'][0]
        original=copy.deepcopy(ref);ref['sha256']='0'*64;self.reject()
        ref.update(original);ref['file']='../repro.txt';self.reject()
    def test_symlink_and_total_limit(self):
        self.material();p=self.evidence/'repro.txt';q=self.root/'target';p.rename(q);p.symlink_to(q);self.reject()
        p.unlink();q.rename(p)
        with patch.object(d,'TOTAL_EVIDENCE_BYTES',1):self.reject()
    def test_self_promotion_or_missing_identity_refused(self):
        self.decisions['production_ready']=True;self.reject();del self.decisions['production_ready']
        self.decisions['adjudicator']['id']=None;self.reject()
    def test_duplicate_evidence_and_empty_dispute_refused(self):
        self.material('disputed');row=self.decisions['decisions'][0];row['evidence']*=2;self.reject()
        row['evidence']=[];self.reject()
    def test_no_overwrite(self):
        self.run_record()
        with self.assertRaises(FileExistsError):self.run_record()
    def test_evidence_snapshot_is_exact_even_if_source_changes(self):
        self.material();original=a.read_regular
        def mutate(path):
            raw=original(path)
            if path==self.evidence/'repro.txt':path.write_bytes(b'changed after read')
            return raw
        with patch.object(a,'read_regular',side_effect=mutate):r=self.run_record()
        self.assertEqual(a.sha((self.out/'evidence/repro.txt').read_bytes()),r['evidence']['repro.txt'])
        self.assertNotEqual((self.out/'evidence/repro.txt').read_bytes(),(self.evidence/'repro.txt').read_bytes())
    def test_cli_record(self):
        self.dpath.write_bytes(a.encode(self.decisions))
        result=subprocess.check_output(['python3',d.__file__,'--packet',str(self.packet),'--manifest-sha256',self.anchor,
            '--response',str(self.rpath),'--response-sha256',self.rsha,'--decisions',str(self.dpath),
            '--decisions-sha256',a.sha(self.dpath.read_bytes()),'--evidence-dir',str(self.evidence),'--output',str(self.out)],text=True)
        self.assertEqual(json.loads(result)['status'],'dispositions_recorded')
