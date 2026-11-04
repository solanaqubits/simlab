import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_review as r
import test_pdf_pages as fixtures


class PdfReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfPageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.packet=self.f.output;self.pin=self.f.render()['manifest_sha256'];self.root=self.f.root
        self.review=self.root/'review.json';self.out=self.root/'accepted';self.packet_report,_=r.p.verified(self.packet,self.pin)
        self.spec=r.template(self.pin,self.packet_report);self.spec['reviewer']=dict(id='Synthetic reviewer',role='implementer',prior_exposure='Fixture, not independent')
        self.spec['diagnostics']=dict(status='reviewed',note='Synthetic fixture diagnostics inspected')
        for row in self.spec['pages']:
            for check in row['checks'].values():check.update(status='pass',note='Synthetic test assertion, not real visual qualification')

    def accept(self):
        self.review.write_bytes(r.m.encoded(self.spec));return r.accept(self.packet,self.pin,self.review,r.m.sha(self.review.read_bytes()),self.out)

    def reseal(self):
        p=self.out/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:r.m.sha((self.out/n).read_bytes()) for n in x['files']};p.write_bytes(r.m.encoded(x));return r.m.sha(p.read_bytes())

    def test_reported_review_is_not_verified_or_independent(self):
        x=self.accept();self.assertEqual(x['status'],r.CLEAN);self.assertFalse(x['pdf_visual_review_verified']);self.assertFalse(x['independence_verified']);self.assertFalse(x['accepted_as_gold'])
        self.assertTrue(r.verify(self.out,x['manifest_sha256'])['reproduced'])

    def test_template_has_no_default_decisions_and_is_exclusive(self):
        path=self.root/'template.json';r.make_template(self.packet,self.pin,path);spec=json.loads(path.read_bytes());self.assertIsNone(spec['reviewer']['id'])
        self.assertTrue(all(v['status'] is None for row in spec['pages'] for v in row['checks'].values()))
        with self.assertRaises(FileExistsError):r.make_template(self.packet,self.pin,path)
        self.spec=spec
        with self.assertRaises(ValueError):self.accept()
        self.assertFalse(self.out.exists())

    def test_fail_unknown_and_optional_outcomes(self):
        for value,status in [('fail','changes_requested'),('unknown','visual_review_incomplete'),('not_applicable',r.CLEAN)]:
            self.spec['pages'][0]['checks']['formulas']['status']=value
            self.assertEqual(r.assess(r.m.encoded(self.spec),self.pin,self.packet_report)['status'],status)
        self.spec['pages'][0]['checks']['legibility']['status']='not_applicable'
        with self.assertRaisesRegex(ValueError,'required check'):self.accept()

    def test_all_checks_and_reasons_required(self):
        row=self.spec['pages'][0];saved=row['checks'].pop('page_order')
        with self.assertRaises(ValueError):self.accept()
        row['checks']['page_order']=saved;saved['note']=''
        with self.assertRaises(ValueError):self.accept()

    def test_pdf_png_and_packet_anchors(self):
        for field in ('pdf_sha256','page_packet_sha256'):
            value=self.spec[field];self.spec[field]='0'*64
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'binding'):self.accept()
            self.spec[field]=value
        self.spec['pages'][0]['png_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PNG binding'):self.accept()

    def test_complete_unique_integer_page_coverage(self):
        for rows in ([],self.spec['pages']*2,[dict(self.spec['pages'][0],page=True)],[dict(self.spec['pages'][0],page=2)]):
            copy=dict(self.spec,pages=rows)
            with self.subTest(rows=rows),self.assertRaises(ValueError):r.assess(r.m.encoded(copy),self.pin,self.packet_report)

    def test_compile_warnings_cannot_be_cleared_by_check_decisions(self):
        packet=dict(self.packet_report,diagnostics_review_required=True,source_binding_status='source_bound_compile_needs_review')
        result=r.assess(r.m.encoded(self.spec),self.pin,packet);self.assertEqual(result['status'],'visual_review_reported_with_diagnostics');self.assertTrue(result['diagnostics_present'])
        self.spec['diagnostics']['status']='unresolved';self.assertEqual(r.assess(r.m.encoded(self.spec),self.pin,packet)['status'],'visual_review_incomplete')

    def test_renderer_diagnostics_cannot_be_cleared(self):
        packet=dict(self.packet_report,renderer_diagnostics_present=True)
        self.assertEqual(r.assess(r.m.encoded(self.spec),self.pin,packet)['status'],'visual_review_reported_with_diagnostics')

    def test_claimed_external_role_does_not_verify_independence(self):
        self.spec['reviewer'].update(role='external_reviewer',prior_exposure='Reviewer self-report')
        self.assertFalse(r.assess(r.m.encoded(self.spec),self.pin,self.packet_report)['independence_verified'])
        self.spec['reviewer']['prior_exposure']=None
        with self.assertRaises(ValueError):self.accept()

    def test_html_escapes_notes_and_uses_only_relative_page_images(self):
        self.spec['pages'][0]['checks']['formulas']['note']='<script>alert("fixture")</script>'
        self.accept();html=(self.out/'review.html').read_text();self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html);self.assertIn('src="page-packet/pages/0001.png"',html)
        self.assertIn("img-src 'self'",html)

    def test_resealed_report_and_preview_tampering_rejected(self):
        self.accept()
        for name in ('report.json','review.html'):
            path=self.out/name;raw=path.read_bytes();path.write_bytes(raw+b'Forged')
            pin=self.reseal()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'review archive hashes'):r.verify(self.out,pin)
            path.write_bytes(raw);self.reseal()

    def test_review_file_pin_and_output_separation(self):
        self.review.write_bytes(r.m.encoded(self.spec))
        with self.assertRaisesRegex(ValueError,'review SHA'):r.accept(self.packet,self.pin,self.review,'0'*64,self.out)
        with self.assertRaises(ValueError):r.accept(self.packet,self.pin,self.review,r.m.sha(self.review.read_bytes()),self.packet/'output')
        self.assertFalse(self.out.exists())

    def test_offline_relocation_uses_no_renderer_or_old_inputs(self):
        x=self.accept();copy=self.root/'relocated';shutil.copytree(self.out,copy)
        for path in (self.packet,self.review,self.out):
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink()
        with patch.object(r.p,'run',side_effect=AssertionError('no process')),patch.object(r.p,'profile',side_effect=AssertionError('no runtime')):
            self.assertTrue(r.verify(copy,x['manifest_sha256'])['reproduced'])

    def test_second_page_requires_its_own_decisions(self):
        shutil.rmtree(self.packet);self.f.info=b'Pages: 2\nEncrypted: no\n';self.pin=self.f.render()['manifest_sha256'];self.packet_report,_=r.p.verified(self.packet,self.pin)
        spec=r.template(self.pin,self.packet_report);spec['reviewer']=self.spec['reviewer'];spec['diagnostics']=self.spec['diagnostics']
        for row in spec['pages']:
            for check in row['checks'].values():check.update(status='pass',note='Synthetic multi-page fixture')
        spec['pages'][1]['checks']['legibility']['status']='unknown'
        self.assertEqual(r.assess(r.m.encoded(spec),self.pin,self.packet_report)['status'],'visual_review_incomplete')
        spec['pages'][1]['page']=1
        with self.assertRaisesRegex(ValueError,'unique page'):r.assess(r.m.encoded(spec),self.pin,self.packet_report)

    def test_cli_fail_and_unknown_are_not_success(self):
        for choice in ('fail','unknown'):
            self.spec['pages'][0]['checks']['references']['status']=choice;x=self.accept()
            result=subprocess.run([sys.executable,r.__file__,'verify','--bundle',str(self.out),'--sha256',x['manifest_sha256']],capture_output=True)
            self.assertEqual(result.returncode,2,result.stderr);shutil.rmtree(self.out)

    def test_extra_directory_symlink_and_bad_anchor_rejected(self):
        x=self.accept()
        with self.assertRaisesRegex(ValueError,'anchor'):r.verify(self.out,'0'*64)
        (self.out/'extra').mkdir()
        with self.assertRaises(ValueError):r.verify(self.out,x['manifest_sha256'])
        (self.out/'extra').rmdir();path=self.out/'review.json';path.unlink();path.symlink_to(self.review)
        with self.assertRaises(ValueError):r.verify(self.out,x['manifest_sha256'])


if __name__=='__main__':unittest.main()
