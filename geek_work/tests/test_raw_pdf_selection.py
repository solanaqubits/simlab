import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_raw_pdf_pages as fixtures
from test_pdf_container import DockerFixture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_raw_pdf_selection as s
import geek_work_raw_pdf_container as legacy
import geek_work_pdf_diagnostics as d
import geek_work_ocr_candidate as o


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RawPDFTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.output=self.root/'selected';self.runtime=s.c.selection_profile()
        self.pin=s.m.sha(s.m.encoded(self.runtime));self.fake=DockerFixture(runtime=self.runtime)
        self.fake.info=b'Pages: 100\nEncrypted: no\n'
    def render(self,first=50,last=51):
        with patch.object(s.c,'capture',side_effect=self.fake.capture):
            return s.render(self.f.pdf,self.f.pin,self.pin,first,last,self.output)
    def reseal(self):
        path=self.output/'manifest.json';spec=json.loads(path.read_bytes())
        spec['files']={n:s.m.sha((self.output/n).read_bytes()) for n in spec['files']}
        path.write_bytes(s.m.encoded(spec));return s.m.sha(path.read_bytes())
    def test_original_page_numbers_and_runtime_are_bound(self):
        result=self.render();r,_=s.verified(self.output,result['manifest_sha256'],True)
        self.assertEqual(r['source_pdf_pages'],[50,51]);self.assertEqual(r['pdf_page_count'],100)
        self.assertFalse(r['full_document_coverage']);self.assertFalse(r['compile_binding_verified'])
        self.assertEqual(r['renderer_backend'],'docker');self.assertEqual(r['page_count'],2)
        args=[a for a,_,_,_ in self.fake.commands if a[:2]==['docker','create']]
        self.assertEqual([a[-1] for a in args[2:]],['50','51'])
        self.assertTrue(all(x['image_id']==self.runtime['image_id'] and x['container_removed'] for x in r['container_operations']))
        self.assertEqual((self.output/'original.pdf').read_bytes(),self.f.pdf.read_bytes())
    def test_invalid_selection_rejected_before_output_and_docker(self):
        for first,last in [(True,1),(1,False),(0,1),(2,1),(1,17),(100001,100001)]:
            with self.subTest(first=first,last=last),patch.object(s.c,'capture',side_effect=AssertionError('no Docker')),self.assertRaises(ValueError):
                s.render(self.f.pdf,self.f.pin,self.pin,first,last,self.output)
            self.assertFalse(self.output.exists())
    def test_wrong_pdf_or_runtime_anchor_rejected_before_output(self):
        for pdf_pin,runtime_pin in [('0'*64,self.pin),(self.f.pin,'0'*64)]:
            with patch.object(s.c,'capture',side_effect=AssertionError('no Docker')),self.assertRaises(ValueError):
                s.render(self.f.pdf,pdf_pin,runtime_pin,1,1,self.output)
            self.assertFalse(self.output.exists())
    def test_selection_above_document_is_archived_without_page_calls(self):
        result=self.render(101,101);r,_=s.verified(self.output,result['manifest_sha256'])
        self.assertEqual(r['status'],'container_render_failed');self.assertEqual(r['requested_source_pages'],[101])
        self.assertEqual(len(r['operations']),2);self.assertFalse((self.output/'pages').exists())
        with self.assertRaises(ValueError):o.source(self.output,result['manifest_sha256'],1)
        diag=d.assess(self.output,result['manifest_sha256']);self.assertIn('format_bounds_or_coverage_rejected',diag['failure_classes'])
    def test_unencrypted_unambiguous_info_required(self):
        for info in [b'Pages: 100\nEncrypted: yes\n',b'Pages: 100\nPages: 100\nEncrypted: no\n',b'Pages: 100001\nEncrypted: no\n']:
            self.fake.info=info;result=self.render();r,_=s.verified(self.output,result['manifest_sha256'])
            self.assertEqual(r['status'],'container_render_failed');self.assertEqual(len(r['operations']),2)
            shutil.rmtree(self.output)
    def test_exact_sixteen_and_upper_source_limit_supported(self):
        self.fake.info=b'Pages: 100000\nEncrypted: no\n';result=self.render(99985,100000)
        r,_=s.verified(self.output,result['manifest_sha256'],True)
        self.assertEqual(r['source_pdf_pages'],list(range(99985,100001)));self.assertEqual(len(r['container_operations']),18)
    def test_full_coverage_only_when_actual_document_selected(self):
        self.fake.info=b'Pages: 2\nEncrypted: no\n';result=self.render(1,2)
        self.assertTrue(s.verified(self.output,result['manifest_sha256'],True)[0]['full_document_coverage'])
    def test_no_docker_or_original_needed_for_relocated_replay(self):
        result=self.render();moved=self.root/'relocated';shutil.move(self.output,moved);self.f.pdf.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):
            r,_=s.verified(moved,result['manifest_sha256'],True);diag=d.assess(moved,result['manifest_sha256'])
        self.assertEqual(r['source_pdf_pages'],[50,51]);self.assertEqual(diag['failure_classes'],[])
        self.assertEqual(diag['requested_source_pages'],[50,51]);self.assertEqual(diag['live_container_state'],'not_checked')
    def test_failed_page_or_cleanup_cannot_enter_ocr(self):
        for fault in ['process','bad_png','overflow','cleanup','create_timeout','image','profile','network']:
            with self.subTest(fault=fault):
                self.fake=DockerFixture(fault,runtime=self.runtime);self.fake.info=b'Pages: 100\nEncrypted: no\n'
                result=self.render();r,_=s.verified(self.output,result['manifest_sha256'])
                self.assertIn(r['status'],['container_render_failed','cleanup_failed'])
                with self.assertRaises(ValueError):o.source(self.output,result['manifest_sha256'],1)
                self.assertTrue(d.assess(self.output,result['manifest_sha256'])['failure_classes'])
                shutil.rmtree(self.output)
    def test_ocr_maps_packet_ordinal_to_source_page(self):
        result=self.render();raw=self.root/'ocr.txt';raw.write_bytes(b'x^2 + y')
        meta=self.root/'meta.json';meta.write_bytes(s.m.encoded(o.template()));out=self.root/'ocr'
        candidate=o.capture(self.output,result['manifest_sha256'],2,raw,s.m.sha(raw.read_bytes()),meta,s.m.sha(meta.read_bytes()),out)
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):o.verify(self.output,result['manifest_sha256'],out,candidate['manifest_sha256'])
        r=json.loads((out/'report.json').read_bytes());self.assertEqual(r['source_pdf_page'],51)
        self.assertFalse(r['source_full_document_coverage']);self.assertFalse(r['model_called_here'])
        self.assertFalse(r['content_verified'])
    def test_mapping_and_report_promotion_reseal_rejected(self):
        result=self.render();path=self.output/'report.json';saved=path.read_bytes()
        for key,value in [('source_pdf_pages',[1,2]),('full_document_coverage',True),('compile_binding_verified',True)]:
            r=json.loads(saved);r[key]=value;path.write_bytes(s.m.encoded(r))
            with self.assertRaises(ValueError):s.verified(self.output,self.reseal())
        path.write_bytes(saved)
    def test_manifest_selection_change_cannot_relabel_existing_operations(self):
        self.render();path=self.output/'manifest.json';spec=json.loads(path.read_bytes());spec.update(first_page=1,last_page=2)
        path.write_bytes(s.m.encoded(spec))
        with self.assertRaisesRegex(ValueError,'operation order'):s.verified(self.output,s.m.sha(path.read_bytes()))
    def test_page_command_tamper_cannot_be_resealed(self):
        self.render();path=self.output/'operations/0002/create.json';r=json.loads(path.read_bytes());r['argv'][-1]='1';path.write_bytes(s.m.encoded(r))
        with self.assertRaises(ValueError):s.verified(self.output,self.reseal())
    def test_legacy_profile_cannot_replace_selection_profile(self):
        self.render();(self.output/'profile.json').write_bytes(s.m.encoded(s.c.profile()))
        with self.assertRaises(ValueError):s.verified(self.output,self.reseal())
        with self.assertRaises(ValueError):s.c.validate_profile(self.runtime)
    def test_legacy_verifiers_do_not_accept_selection_schema(self):
        result=self.render()
        for verify in [legacy.verified,s.c.verified,s.raw.verified]:
            with self.assertRaises(ValueError):verify(self.output,result['manifest_sha256'])
    def test_unknown_runtime_rejected(self):
        altered=copy.deepcopy(self.runtime);altered['max_source_page']=100001
        with self.assertRaises(ValueError):s.c.execute(self.root/'never','page',b'',50,runtime=altered)
        self.assertFalse((self.root/'never').exists())
    def test_legacy_worker_page_limit_unchanged(self):
        with patch.object(s.c,'capture',side_effect=AssertionError('no Docker')),self.assertRaises(ValueError):s.c.execute(self.root/'never','page',b'',17)
        self.assertFalse((self.root/'never').exists())
    def test_profile_matches_worker_source_and_pinned_parent(self):
        root=Path(s.c.PROFILE_FILE).parent
        self.assertEqual(self.runtime['worker_sha256'],s.m.sha((root/'selection/worker.py').read_bytes()))
        self.assertEqual(self.runtime['base_image_id'],s.c.profile()['image_id'])
        self.assertNotEqual(self.runtime['image_id'],s.c.profile()['image_id'])
    def test_cli_replay_exit_is_review_required(self):
        result=self.render();run=subprocess.run([sys.executable,s.__file__,'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True)
        self.assertEqual(run.returncode,2,run.stderr);self.assertTrue(json.loads(run.stdout)['integrity_reproduced'])
    def test_deadline_without_operations_is_failure_not_empty_success(self):
        with patch.object(s.c,'TOTAL_TIMEOUT',0):result=self.render()
        report,_=s.verified(self.output,result['manifest_sha256'])
        self.assertEqual(report['status'],'container_render_failed');self.assertEqual(report['operations'],[])
        self.assertIn('incomplete_pipeline',d.assess(self.output,result['manifest_sha256'])['failure_classes'])
        with self.assertRaises(ValueError):o.source(self.output,result['manifest_sha256'],1)
    def test_second_page_failure_never_exposes_successful_prefix_to_ocr(self):
        capture=self.fake.capture
        def fail_second(args,*a,**kw):
            if args[:2]==['docker','create'] and args[-2:]==['page','51']:self.fake.fault='process'
            return capture(args,*a,**kw)
        with patch.object(s.c,'capture',side_effect=fail_second):
            result=s.render(self.f.pdf,self.f.pin,self.pin,50,51,self.output)
        report,_=s.verified(self.output,result['manifest_sha256'])
        self.assertEqual([row['status'] for row in report['operations']],['completed']*3+['failed'])
        self.assertFalse((self.output/'pages').exists())
        with self.assertRaises(ValueError):o.source(self.output,result['manifest_sha256'],1)
    def test_selection_worker_passes_original_page_and_enforces_own_limit(self):
        import importlib.util
        import io
        from types import SimpleNamespace
        path=Path(s.c.PROFILE_FILE).parent/'selection/worker.py'
        spec=importlib.util.spec_from_file_location('selection_worker_fixture',path)
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        with patch.object(worker.sys,'argv',['worker','page','100000']),patch.object(worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(b'%PDF-fixture'))),patch.object(worker.sys,'stdout',SimpleNamespace(buffer=io.BytesIO())),patch.object(worker.sys,'stderr',SimpleNamespace(buffer=io.BytesIO())),patch.object(worker,'run',return_value=(b'PNG fixture',b'')) as run:
            worker.main();self.assertEqual(run.call_args.args[0][1:5],['-f','100000','-l','100000'])
        for number in ['0','100001','-1','1.0']:
            with patch.object(worker.sys,'argv',['worker','page',number]),patch.object(worker,'run',side_effect=AssertionError('no parser')),self.assertRaises(ValueError):worker.main()
    def test_extra_file_rejected(self):
        result=self.render();(self.output/'unexpected').write_bytes(b'x')
        with self.assertRaises(ValueError):s.verified(self.output,result['manifest_sha256'])


if __name__=='__main__':unittest.main()
