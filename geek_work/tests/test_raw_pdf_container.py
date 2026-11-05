import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_raw_pdf_pages as fixtures
import test_pdf_container as docker
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_raw_pdf_container as r
import geek_work_ocr_candidate as o


class RawContainerTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RawPDFTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root;self.output=self.root/'container';self.fake=docker.DockerFixture();self.pin=r.m.sha(r.m.encoded(r.c.profile()))
    def render(self):
        with patch.object(r.c,'capture',side_effect=self.fake.capture):return r.render(self.f.pdf,self.f.pin,self.pin,self.output)
    def test_original_pdf_preserved_no_fake_compile_binding(self):
        result=self.render();report,archive=r.verified(self.output,result['manifest_sha256'],True)
        self.assertEqual(archive['original.pdf'],self.f.pdf.read_bytes());self.assertEqual(report['source_pdf_pages'],[1]);self.assertFalse(report['compile_binding_verified']);self.assertEqual(report['renderer_backend'],'docker');self.assertFalse(report['container_escape_protection_verified']);self.assertFalse((self.output/'binding').exists());self.assertTrue(all(x['container_removed'] for x in report['container_operations']))
    def test_hash_profile_and_oversize_refused_before_execution(self):
        with patch.object(r.c,'capture',side_effect=AssertionError('no docker')):
            with self.assertRaises(ValueError):r.render(self.f.pdf,'0'*64,self.pin,self.output)
            with self.assertRaises(ValueError):r.render(self.f.pdf,self.f.pin,'0'*64,self.output)
            self.f.pdf.write_bytes(b'%PDF-'+b'x'*r.c.profile()['max_pdf_bytes'])
            with self.assertRaises(ValueError):r.render(self.f.pdf,r.m.sha(self.f.pdf.read_bytes()),self.pin,self.output)
        self.assertFalse(self.output.exists())
    def test_faults_remain_offline_verifiable_and_never_ocr_sources(self):
        for fault in ('image','network','process','bad_png','overflow','profile','create_timeout','cleanup'):
            with self.subTest(fault=fault):
                self.fake=docker.DockerFixture(fault);result=self.render();report,_=r.verified(self.output,result['manifest_sha256']);self.assertIn(report['status'],('container_render_failed','cleanup_failed'))
                with self.assertRaises(ValueError):r.verified(self.output,result['manifest_sha256'],True)
                with self.assertRaises(ValueError):o.source(self.output,result['manifest_sha256'],1)
                shutil.rmtree(self.output)
    def test_large_document_no_silent_first_sixteen_pages(self):
        self.fake.info=b'Pages: 17\nEncrypted: no\n';result=self.render();report,_=r.verified(self.output,result['manifest_sha256']);self.assertEqual(report['status'],'container_render_failed');self.assertFalse((self.output/'pages').exists());self.assertFalse(any(s['mode']=='page' for s in self.fake.states.values()))
    def test_complete_two_page_mapping_and_original_stdin(self):
        self.fake.info=b'Pages: 2\nEncrypted: no\n';result=self.render();report,_=r.verified(self.output,result['manifest_sha256'],True);self.assertEqual(report['source_pdf_pages'],[1,2]);self.assertTrue(report['full_document_coverage'])
        inputs=[data for args,data,_,_ in self.fake.commands if args[:2]==['docker','start'] and data];self.assertEqual(len(inputs),3);self.assertTrue(all(data==self.f.pdf.read_bytes() for data in inputs))
    def reseal(self):
        path=self.output/'manifest.json';d=json.loads(path.read_bytes());d['files']={n:r.m.sha((self.output/n).read_bytes()) for n in d['files']};path.write_bytes(r.m.encoded(d));return r.m.sha(path.read_bytes())
    def test_resealed_promotion_and_added_files_rejected(self):
        self.render();p=self.output/'report.json';d=json.loads(p.read_bytes());d['compile_binding_verified']=True;p.write_bytes(r.m.encoded(d))
        with self.assertRaises(ValueError):r.verified(self.output,self.reseal())
    def test_native_packet_cannot_adopt_container_profile(self):
        result=self.f.render();path=self.f.output/'profile.json';path.write_bytes(r.m.encoded(r.c.profile()));pin=self.f.reseal()
        with self.assertRaisesRegex(ValueError,'native packet requires native profile'):r.raw.verified(self.f.output,pin)
    def test_relocated_ocr_capture_replays_without_docker_or_original(self):
        result=self.render();raw=self.root/'text';raw.write_bytes(b'$A^T$');meta=self.root/'meta';meta.write_bytes(o.m.encoded(o.template()));out=self.root/'ocr'
        c=o.capture(self.output,result['manifest_sha256'],1,raw,o.m.sha(raw.read_bytes()),meta,o.m.sha(meta.read_bytes()),out)
        moved=self.root/'relocated';moved.mkdir();shutil.move(self.output,moved/'packet');shutil.move(out,moved/'candidate');self.f.pdf.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):self.assertTrue(o.verify(moved/'packet',result['manifest_sha256'],moved/'candidate',c['manifest_sha256'])['integrity_reproduced'])
    def test_diagnostics_kept_and_no_native_fallback(self):
        self.fake.fault='diagnostic'
        with patch.object(r.raw.p,'run',side_effect=AssertionError('no native')):result=self.render()
        report,_=r.verified(self.output,result['manifest_sha256'],True);self.assertTrue(report['renderer_diagnostics_present']);self.assertTrue(report['diagnostics_review_required'])
    def test_cli_offline_success_and_failure_distinguish_review_and_error(self):
        for fault,code in [(None,2),('cleanup',3)]:
            self.fake=docker.DockerFixture(fault);result=self.render();p=subprocess.run([sys.executable,r.__file__,'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True);self.assertEqual(p.returncode,code,p.stderr);self.assertTrue(json.loads(p.stdout)['integrity_reproduced']);shutil.rmtree(self.output)

if __name__=='__main__':unittest.main()
