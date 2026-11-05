import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_operation_preflight as c


class OperationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.make(False)

    def make(self,fixed,extra=False):
        self.base=self.root/'base';self.candidate=self.root/'candidate';self.proposal=self.root/'proposal';self.decision=self.root/'decision';self.out=self.root/'preflight'
        for p in (self.base,self.candidate,self.proposal,self.decision,self.out):
            if p.exists():shutil.rmtree(p)
        main=b'\\input{section}\n\\bibliography{refs}\n\\cite{k}\n\\ref{part}\n'
        left={'main.tex':main,'section.tex':b'\\label{part}\n','refs.bib':b'@article{k, title={Fixture}}\n'}
        right={'main.tex':main.replace(b'{refs}',b'{bib/refs}') if fixed else main,'section.tex':left['section.tex'],'bib/refs.bib':left['refs.bib']}
        rows=[dict(id='main',op='replace' if fixed else 'guard',kind='text',source='main.tex',target='main.tex'),dict(id='move',op='rename',kind='text',source='refs.bib',target='bib/refs.bib')]
        if extra:
            left['scope.md']=right['scope.md']=b'Guard';rows.append(dict(id='scope',op='guard',kind='text',source='scope.md',target='scope.md'))
        for root,files in [(self.base,left),(self.candidate,right)]:
            root.mkdir()
            for name,raw in files.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.ops=self.root/'ops.json';raw=c.m.encoded(dict(schema='geek-work-file-operations-1',operations=rows));self.ops.write_bytes(raw)
        p=c.ops.propose(self.base,self.candidate,self.ops,c.m.sha(raw),'synthetic','test',self.proposal)
        raw=c.m.encoded(dict(schema='geek-work-file-operation-selection-1',proposal_sha256=p['manifest_sha256'],reviewer='synthetic',decisions=[dict(operation_id=r['id'],decision='confirm' if r['op']=='guard' else 'accept',reason='fixture') for r in rows]))
        ds=self.root/'decisions.json';ds.write_bytes(raw);d=c.ops.decide(self.proposal,p['manifest_sha256'],self.base,ds,c.m.sha(raw),self.decision);self.decision_anchor=d['manifest_sha256']
        self.spec=dict(schema='geek-work-operation-preflight-selection-1',entry='main.tex',files=['main.tex','section.tex','bib/refs.bib']);self.selection=self.root/'selection.json'

    def check(self):
        raw=c.m.encoded(self.spec);self.selection.write_bytes(raw)
        return c.check(self.decision,self.decision_anchor,self.base,self.selection,c.m.sha(raw),self.out)

    def reseal(self):
        p=self.out/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:c.m.sha((self.out/n).read_bytes()) for n in x['files']};raw=c.m.encoded(x);p.write_bytes(raw);return c.m.sha(raw)

    def test_renamed_bibliography_stale_link_flagged(self):
        r=self.check();self.assertEqual(r['status'],'review_required');self.assertEqual(r['references_to_removed_paths'],1)
        report=json.loads((self.out/'report.json').read_bytes());edge=report['references_to_removed_paths'][0]
        self.assertEqual((edge['target'],edge['rename_target']),('refs.bib','bib/refs.bib'))
        self.assertIn('unresolved_citation',{f['code'] for f in report['preflight']['findings']})
        self.assertEqual(report['additional_selected_baseline_paths'],['section.tex'])
        self.assertTrue((self.base/'refs.bib').exists());self.assertFalse((self.out/'sources/refs.bib').exists())

    def test_corrected_projection_has_no_findings(self):
        self.make(True);r=self.check();self.assertEqual(r['status'],'no_findings_in_supported_subset')
        self.assertIn(b'{bib/refs}',(self.out/'sources/main.tex').read_bytes());self.assertIn(b'{refs}',(self.base/'main.tex').read_bytes())
        report=json.loads((self.out/'report.json').read_bytes());self.assertEqual(report['preflight']['active_bibliographies'],['bib/refs.bib'])
        self.assertFalse(report['full_syntax_coverage']);self.assertFalse(report['compilation_verified'])

    def test_warning_exit_codes_for_check_and_verify(self):
        raw=c.m.encoded(self.spec);self.selection.write_bytes(raw)
        args=[sys.executable,c.__file__,'check','--decision',str(self.decision),'--decision-sha256',self.decision_anchor,'--root',str(self.base),'--selection',str(self.selection),'--selection-sha256',c.m.sha(raw),'--output',str(self.out)]
        result=subprocess.run(args,capture_output=True);self.assertEqual(result.returncode,2);anchor=json.loads(result.stdout)['manifest_sha256']
        checked=subprocess.run([sys.executable,c.__file__,'verify','--bundle',str(self.out),'--sha256',anchor],capture_output=True);self.assertEqual(checked.returncode,2);self.assertTrue(json.loads(checked.stdout)['reproduced'])

    def test_stale_bound_source_and_occupied_target_reject_before_output(self):
        for name,raw in [('main.tex',b'drift'),('bib/refs.bib',b'')]:
            p=self.base/name;old=p.read_bytes() if p.exists() else None;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):self.check()
            self.assertFalse(self.out.exists())
            if old is None:p.unlink()
            else:p.write_bytes(old)

    def test_additional_selected_source_is_captured_not_old_review(self):
        self.make(True);(self.base/'section.tex').write_bytes(b'Changed extra material\n');r=self.check();self.assertEqual(r['status'],'review_required')
        report=json.loads((self.out/'report.json').read_bytes());self.assertEqual(report['additional_selected_baseline_paths'],['section.tex']);self.assertIn('unresolved_reference',{f['code'] for f in report['preflight']['findings']})

    def test_removed_or_omitted_supported_write_selection_rejected(self):
        original=self.spec['files'][:]
        for names in [original+['refs.bib'],['main.tex','section.tex']]:
            self.spec['files']=names
            with self.assertRaises(ValueError):self.check()
            self.assertFalse(self.out.exists())

    def test_unsupported_operation_paths_require_review(self):
        self.make(True,True);r=self.check();self.assertEqual(r['status'],'review_required');self.assertEqual(r['findings'],0)
        self.assertEqual(json.loads((self.out/'report.json').read_bytes())['unanalysed_operation_paths'],['scope.md'])

    def test_unselected_dependency_and_dynamic_syntax_are_not_success(self):
        self.make(True);self.spec['files'].remove('section.tex');r=self.check();self.assertEqual(r['status'],'review_required')
        report=json.loads((self.out/'report.json').read_bytes());self.assertIn('dependency_not_selected',{f['code'] for f in report['preflight']['findings']})
        self.make(True);(self.base/'section.tex').write_bytes(b'\\newcommand{\\x}{1}\n\\label{part}\n');r=self.check();self.assertEqual(r['status'],'review_required')

    def test_missing_or_symlink_additional_source_fails(self):
        p=self.base/'section.tex';p.unlink()
        with self.assertRaises(ValueError):self.check()
        p.symlink_to(self.root/'external')
        with self.assertRaises(ValueError):self.check()
        self.assertFalse(self.out.exists())

    def test_relocation_reproduces_without_old_inputs_or_processes(self):
        self.make(True);r=self.check();moved=self.root/'moved';shutil.move(self.out,moved)
        for p in (self.base,self.candidate,self.proposal,self.decision):shutil.rmtree(p)
        with patch('subprocess.run',side_effect=AssertionError('no execution')):v=c.verify(moved,r['manifest_sha256'])
        self.assertEqual(v['status'],r['status']);self.assertFalse(v['live_project_checked']);self.assertFalse(v['historical_baseline_check_verified'])
        result=json.loads(subprocess.check_output([sys.executable,c.__file__,'verify','--bundle',str(moved),'--sha256',r['manifest_sha256']],env={**os.environ,'PATH':''}));self.assertEqual(result,v)

    def test_resealed_report_cannot_hide_findings(self):
        self.check();p=self.out/'report.json';x=json.loads(p.read_bytes());x['status']='no_findings_in_supported_subset';x['references_to_removed_paths']=[];p.write_bytes(c.m.encoded(x));anchor=self.reseal()
        with self.assertRaisesRegex(ValueError,'report reproduction'):c.verify(self.out,anchor)

    def test_resealed_projection_and_bound_baseline_rejected(self):
        self.make(True);self.check();p=self.out/'sources/main.tex';old=p.read_bytes();p.write_bytes(b'forged');anchor=self.reseal()
        with self.assertRaisesRegex(ValueError,'projection mismatch'):c.verify(self.out,anchor)
        p.write_bytes(old);(self.out/'baseline/main.tex').write_bytes(b'drift');anchor=self.reseal()
        with self.assertRaisesRegex(ValueError,'STALE_BASE'):c.verify(self.out,anchor)

    def test_anchors_and_embedded_decision_tamper(self):
        self.check()
        with self.assertRaisesRegex(ValueError,'anchor'):c.verify(self.out,'0'*64)
        (self.out/'decision/removals.json').write_bytes(b'[]\n')
        with self.assertRaises(ValueError):c.verify(self.out,c.m.sha((self.out/'manifest.json').read_bytes()))

    def test_extra_missing_and_unsafe_archive_entries(self):
        r=self.check();(self.out/'empty').mkdir()
        with self.assertRaises(ValueError):c.verify(self.out,r['manifest_sha256'])
        (self.out/'empty').rmdir();p=self.out/'sources/section.tex';p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):c.verify(self.out,r['manifest_sha256'])

    def test_limits_output_separation_and_selection_pin(self):
        with patch.object(c,'MAX_BASELINE',1),self.assertRaisesRegex(ValueError,'baseline byte'):self.check()
        self.assertFalse(self.out.exists());self.out=self.base/'output'
        with self.assertRaisesRegex(ValueError,'disjoint'):self.check()
        self.out=self.root/'preflight';raw=c.m.encoded(self.spec);self.selection.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'selection SHA'):c.check(self.decision,self.decision_anchor,self.base,self.selection,'0'*64,self.out)


if __name__=='__main__':unittest.main()
