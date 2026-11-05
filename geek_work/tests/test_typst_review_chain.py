import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_binding as binding
import geek_work_pdf_pages as pages
import geek_work_pdf_review as review
import geek_work_manuscript_status as status
import test_typst_gate as gate_fixture
import test_pdf_pages as page_fixture
import test_manuscript_status as latex_status_fixture


class TypstReviewChainTests(unittest.TestCase):
    def setUp(self):
        self.f=gate_fixture.TypstGateTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root;self.gate=self.f.out;self.gate_pin=self.f.bind()['manifest_sha256']
        self.p=page_fixture.PdfPageTests();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.old_latex_binding=self.p.binding;self.old_latex_pin=self.p.anchor
        self.p.binding=self.gate;self.p.anchor=self.gate_pin;self.p.output=self.root/'pages';self.page_pin=self.p.render()['manifest_sha256']
        self.review_out=self.root/'review';self.review_pin=self.record_review(self.p.output,self.page_pin,self.review_out)
        self.spec=dict(schema='geek-work-manuscript-status-plan-2',engine='typst',source=dict(path=self.f.preflight.name,sha256=self.f.pin),compile_binding=dict(path=self.gate.name,sha256=self.gate_pin),page_packet=dict(path='pages',sha256=self.page_pin),visual_review=dict(path='review',sha256=self.review_pin))

    def record_review(self,packet,pin,out,choice='pass'):
        data,_=pages.verified(packet,pin);spec=review.template(pin,data);spec['reviewer']=dict(id='Synthetic',role='implementer',prior_exposure='Synthetic protocol fixture')
        spec['diagnostics']=dict(status='reviewed',note='Synthetic disposition')
        for row in spec['pages']:
            for check in row['checks'].values():check.update(status=choice,note='Synthetic judgment, not independent review')
        path=self.root/(out.name+'-input.json');path.write_bytes(status.m.encoded(spec))
        return review.accept(packet,pin,path,status.m.sha(path.read_bytes()),out)['manifest_sha256']

    def assess(self):return status.assess(self.root,status.m.encoded(self.spec))[0]

    def test_typst_pdf_dispatch_selects_correct_verified_artifact(self):
        report,archive,pdf=binding.verified(self.gate,self.gate_pin)
        self.assertEqual(pdf,self.f.f.pdf);self.assertEqual(pdf,archive['compile/document.pdf']);self.assertEqual(report['binding_kind'],'typst_gate')
        self.assertFalse(report['diagnostics_review_required'])

    def test_typst_pages_and_review_integrate_with_v2_status(self):
        packet,_=pages.verified(self.p.output,self.page_pin);self.assertEqual(packet['binding_kind'],'typst_gate');self.assertEqual(packet['source_binding_status'],binding.typst.CLEAN)
        report=self.assess();self.assertEqual(report['status'],status.CLEAR);self.assertEqual(report['schema'],'geek-work-manuscript-status-report-2');self.assertEqual(report['source_kind'],'typst_preflight')
        self.assertFalse(report['publication_authorized']);self.assertFalse(report['independence_verified'])

    def test_latex_dispatch_retains_legacy_report_shape(self):
        report,archive,pdf=binding.verified(self.old_latex_binding,self.old_latex_pin)
        self.assertNotIn('binding_kind',report);self.assertEqual(pdf,archive['compile/artifacts/document.pdf'])

    def test_unknown_binding_schema_and_bad_pin_are_rejected(self):
        folder=self.root/'unknown';folder.mkdir();raw=status.m.encoded(dict(schema='not-supported'));(folder/'manifest.json').write_bytes(raw)
        with patch.object(binding.typst,'verified',side_effect=AssertionError('not called')),patch.object(binding.latex,'verified_binding',side_effect=AssertionError('not called')),self.assertRaisesRegex(ValueError,'unsupported'):binding.verified(folder,status.m.sha(raw))
        with self.assertRaisesRegex(ValueError,'anchor'):binding.verified(self.gate,'0'*64)

    def test_failed_typst_gate_has_no_renderable_pdf(self):
        self.f.failure();self.f.out=self.root/'failed-gate';pin=self.f.bind()['manifest_sha256'];self.p.binding=self.f.out;self.p.anchor=pin;self.p.output=self.root/'failed-pages';self.p.calls.clear()
        with self.assertRaisesRegex(ValueError,'compiled PDF'):self.p.render()
        self.assertFalse(self.p.output.exists());self.assertFalse(self.p.calls)

    def test_typst_diagnostics_survive_pages_review_and_status(self):
        self.f.f.data['compiler.log']=b'Warning: synthetic';self.f.f.seal();self.f.out=self.root/'warning-gate';pin=self.f.bind()['manifest_sha256']
        self.p.binding=self.f.out;self.p.anchor=pin;self.p.output=self.root/'warning-pages';page_pin=self.p.render()['manifest_sha256']
        review_out=self.root/'warning-review';review_pin=self.record_review(self.p.output,page_pin,review_out)
        self.spec['compile_binding']=dict(path=self.f.out.name,sha256=pin);self.spec['page_packet']=dict(path=self.p.output.name,sha256=page_pin);self.spec['visual_review']=dict(path=review_out.name,sha256=review_pin)
        report=self.assess();self.assertEqual(report['status'],'needs_work');self.assertIn('compile_diagnostics',report['blockers']);self.assertIn('review_diagnostics',report['blockers'])

    def test_renderer_only_diagnostic_keeps_full_typst_chain_blocked(self):
        original=self.p.worker
        def observed(args,cwd=None,timeout=None):
            out,err=original(args,cwd,timeout)
            return (out,b'Syntax Error: synthetic metadata diagnostic') if args[0].endswith('pdfinfo') else (out,err)
        self.p.output=self.root/'metadata-pages'
        with patch.object(self.p,'worker',observed):packet=self.p.render()
        review_out=self.root/'metadata-review';pin=self.record_review(self.p.output,packet['manifest_sha256'],review_out)
        self.spec['page_packet']=dict(path=self.p.output.name,sha256=packet['manifest_sha256']);self.spec['visual_review']=dict(path=review_out.name,sha256=pin)
        report=self.assess();self.assertTrue(report['all_stages_present']);self.assertEqual(report['status'],'needs_work');self.assertIn('renderer_diagnostics',report['blockers'])
        self.assertEqual(report['next_action'],'resolve_recorded_diagnostics')

    def test_stale_preflight_is_rejected_even_with_same_source_bytes(self):
        raw=json.dumps(json.loads(self.f.selection.read_bytes()),separators=(',',':')).encode();self.f.selection.write_bytes(raw);out=self.root/'alternative-preflight'
        pin=status.typst_preflight.check(self.f.project,self.f.selection,status.m.sha(raw),out)['manifest_sha256'];self.spec['source']=dict(path=out.name,sha256=pin)
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: compile/source'):self.assess()

    def test_changed_typst_gate_cannot_use_old_pages(self):
        self.f.f.change('receipt.json',lambda x:x.update(limits='Another consistent record'))
        self.f.out=self.root/'another-gate';pin=self.f.bind()['manifest_sha256'];self.spec['compile_binding']=dict(path=self.f.out.name,sha256=pin)
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: page/compile'):self.assess()

    def test_changed_page_packet_cannot_use_old_review(self):
        self.p.runtime['tools']['pdfinfo']['version']='Other synthetic profile';self.p.renderer_anchor=status.m.sha(status.m.encoded(self.p.runtime));self.p.output=self.root/'another-pages';pin=self.p.render()['manifest_sha256']
        self.spec['page_packet']=dict(path=self.p.output.name,sha256=pin)
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: review/page'):self.assess()

    def test_wrong_engine_or_legacy_plan_does_not_guess_typst(self):
        self.spec['engine']='latex'
        with self.assertRaises(ValueError):self.assess()
        self.spec.pop('engine');self.spec['schema']='geek-work-manuscript-status-plan-1'
        with self.assertRaises(ValueError):self.assess()
        self.spec['schema']='geek-work-manuscript-status-plan-2'
        with self.assertRaises(ValueError):self.assess()

    def test_source_only_typst_plan_has_next_action(self):
        for name in ('compile_binding','page_packet','visual_review'):self.spec[name]=None
        self.assertEqual(self.assess()['next_action'],'run_typst_preflight_gate')
        (self.f.project/'main.typ').write_bytes(b'#include dynamic_path');out=self.root/'needs-review'
        pin=status.typst_preflight.check(self.f.project,self.f.selection,status.m.sha(self.f.selection.read_bytes()),out)['manifest_sha256'];self.spec['source']=dict(path=out.name,sha256=pin)
        self.assertEqual(self.assess()['next_action'],'address_preflight_findings')

    def test_negative_review_and_unknown_outcomes_are_preserved(self):
        for choice,action in [('fail','address_visual_changes'),('unknown','complete_visual_review')]:
            out=self.root/(choice+'-review');pin=self.record_review(self.p.output,self.page_pin,out,choice)
            self.spec['visual_review']=dict(path=out.name,sha256=pin);report=self.assess();self.assertEqual(report['next_action'],action);self.assertEqual(report['status'],'needs_work')

    def test_explicit_v2_latex_plan_retains_public_source_contract(self):
        f=latex_status_fixture.ManuscriptStatusTests();f.setUp()
        try:
            f.spec.update(schema='geek-work-manuscript-status-plan-2',engine='latex')
            report,_=status.assess(f.root,status.m.encoded(f.spec));self.assertEqual(report['status'],status.CLEAR);self.assertEqual(report['source_kind'],'public_source_package')
        finally:f.doCleanups()

    def test_relocated_v2_report_and_review_need_no_runtime(self):
        plan=self.root/'plan.json';plan.write_bytes(status.m.encoded(self.spec));report=self.root/'status.json';result=status.check(self.root,plan,status.m.sha(plan.read_bytes()),report)
        copy=self.root/'relocated';copy.mkdir()
        for name in status.STAGES:shutil.copytree(self.root/self.spec[name]['path'],copy/self.spec[name]['path'])
        shutil.copy2(plan,copy/'plan.json');shutil.copy2(report,copy/'status.json')
        with patch.object(pages,'run',side_effect=AssertionError('no renderer')),patch.object(binding.typst.compiled.c,'build',side_effect=AssertionError('no compiler')):
            self.assertTrue(status.verify_report(copy,copy/'plan.json',status.m.sha((copy/'plan.json').read_bytes()),copy/'status.json',result['report_sha256'])['reproduced'])
        env=dict(os.environ);env['PATH']='';r=subprocess.run([sys.executable,status.__file__,'verify-report','--root',str(copy),'--plan',str(copy/'plan.json'),'--plan-sha256',status.m.sha((copy/'plan.json').read_bytes()),'--report',str(copy/'status.json'),'--report-sha256',result['report_sha256']],capture_output=True,env=env)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':unittest.main()
