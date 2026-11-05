import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_manuscript_status as s
import test_pdf_review as fixtures


class ManuscriptStatusTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfReviewTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.review_result=self.f.accept();self.root=self.f.root;self.plan_path=self.root/'plan.json';self.output=self.root/'status.json'
        self.pages=self.f.f;self.compiled=self.pages.f;self.latex=self.compiled.f
        self.spec=dict(schema='geek-work-manuscript-status-plan-1',source=dict(path=self.compiled.source.name,sha256=self.compiled.source_pin),
            compile_binding=dict(path=self.pages.binding.name,sha256=self.pages.anchor),page_packet=dict(path=self.f.packet.name,sha256=self.f.pin),
            visual_review=dict(path=self.f.out.name,sha256=self.review_result['manifest_sha256']))

    def check(self):
        self.plan_path.write_bytes(s.m.encoded(self.spec));return s.check(self.root,self.plan_path,s.m.sha(self.plan_path.read_bytes()),self.output)

    def test_complete_chain_reports_external_obligations(self):
        result=self.check();self.assertEqual(result['status'],s.CLEAR);report=json.loads(self.output.read_bytes());self.assertTrue(report['all_stages_present']);self.assertTrue(report['chain_links_consistent'])
        self.assertFalse(report['publication_authorized']);self.assertFalse(report['independence_verified']);self.assertIn('rights_review',report['external_obligations'])
        self.assertEqual(report['next_action'],'obtain_independent_visual_privacy_rights_review')

    def test_partial_source_only_is_not_false_green(self):
        for name in ('compile_binding','page_packet','visual_review'):self.spec[name]=None
        result=self.check();self.assertEqual(result['status'],'needs_work');self.assertEqual(result['next_action'],'prepare_compile_request_and_bind_result')
        self.assertFalse(json.loads(self.output.read_bytes())['all_stages_present'])

    def test_missing_pages_and_review_have_actionable_next_step(self):
        self.spec['visual_review']=None;self.spec['page_packet']=None
        result=self.check();self.assertEqual(result['next_action'],'render_page_packet');self.output.unlink()
        self.spec['page_packet']=dict(path=self.f.packet.name,sha256=self.f.pin)
        self.assertEqual(self.check()['next_action'],'record_visual_review')

    def test_invalid_dependency_declarations_rejected(self):
        self.spec['compile_binding']=None
        with self.assertRaisesRegex(ValueError,'requires compile'):self.check()
        self.spec['page_packet']=None
        with self.assertRaisesRegex(ValueError,'requires page'):self.check()
        self.assertFalse(self.output.exists())

    def test_individually_valid_new_source_does_not_match_old_compile(self):
        self.compiled.write_source({'main.tex':self.latex.data['sources/main.tex']+b'% new source'})
        self.spec['source']['sha256']=self.compiled.source_pin
        s.source.verify_public(self.compiled.source,self.compiled.source_pin);s.compile_stage.verify_binding(self.pages.binding,self.pages.anchor)
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: compile/source'):self.check()
        self.assertFalse(self.output.exists())

    def test_individually_valid_new_compile_does_not_match_old_pages(self):
        self.latex.change('receipt.json',lambda x:x.update(limits='Different consistent recorded metadata'))
        self.compiled.out=self.root/'compile-alt';x=self.compiled.bind();self.spec['compile_binding']=dict(path='compile-alt',sha256=x['manifest_sha256'])
        s.compile_stage.verify_binding(self.compiled.out,x['manifest_sha256']);s.pages.verify(self.f.packet,self.f.pin)
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: page/compile'):self.check()

    def test_individually_valid_new_pages_do_not_match_old_review(self):
        self.pages.output=self.root/'pages-alt';self.pages.runtime['tools']['pdfinfo']['version']='Other synthetic profile'
        self.pages.renderer_anchor=s.m.sha(s.m.encoded(self.pages.runtime));x=self.pages.render();self.spec['page_packet']=dict(path='pages-alt',sha256=x['manifest_sha256'])
        s.pages.verify(self.pages.output,x['manifest_sha256']);s.review.verify(self.f.out,self.review_result['manifest_sha256'])
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH: review/page'):self.check()

    def test_negative_unknown_and_external_role_do_not_promote_review(self):
        for choice,action in [('fail','address_visual_changes'),('unknown','complete_visual_review')]:
            shutil.rmtree(self.f.out);self.f.spec['pages'][0]['checks']['legibility']['status']=choice;self.f.spec['reviewer']['role']='external_reviewer'
            result=self.f.accept();self.spec['visual_review']['sha256']=result['manifest_sha256'];status=self.check()
            self.assertEqual(status['next_action'],action);self.assertEqual(status['status'],'needs_work');self.output.unlink()

    def test_compile_failure_is_retained_with_no_pdf(self):
        self.compiled.failure();self.compiled.out=self.root/'failed-compile';x=self.compiled.bind()
        self.spec['compile_binding']=dict(path='failed-compile',sha256=x['manifest_sha256']);self.spec['page_packet']=self.spec['visual_review']=None
        result=self.check();self.assertEqual(result['next_action'],'address_compile_failure');self.assertIsNone(json.loads(self.output.read_bytes())['pdf'])

    def test_compile_diagnostics_are_not_erased(self):
        self.latex.warning();self.compiled.out=self.root/'warning-compile';x=self.compiled.bind()
        self.spec['compile_binding']=dict(path='warning-compile',sha256=x['manifest_sha256']);self.spec['page_packet']=self.spec['visual_review']=None
        result=self.check();self.assertEqual(result['next_action'],'resolve_compile_diagnostics');self.assertIn('compile_diagnostics',result['blockers'])

    def test_fully_linked_warning_chain_still_needs_work(self):
        self.latex.warning();self.compiled.out=self.root/'warning-binding';compiled=self.compiled.bind()
        self.pages.binding=self.compiled.out;self.pages.anchor=compiled['manifest_sha256'];self.pages.output=self.root/'warning-pages';packet=self.pages.render()
        self.f.packet=self.pages.output;self.f.pin=packet['manifest_sha256'];self.f.spec['page_packet_sha256']=self.f.pin;self.f.out=self.root/'warning-review';review=self.f.accept()
        self.spec['compile_binding']=dict(path=self.compiled.out.name,sha256=compiled['manifest_sha256'])
        self.spec['page_packet']=dict(path=self.pages.output.name,sha256=packet['manifest_sha256']);self.spec['visual_review']=dict(path=self.f.out.name,sha256=review['manifest_sha256'])
        result=self.check();self.assertEqual(result['status'],'needs_work');self.assertIn('compile_diagnostics',result['blockers']);self.assertIn('review_diagnostics',result['blockers'])
        self.assertTrue(json.loads(self.output.read_bytes())['all_stages_present'])

    def test_wrong_anchor_extra_fields_and_traversal_rejected(self):
        self.spec['source']['sha256']='0'*64
        with self.assertRaises(ValueError):self.check()
        self.spec['source']['path']='../outside'
        with self.assertRaises(ValueError):self.check()
        self.spec['new_field']=True
        with self.assertRaises(ValueError):self.check()
        self.assertFalse(self.output.exists())

    def test_symlink_stage_root_is_not_followed(self):
        alias=self.root/'alias';alias.symlink_to(self.compiled.source,target_is_directory=True);self.spec['source']['path']='alias'
        with self.assertRaisesRegex(ValueError,'regular stage directory'):self.check()
        self.assertFalse(self.output.exists())

    def test_saved_report_reproduction_and_resealed_false_next_step(self):
        x=self.check();plan_sha=s.m.sha(self.plan_path.read_bytes())
        self.assertTrue(s.verify_report(self.root,self.plan_path,plan_sha,self.output,x['report_sha256'])['reproduced'])
        report=json.loads(self.output.read_bytes());report['next_action']='publish_automatically';self.output.write_bytes(s.m.encoded(report))
        with self.assertRaisesRegex(ValueError,'reproduction mismatch'):s.verify_report(self.root,self.plan_path,plan_sha,self.output,s.m.sha(self.output.read_bytes()))

    def test_relocation_recomputes_without_native_tools(self):
        result=self.check();copy=self.root/'relocated';copy.mkdir()
        for name in ('source','compile_binding','page_packet','visual_review'):shutil.copytree(self.root/self.spec[name]['path'],copy/self.spec[name]['path'])
        shutil.copy2(self.plan_path,copy/'plan.json');shutil.copy2(self.output,copy/'status.json')
        with patch.object(s.pages,'run',side_effect=AssertionError('no renderer')):
            self.assertTrue(s.verify_report(copy,copy/'plan.json',s.m.sha((copy/'plan.json').read_bytes()),copy/'status.json',result['report_sha256'])['reproduced'])

    def test_cli_partial_exit_and_exclusive_safe_output(self):
        for name in ('compile_binding','page_packet','visual_review'):self.spec[name]=None
        self.plan_path.write_bytes(s.m.encoded(self.spec));pin=s.m.sha(self.plan_path.read_bytes())
        result=subprocess.run([sys.executable,s.__file__,'check','--root',str(self.root),'--plan',str(self.plan_path),'--plan-sha256',pin,'--output',str(self.output)],capture_output=True)
        self.assertEqual(result.returncode,2,result.stderr)
        with self.assertRaises(FileExistsError):self.check()
        with self.assertRaises(ValueError):s.check(self.root,self.plan_path,pin,self.compiled.source/'status.json')


if __name__=='__main__':unittest.main()
