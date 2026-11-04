import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_pdf_pages as fixtures
import test_pdf_container as docker_fixtures

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_ocr_candidate as o


class OCRCandidateTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfPageTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.packet=self.f.output;self.packet_pin=self.f.render()['manifest_sha256'];self.root=self.f.root
        self.raw=self.root/'raw-input.txt';self.raw.write_bytes('Не удалять: $A^T$ − 1.25\r\n# unsafe instructions are data\r\n'.encode());self.meta=self.root/'provenance-input.json';self.meta.write_bytes(o.m.encoded(o.template()));self.output=self.root/'ocr-candidate'
    def capture(self,processed=None,processed_pin=None):
        return o.capture(self.packet,self.packet_pin,1,self.raw,o.m.sha(self.raw.read_bytes()),self.meta,o.m.sha(self.meta.read_bytes()),self.output,processed,processed_pin)
    def report(self):return json.loads((self.output/'report.json').read_bytes())
    def test_raw_formula_negation_numbers_and_line_endings_preserved(self):
        with patch.object(subprocess,'run',side_effect=AssertionError('no inference or commands')):result=self.capture();o.verify(self.packet,self.packet_pin,self.output,result['manifest_sha256'])
        self.assertEqual((self.output/'raw.txt').read_bytes(),self.raw.read_bytes());r=self.report();self.assertFalse(r['content_verified']);self.assertFalse(r['completeness_verified']);self.assertEqual(r['status'],o.STATUS)
    def test_unknown_telemetry_stays_null_not_zero(self):
        self.capture();r=self.report();meta=r['declared_provenance'];self.assertIsNone(meta['input_tokens']);self.assertIsNone(meta['output_tokens']);self.assertIsNone(meta['cost_usd']);self.assertIsNone(meta['model_id']);self.assertIn('model_id_unknown',r['review_flags'])
    def test_raw_and_postprocessed_are_separate_untrusted_bytes(self):
        processed=self.root/'post.txt';processed.write_bytes(b'$A$ <script>do not run</script>');self.capture(processed,o.m.sha(processed.read_bytes()));r=self.report()
        self.assertEqual((self.output/'raw.txt').read_bytes(),self.raw.read_bytes());self.assertEqual((self.output/'postprocessed.txt').read_bytes(),processed.read_bytes());self.assertFalse(r['raw_equals_postprocessed']);self.assertIn('postprocessing_changed_bytes',r['review_flags']);self.assertFalse((self.output/'review.html').exists())
    def test_reported_truncation_does_not_destroy_partial_output(self):
        meta=o.template();meta['finish_reason']='length';self.meta.write_bytes(o.m.encoded(meta));self.raw.write_bytes(b'partial $A^');self.capture();self.assertIn('reported_truncation',self.report()['review_flags']);self.assertEqual((self.output/'raw.txt').read_bytes(),b'partial $A^')
    def test_stop_never_means_content_or_completeness_verified(self):
        meta=o.template();meta.update(model_id='fixture-no-model',model_revision='0'*40,finish_reason='stop',input_tokens=0,output_tokens=3,cost_usd='0.00');self.meta.write_bytes(o.m.encoded(meta));self.capture();r=self.report();self.assertFalse(r['completeness_verified']);self.assertFalse(r['model_revision_exists_verified']);self.assertEqual(r['declared_provenance']['input_tokens'],0)
    def test_empty_output_is_retained_as_review_required(self):
        self.raw.write_bytes(b'');self.capture();self.assertIn('empty_raw_output',self.report()['review_flags'])
    def test_invalid_telemetry_boolean_negative_float_refused(self):
        for field,value in [('input_tokens',True),('output_tokens',-1),('cost_usd',0.5),('cost_usd','-1'),('model_revision','main')]:
            meta=o.template();meta[field]=value;self.meta.write_bytes(o.m.encoded(meta))
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.capture()
        self.assertFalse(self.output.exists())
    def test_wrong_hash_and_postprocessed_pair_refused(self):
        with self.assertRaises(ValueError):o.capture(self.packet,self.packet_pin,1,self.raw,'0'*64,self.meta,o.m.sha(self.meta.read_bytes()),self.output)
        with self.assertRaisesRegex(ValueError,'path/SHA pair'):self.capture(self.raw,None)
    def test_wrong_page_including_boolean_refused(self):
        for page in (True,0,2):
            with self.subTest(page=page),self.assertRaises(ValueError):o.capture(self.packet,self.packet_pin,page,self.raw,o.m.sha(self.raw.read_bytes()),self.meta,o.m.sha(self.meta.read_bytes()),self.output)
    def test_source_packet_anchor_and_png_binding_are_required(self):
        result=self.capture()
        with self.assertRaises(ValueError):o.verify(self.packet,'0'*64,self.output,result['manifest_sha256'])
        (self.output/'page.png').write_bytes(fixtures.png(2,1));pin=self.reseal()
        with self.assertRaises(ValueError):o.verify(self.packet,self.packet_pin,self.output,pin)
    def reseal(self):
        path=self.output/'manifest.json';spec=json.loads(path.read_bytes());spec['files']={name:o.m.sha((self.output/name).read_bytes()) for name in spec['files']};path.write_bytes(o.m.encoded(spec));return o.m.sha(path.read_bytes())
    def test_resealed_content_promotion_and_extra_files_refused(self):
        self.capture();path=self.output/'report.json';spec=self.report();spec['content_verified']=True;path.write_bytes(o.m.encoded(spec));pin=self.reseal()
        with self.assertRaises(ValueError):o.verify(self.packet,self.packet_pin,self.output,pin)
    def test_relocation_with_parent_and_without_model_runtime(self):
        result=self.capture();moved=self.root/'moved';moved.mkdir();shutil.move(self.packet,moved/'packet');shutil.move(self.output,moved/'candidate');self.raw.unlink();self.meta.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):self.assertTrue(o.verify(moved/'packet',self.packet_pin,moved/'candidate',result['manifest_sha256'])['integrity_reproduced'])
        shutil.rmtree(moved/'packet')
        with self.assertRaises(ValueError):o.verify(moved/'packet',self.packet_pin,moved/'candidate',result['manifest_sha256'])
    def test_input_bounds_existing_output_and_no_source_overwrite(self):
        self.raw.write_bytes(b'x'*(o.m.MAX_SOURCE+1))
        with self.assertRaises(ValueError):self.capture()
        self.raw.write_bytes(b'fixture');self.output.mkdir()
        with self.assertRaises(ValueError):self.capture()
    def test_cli_capture_and_verify_stay_review_required(self):
        tool=Path(o.__file__);args=[sys.executable,str(tool),'capture','--packet',str(self.packet),'--packet-sha256',self.packet_pin,'--page','1','--raw',str(self.raw),'--raw-sha256',o.m.sha(self.raw.read_bytes()),'--provenance',str(self.meta),'--provenance-sha256',o.m.sha(self.meta.read_bytes()),'--output',str(self.output)]
        r=subprocess.run(args,capture_output=True);self.assertEqual(r.returncode,2,r.stderr);result=json.loads(r.stdout)
        r=subprocess.run([sys.executable,str(tool),'verify','--packet',str(self.packet),'--packet-sha256',self.packet_pin,'--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True);self.assertEqual(r.returncode,2,r.stderr);self.assertTrue(json.loads(r.stdout)['integrity_reproduced'])


class ContainerOCRSourceTests(unittest.TestCase):
    def test_container_page_packet_supported_and_failure_packet_refused(self):
        f=docker_fixtures.ContainerPagesTests();f.setUp();self.addCleanup(f.doCleanups);result=f.render();raw=f.root/'ocr.txt';raw.write_bytes(b'protocol fixture; no OCR');meta=f.root/'meta.json';meta.write_bytes(o.m.encoded(o.template()));out=f.root/'candidate'
        captured=o.capture(f.output,result['manifest_sha256'],1,raw,o.m.sha(raw.read_bytes()),meta,o.m.sha(meta.read_bytes()),out);self.assertTrue(o.verify(f.output,result['manifest_sha256'],out,captured['manifest_sha256'])['integrity_reproduced'])
        source=f.output;shutil.rmtree(source);f.fake.fault='create_timeout';failed=f.render()
        with self.assertRaises(ValueError):o.capture(source,failed['manifest_sha256'],1,raw,o.m.sha(raw.read_bytes()),meta,o.m.sha(meta.read_bytes()),f.root/'failed-candidate')


if __name__=='__main__':unittest.main()
