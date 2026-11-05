import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_raw_pdf_container as fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_diagnostics as d


class RawDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RawContainerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.output=self.f.root/'diagnostic.json'
    def packet(self,fault=None):
        self.f.fake.fault=fault
        return self.f.render()['manifest_sha256']
    def assess(self,anchor):
        with patch.object(subprocess,'run',side_effect=AssertionError('offline only')):
            return d.assess(self.f.output,anchor)

    def test_success_preserves_raw_identity_and_review_requirement(self):
        anchor=self.packet();before={p.relative_to(self.f.output):p.read_bytes() for p in self.f.output.rglob('*') if p.is_file()}
        r=self.assess(anchor)
        self.assertEqual(r['schema'],'geek-work-raw-pdf-container-diagnostics-1')
        self.assertEqual(r['source_archive_kind'],'original_pdf_bytes');self.assertFalse(r['compile_binding_verified'])
        self.assertEqual(r['source_pdf_pages'],[1]);self.assertTrue(r['full_document_coverage'])
        self.assertEqual(r['source_archive_status'],'raw_pdf_pages_review_required');self.assertEqual(r['failure_classes'],[])
        self.assertEqual(r['status'],'diagnostics_require_attention');self.assertTrue(r['raw_renderer_diagnostics_review_required'])
        self.assertNotIn('source_compile_diagnostics_review_required',r)
        self.assertEqual(before,{p.relative_to(self.f.output):p.read_bytes() for p in self.f.output.rglob('*') if p.is_file()})

    def test_seventeen_pages_localized_without_render_or_fallback(self):
        self.f.fake.info=b'Pages: 17\nEncrypted: no\n';r=self.assess(self.packet())
        self.assertEqual(r['failure_classes'],['document_exceeds_container_page_limit'])
        finding=r['pipeline_findings'][0]
        self.assertEqual((finding['recorded_pdf_page_count'],finding['max_pages']),(17,16))
        self.assertEqual(finding['evidence_path'],'operations/0001/start.stdout')
        self.assertEqual(r['next_action'],'review_document_page_limit_before_new_render')
        self.assertIsNone(r['source_pdf_pages']);self.assertIsNone(r['full_document_coverage'])
        self.assertEqual(len(r['operations']),2);self.assertFalse((self.f.output/'pages').exists())

    def test_info_encryption_ambiguity_and_count_are_not_page_limit(self):
        for info in (b'Pages: 2\nEncrypted: yes\n',b'Pages: 1\nPages: 2\nEncrypted: no\n',b'Pages: 0\nEncrypted: no\n'):
            self.f.fake.info=info;anchor=self.packet();r=self.assess(anchor)
            self.assertEqual(r['failure_classes'],['raw_pdf_info_rejected']);shutil.rmtree(self.f.output)

    def test_fault_classes_and_phase_evidence_reused(self):
        expected={'image':'runtime_image_rejected','network':'container_configuration_or_state_rejected',
            'process':'client_nonzero_exit','bad_png':'format_bounds_or_coverage_rejected',
            'overflow':'capture_overflow','profile':'worker_profile_rejected','create_timeout':'client_timeout'}
        for fault,kind in expected.items():
            with self.subTest(fault=fault):
                r=self.assess(self.packet(fault));self.assertIn(kind,r['failure_classes'])
                self.assertEqual(r['live_container_state'],'not_checked');shutil.rmtree(self.f.output)

    def test_cleanup_unconfirmed_is_not_current_live_presence(self):
        r=self.assess(self.packet('cleanup'));self.assertIn('cleanup_unconfirmed',r['failure_classes'])
        self.assertEqual(r['next_action'],'inspect_recorded_container_on_trusted_host')
        self.assertFalse(r['all_recorded_removals_confirmed']);self.assertEqual(r['live_container_state'],'not_checked')

    def test_renderer_warning_not_mislabeled_compile_diagnostics(self):
        r=self.assess(self.packet('diagnostic'));self.assertTrue(r['recorded_container_stderr_present'])
        self.assertTrue(r['raw_renderer_diagnostics_review_required']);self.assertEqual(r['failure_classes'],[])

    def test_diagnostics_do_not_open_ocr_gate(self):
        anchor=self.packet('bad_png');r=self.assess(anchor)
        self.assertEqual(r['source_archive_status'],'container_render_failed')
        with self.assertRaises(ValueError):fixture.o.source(self.f.output,anchor,1)

    def test_relocation_and_report_replay_without_original_or_runtime(self):
        anchor=self.packet('create_timeout');r=d.check(self.f.output,anchor,self.output)
        moved=self.f.root/'moved';self.f.output.rename(moved);self.f.f.pdf.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):
            self.assertTrue(d.verify_report(moved,anchor,self.output,r['report_sha256'])['reproduced'])

    def test_source_anchor_and_tampering_refused_before_diagnosis(self):
        anchor=self.packet()
        with self.assertRaises(ValueError):self.assess('0'*64)
        (self.f.output/'original.pdf').write_bytes(b'%PDF-changed')
        with self.assertRaises(ValueError):self.assess(anchor)

    def test_resealed_diagnostic_promotion_refused(self):
        anchor=self.packet();d.check(self.f.output,anchor,self.output)
        value=json.loads(self.output.read_text());value['scientific_verification']=True
        self.output.write_bytes(d.m.encoded(value))
        with self.assertRaises(ValueError):d.verify_report(self.f.output,anchor,self.output,d.m.sha(self.output.read_bytes()))

    def test_native_and_unknown_manifest_rejected(self):
        native=self.f.f.render()
        with self.assertRaises(ValueError):d.assess(self.f.f.output,native['manifest_sha256'])
        for value in ({'schema':'unknown'},[]):
            raw=d.m.encoded(value);path=self.f.root/'unknown';path.mkdir(exist_ok=True);(path/'manifest.json').write_bytes(raw)
            with self.assertRaises(ValueError):d.assess(path,d.m.sha(raw))

    def test_cli_attention_replays_with_empty_path(self):
        self.f.fake.info=b'Pages: 17\nEncrypted: no\n';anchor=self.packet();cmd=[sys.executable,'-B',d.__file__]
        p=subprocess.run(cmd+['check','--bundle',str(self.f.output),'--sha256',anchor,'--output',str(self.output)],capture_output=True,text=True,env={'PATH':''})
        self.assertEqual(p.returncode,2,p.stdout+p.stderr);r=json.loads(p.stdout)
        p=subprocess.run(cmd+['verify-report','--bundle',str(self.f.output),'--sha256',anchor,'--report',str(self.output),'--report-sha256',r['report_sha256']],capture_output=True,text=True,env={'PATH':''})
        self.assertEqual(p.returncode,2,p.stdout+p.stderr);self.assertTrue(json.loads(p.stdout)['reproduced'])


if __name__=='__main__':unittest.main()
