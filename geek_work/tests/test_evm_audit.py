import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('evm_audit',Path(__file__).parents[1]/'tools/geek_work_evm_audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


class EVMAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
        self.git('init','-q');self.git('config','user.name','Test');self.git('config','user.email','test@example.invalid')
        for name in a.SOURCE_NAMES:
            p=self.repo/(a.PREFIX+name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Source α\n')
        p=self.repo/a.REVIEW_PATH;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Review pinned sources.\n')
        self.git('add','.');self.git('commit','-qm','fixture')
        self.commit=self.git('rev-parse','HEAD').strip();self.out=self.root/'packet'
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args],text=True,stderr=subprocess.PIPE)
    def packet(self):return a.export(self.repo,self.commit,self.out)
    def test_pinned_snapshot_ignores_dirty_worktree_and_relocates(self):
        (self.repo/(a.PREFIX+a.SOURCE_NAMES[0])).write_text('uncommitted mutation')
        result=self.packet();packet=json.loads((self.out/'packet.json').read_text())
        self.assertEqual(packet['sources'][0]['text'],'Source α\n')
        moved=self.root/'moved';self.out.rename(moved)
        self.assertEqual(a.verify(moved,result['manifest_sha256'])['status'],'integrity_verified')
        self.assertFalse(a.verify(moved,result['manifest_sha256'])['source_repository_checked'])
    def test_tamper_and_wrong_anchor(self):
        result=self.packet()
        with self.assertRaises(ValueError):a.verify(self.out,'0'*64)
        (self.out/'REVIEW.md').write_text('changed')
        with self.assertRaises(ValueError):a.verify(self.out,result['manifest_sha256'])
    def test_exclusive_output(self):
        self.packet()
        with self.assertRaises(FileExistsError):self.packet()
    def test_extra_file_and_symlink_rejected(self):
        result=self.packet();extra=self.out/'other';extra.write_text('x')
        with self.assertRaises(ValueError):a.verify(self.out,result['manifest_sha256'])
        extra.unlink();target=self.out/'REVIEW.md';outside=self.root/'review';target.rename(outside);target.symlink_to(outside)
        with self.assertRaises(ValueError):a.verify(self.out,result['manifest_sha256'])
    def test_commit_required_and_missing_source(self):
        with self.assertRaises(ValueError):a.export(self.repo,'HEAD',self.out)
        self.git('rm',a.PREFIX+a.SOURCE_NAMES[0]);self.git('commit','-qm','remove')
        with self.assertRaises(ValueError):a.export(self.repo,self.git('rev-parse','HEAD').strip(),self.out)
        self.assertFalse(self.out.exists())
    def test_git_symlink_refused(self):
        p=self.repo/(a.PREFIX+a.SOURCE_NAMES[0]);p.unlink();p.symlink_to('/etc/passwd')
        self.git('add','.');self.git('commit','-qm','symlink')
        with self.assertRaises(ValueError):a.export(self.repo,self.git('rev-parse','HEAD').strip(),self.out)
    def test_resealed_inconsistent_source_and_false_claims_refused(self):
        self.packet();original=json.loads((self.out/'packet.json').read_text())
        for fault in ('source','claim'):
            packet=json.loads(json.dumps(original))
            if fault=='source':packet['sources'][0]['text']='wrong'
            else:packet['production_ready']=True
            (self.out/'packet.json').write_bytes(a.encode(packet))
            manifest=json.loads((self.out/'MANIFEST.json').read_text());manifest['files']['packet.json']=a.sha((self.out/'packet.json').read_bytes())
            raw=a.encode(manifest);(self.out/'MANIFEST.json').write_bytes(raw)
            with self.assertRaises(ValueError):a.verify(self.out,a.sha(raw))


class EVMReviewIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.packet=self.root/'packet';self.packet.mkdir()
        source=dict(schema='geek-work-evm-audit-source-1',commit='a'*40,
                    sources=[dict(path=a.PREFIX+n,text='first α\nsecond β\n',sha256=a.sha('first α\nsecond β\n'.encode())) for n in a.SOURCE_NAMES],
                    execution_evidence_included=False,dependency_sources_included=False,
                    independent_audit_completed=False,production_ready=False)
        files={'packet.json':a.encode(source),'REVIEW.md':b'review','RESPONSE.template.json':b'{}'}
        for name,raw in files.items():(self.packet/name).write_bytes(raw)
        manifest=a.encode(dict(schema='geek-work-evm-audit-manifest-1',files={n:a.sha(b) for n,b in files.items()}))
        (self.packet/'MANIFEST.json').write_bytes(manifest);self.anchor=a.sha(manifest)
        self.response=dict(schema='geek-work-evm-audit-response-1',packet_sha256=a.sha(files['packet.json']),
                           reviewer=dict(id='synthetic-test',prior_exposure='fixture only; not an independent reviewer'),
                           integrity_checks=[dict(name='external repository',status='not_checked',details='not accessed')],
                           findings=[dict(id='f1',kind='question',severity='info',summary='Synthetic citation exercise',rationale='Not a real audit finding.',citations=[dict(path=a.PREFIX+a.SOURCE_NAMES[0],line_start=1,line_end=2,quote='first α\nsecond β')])],
                           open_questions=[],overall_assessment=None,independence_verified=False,accepted_as_gold=False)
        self.path=self.root/'response.json';self.out=self.root/'received'
    def run_receive(self,raw=None,anchor=None):
        raw=a.encode(self.response) if raw is None else raw;self.path.write_bytes(raw)
        return a.receive(self.packet,self.anchor,self.path,anchor or a.sha(raw),self.out)
    def reject(self):
        with self.assertRaises(ValueError):self.run_receive()
        self.assertFalse(self.out.exists())
    def test_valid_partial_keeps_limits_and_original_bytes(self):
        result=self.run_receive()
        self.assertEqual(result['findings'],1);self.assertEqual(result['citations'],1)
        self.assertFalse(result['assessment_present']);self.assertEqual(result['reported_unchecked_checks'],1)
        for field in ('findings_verified','reviewer_identity_verified','independence_verified','accepted_as_gold','production_ready','independent_audit_completed'):
            self.assertIs(result[field],False)
        self.assertEqual((self.out/'response.json').read_bytes(),self.path.read_bytes())
    def test_wrong_packet_or_response_anchor(self):
        with self.assertRaises(ValueError):self.run_receive(anchor='0'*64)
        self.response['packet_sha256']='0'*64;self.reject()
    def test_mutated_quote_rejected(self):
        self.response['findings'][0]['citations'][0]['quote']='first a\nsecond β';self.reject()
    def test_bad_line_types_ranges_and_foreign_paths(self):
        import copy
        original=copy.deepcopy(self.response)
        for key,value in [('line_start',True),('line_start',0),('line_end',100),('path','../../secret')]:
            self.response=copy.deepcopy(original);self.response['findings'][0]['citations'][0][key]=value;self.reject()
    def test_self_promotion_and_unknown_fields_rejected(self):
        import copy
        original=copy.deepcopy(self.response)
        for field in ('accepted_as_gold','independence_verified','production_ready'):
            self.response=copy.deepcopy(original);self.response[field]=True;self.reject()
    def test_duplicate_json_and_nonfinite_rejected(self):
        raw=a.encode(self.response)
        for invalid in [raw.replace(b'"accepted_as_gold": false',b'"accepted_as_gold": true, "accepted_as_gold": false'),raw.replace(b'"overall_assessment": null',b'"overall_assessment": NaN')]:
            with self.assertRaises(ValueError):self.run_receive(raw=invalid)
            self.assertFalse(self.out.exists())
    def test_duplicate_findings_and_missing_citations(self):
        self.response['findings']*=2;self.reject()
        self.response['findings']=self.response['findings'][:1];self.response['findings'][0]['citations']=[];self.reject()
    def test_identity_and_exposure_required(self):
        self.response['reviewer']['prior_exposure']=None;self.reject()
    def test_empty_findings_do_not_mean_pass(self):
        self.response['findings']=[];self.response['overall_assessment']='No findings reported; no approval.'
        self.response['integrity_checks'][0]['status']='failed'
        result=self.run_receive();self.assertEqual(result['reported_failed_checks'],1)
        self.assertEqual(result['status'],'structure_and_citations_valid');self.assertFalse(result['independent_audit_completed'])
    def test_no_overwrite_and_symlink(self):
        self.run_receive()
        with self.assertRaises(FileExistsError):self.run_receive()
        other=self.root/'other';self.path.rename(other);self.path.symlink_to(other)
        with self.assertRaises(ValueError):a.receive(self.packet,self.anchor,self.path,a.sha(other.read_bytes()),self.root/'second')
    def test_cli_receives_and_preserves_packet(self):
        self.path.write_bytes(a.encode(self.response));before={p.name:p.read_bytes() for p in self.packet.iterdir()}
        raw=subprocess.check_output(['python3',str(Path(a.__file__)),'receive','--packet',str(self.packet),'--manifest-sha256',self.anchor,'--response',str(self.path),'--response-sha256',a.sha(self.path.read_bytes()),'--output',str(self.out)],text=True)
        self.assertEqual(json.loads(raw)['status'],'structure_and_citations_valid')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.packet.iterdir()})

    def test_packet_is_not_reread_after_snapshot(self):
        from unittest.mock import patch
        original=a.read_regular
        def changing(path):
            raw=original(path)
            if path==self.packet/'packet.json':path.write_bytes(raw.replace('first α'.encode(),b'changed'))
            return raw
        with patch.object(a,'read_regular',side_effect=changing):result=self.run_receive()
        self.assertEqual(result['citations'],1)
        self.assertEqual(result['packet_sha256'],self.response['packet_sha256'])
    def test_fifo_size_and_list_bounds(self):
        import os
        from unittest.mock import patch
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(ValueError):a.read_regular(fifo)
        small=self.root/'large';small.write_bytes(b'12345')
        with patch.object(a,'MAX_BYTES',4),self.assertRaises(ValueError):a.read_regular(small)
        self.response['open_questions']=['question']*257;self.reject()
