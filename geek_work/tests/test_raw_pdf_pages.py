import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_pdf_pages as fixtures
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_raw_pdf_pages as r
import geek_work_ocr_candidate as o


class RawPDFTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfPageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.pdf=self.root/'original.pdf';self.pdf.write_bytes(b'%PDF-1.4\nsynthetic test fixture, not renderable\n')
        self.pin=r.m.sha(self.pdf.read_bytes());self.output=self.root/'raw-pages';self.f.info=b'Pages: 100\nEncrypted: no\n'
    def render(self,first=50,last=51,anchor=None,trusted=True):
        with patch.object(r.p,'profile',return_value=self.f.runtime),patch.object(r.p,'run',side_effect=self.f.worker):
            return r.render(self.pdf,anchor or self.pin,self.f.renderer_anchor,first,last,self.output,trusted)
    def reseal(self):
        p=self.output/'manifest.json';d=json.loads(p.read_bytes());d['files']={n:r.m.sha((self.output/n).read_bytes()) for n in d['files']};p.write_bytes(r.m.encoded(d));return r.m.sha(p.read_bytes())
    def test_selection_uses_original_numbers_preserves_pdf_without_compile_claim(self):
        result=self.render();report,_=r.verified(self.output,result['manifest_sha256'])
        self.assertEqual(report['source_pdf_pages'],[50,51]);self.assertFalse(report['full_document_coverage']);self.assertFalse(report['compile_binding_verified']);self.assertEqual(report['pdf_page_count'],100)
        self.assertEqual(self.f.calls[1][0][1:5],['-f','50','-l','50']);self.assertEqual(self.f.calls[2][0][1:5],['-f','51','-l','51'])
        self.assertEqual((self.output/'original.pdf').read_bytes(),self.pdf.read_bytes());self.assertFalse((self.output/'binding').exists())
    def test_unacknowledged_native_execution_and_wrong_anchor_do_not_start_parser(self):
        with patch.object(r.p,'profile',side_effect=AssertionError('no profile')):
            with self.assertRaisesRegex(ValueError,'acknowledgement'):r.render(self.pdf,self.pin,self.f.renderer_anchor,1,1,self.output)
            with self.assertRaisesRegex(ValueError,'anchor'):r.render(self.pdf,'0'*64,self.f.renderer_anchor,1,1,self.output,True)
        self.assertFalse(self.output.exists())
    def test_selection_limits_and_booleans(self):
        for first,last in [(True,1),(0,1),(2,1),(1,17),(100,101)]:
            with self.subTest(first=first,last=last),self.assertRaises(ValueError):self.render(first,last)
        self.assertFalse(self.output.exists())
    def test_encryption_duplicate_count_and_zero_refused(self):
        for info in [b'Pages: 1\nEncrypted: yes\n',b'Pages: 1\nPages: 2\nEncrypted: no\n',b'Pages: 0\nEncrypted: no\n']:
            with self.assertRaises(ValueError):r.total_pages(info)
    def test_incomplete_document_is_not_full_coverage(self):
        self.f.info=b'Pages: 2\nEncrypted: no\n';result=self.render(1,2);report,_=r.verified(self.output,result['manifest_sha256']);self.assertTrue(report['full_document_coverage']);self.assertFalse(report['pdf_visual_review'])
    def test_relocated_offline_verification_needs_no_input_or_runtime(self):
        result=self.render();moved=self.root/'relocated';shutil.move(self.output,moved);self.pdf.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):report,_=r.verified(moved,result['manifest_sha256'])
        self.assertEqual(report['source_pdf_pages'],[50,51])
    def test_resealed_compile_promotion_refused(self):
        self.render();p=self.output/'report.json';d=json.loads(p.read_bytes());d['compile_binding_verified']=True;p.write_bytes(r.m.encoded(d));pin=self.reseal()
        with self.assertRaises(ValueError):r.verified(self.output,pin)
    def test_resealed_page_mapping_change_refused(self):
        self.render();p=self.output/'report.json';d=json.loads(p.read_bytes());d['source_pdf_pages']=[1,2];p.write_bytes(r.m.encoded(d));pin=self.reseal()
        with self.assertRaises(ValueError):r.verified(self.output,pin)
    def test_pdf_and_png_tampering_or_extra_file_refused(self):
        result=self.render();(self.output/'original.pdf').write_bytes(b'%PDF-tampered')
        with self.assertRaises(ValueError):r.verified(self.output,self.reseal())
    def test_failure_removes_temporary_files_and_no_completed_output(self):
        def fail(args,cwd=None,timeout=None):
            self.tmp=cwd
            if args[0].endswith('pdfinfo'):return self.f.info,b''
            raise subprocess.TimeoutExpired(args,timeout)
        with patch.object(r.p,'profile',return_value=self.f.runtime),patch.object(r.p,'run',side_effect=fail),self.assertRaises(subprocess.TimeoutExpired):r.render(self.pdf,self.pin,self.f.renderer_anchor,1,1,self.output,True)
        self.assertFalse(self.output.exists());self.assertFalse(self.tmp.exists())
    def test_ocr_candidate_propagates_actual_source_page_and_replays(self):
        result=self.render();raw=self.root/'text.txt';raw.write_bytes(b'$A^T$');meta=self.root/'meta.json';meta.write_bytes(o.m.encoded(o.template()));out=self.root/'ocr'
        candidate=o.capture(self.output,result['manifest_sha256'],2,raw,o.m.sha(raw.read_bytes()),meta,o.m.sha(meta.read_bytes()),out)
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):o.verify(self.output,result['manifest_sha256'],out,candidate['manifest_sha256'])
        d=json.loads((out/'report.json').read_bytes());self.assertEqual(d['source_pdf_page'],51);self.assertEqual(d['page'],2);self.assertFalse(d['source_full_document_coverage']);self.assertFalse(d['content_verified'])
    def test_raw_packets_not_accepted_by_manuscript_page_verifier(self):
        result=self.render()
        with self.assertRaises(ValueError):r.p.verified(self.output,result['manifest_sha256'])
    def test_cli_offline_verify_returns_review_required(self):
        result=self.render();p=subprocess.run([sys.executable,r.__file__,'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True)
        self.assertEqual(p.returncode,2,p.stderr);self.assertTrue(json.loads(p.stdout)['integrity_reproduced'])

if __name__=='__main__':unittest.main()
