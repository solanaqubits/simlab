import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_release_compile as b
import test_latex_verify as fixtures


class ReleaseCompileTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.LatexArchiveTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.source=self.root/'public';self.request=self.root/'request';self.out=self.root/'binding'
        self.write_source({'main.tex':self.f.data['sources/main.tex']});self.req=b.prepare(self.source,self.source_pin,self.request)

    def write_source(self,blobs,entry='main.tex'):
        if self.source.exists():shutil.rmtree(self.source)
        files=b.release.public_files(entry,blobs);b.tree.write_tree(self.source,files);self.source_pin=b.m.sha(files['manifest.json'])

    def bind(self):return b.bind(self.request,self.req['manifest_sha256'],self.f.bundle,self.f.anchor,self.out)

    def failure(self,drift=False):
        receipt=json.loads(self.f.data['receipt.json']);receipt.update(status='timeout',timed_out=True,worker_exit_code=None,client_exit_code=None)
        for key in ('engine_exit_codes','diagnostics_review_required','pdf_sha256'):receipt.pop(key)
        self.f.data={n:x for n,x in self.f.data.items() if n in ('request.json','runtime.json') or n.startswith('sources/')}
        self.f.data['receipt.json']=b.m.encoded(receipt)
        if drift:self.f.data['sources/main.tex']+=b'changed'
        shutil.rmtree(self.f.bundle);self.f.bundle.mkdir();self.f.seal()

    def reseal(self,path,**changes):
        p=path/'manifest.json';spec=json.loads(p.read_bytes());spec.update(changes);spec['files']={n:b.m.sha((path/n).read_bytes()) for n in spec['files']};p.write_bytes(b.m.encoded(spec));return b.m.sha(p.read_bytes())

    def test_clean_binding_and_request_reproduction(self):
        q=b.verify_request(self.request,self.req['manifest_sha256']);self.assertEqual(q['request_sha256'],b.m.sha(self.f.data['request.json']))
        r=self.bind();self.assertEqual(r['status'],b.CLEAN);v=b.verify_binding(self.out,r['manifest_sha256']);self.assertTrue(v['source_bytes_match'])
        self.assertEqual(v['pdf']['sha256'],b.m.sha(self.f.artifacts['document.pdf']));self.assertFalse(v['pdf_visual_review']);self.assertFalse(v['compilation_replayed']);self.assertFalse(v['publication_authorized'])

    def test_warning_is_preserved_in_report_and_exit_codes(self):
        self.f.warning();r=self.bind();self.assertEqual(r['status'],'source_bound_compile_needs_review')
        out=subprocess.run([sys.executable,b.__file__,'verify-binding','--bundle',str(self.out),'--sha256',r['manifest_sha256']],capture_output=True)
        self.assertEqual(out.returncode,2,out.stderr);self.assertIsNotNone(json.loads(out.stdout)['pdf'])
        second=self.root/'second';out=subprocess.run([sys.executable,b.__file__,'bind','--request-bundle',str(self.request),'--request-sha256',self.req['manifest_sha256'],'--compile-bundle',str(self.f.bundle),'--compile-sha256',self.f.anchor,'--output',str(second)],capture_output=True);self.assertEqual(out.returncode,2,out.stderr)

    def test_failure_is_retained_without_pdf_promotion(self):
        self.failure();r=self.bind();self.assertEqual(r['status'],'source_bound_failure_archive');self.assertIsNone(r['pdf'])
        report=json.loads((self.out/'report.json').read_bytes());self.assertFalse(report['compile_archive_check']['compiled_profile_checked'])
        out=subprocess.run([sys.executable,b.__file__,'verify-binding','--bundle',str(self.out),'--sha256',r['manifest_sha256']],capture_output=True);self.assertEqual(out.returncode,2,out.stderr)

    def test_failure_with_drift_is_not_source_bound(self):
        self.failure(True)
        with self.assertRaisesRegex(ValueError,'source bytes differ'):self.bind()
        self.assertFalse(self.out.exists())

    def test_alternative_source_version_rejected(self):
        self.write_source({'main.tex':self.f.data['sources/main.tex']+b'%changed'});shutil.rmtree(self.request);self.req=b.prepare(self.source,self.source_pin,self.request)
        with self.assertRaisesRegex(ValueError,'request contract differs'):self.bind()
        self.assertFalse(self.out.exists())

    def test_same_bytes_at_different_entry_is_not_same_compile(self):
        self.write_source({'other.tex':self.f.data['sources/main.tex']},'other.tex');shutil.rmtree(self.request);self.req=b.prepare(self.source,self.source_pin,self.request)
        with self.assertRaisesRegex(ValueError,'request contract differs'):self.bind()

    def test_uncompiled_selected_asset_rejected(self):
        self.write_source({'main.tex':self.f.data['sources/main.tex'],'picture.png':b'opaque'});shutil.rmtree(self.request);self.req=b.prepare(self.source,self.source_pin,self.request)
        with self.assertRaisesRegex(ValueError,'request contract differs'):self.bind()

    def test_equivalent_request_encoding_keeps_distinct_hashes(self):
        raw=json.dumps(json.loads(self.f.data['request.json']),separators=(',',':')).encode();self.f.data['request.json']=raw
        self.f.change('receipt.json',lambda x:x.update(request_sha256=b.m.sha(raw)))
        self.assertEqual(self.f.check()['status'],'compiled_bundle_consistent')
        self.bind();report=json.loads((self.out/'report.json').read_bytes());self.assertTrue(report['request_contract_matches']);self.assertFalse(report['request_bytes_identical'])
        self.assertNotEqual(report['prepared_request_sha256'],report['recorded_request_sha256'])

    def test_request_file_order_does_not_change_source_contract(self):
        blob=b'opaque';self.f.data['sources/picture.png']=blob
        req=json.loads(self.f.data['request.json']);req['files'].insert(0,dict(path='picture.png',sha256=b.m.sha(blob)));self.f.data['request.json']=b.m.encoded(req)
        self.f.change('receipt.json',lambda x:x.update(request_sha256=b.m.sha(self.f.data['request.json'])))
        self.write_source({'main.tex':self.f.data['sources/main.tex'],'picture.png':blob});shutil.rmtree(self.request);self.req=b.prepare(self.source,self.source_pin,self.request)
        self.bind();self.assertFalse(json.loads((self.out/'report.json').read_bytes())['request_bytes_identical'])

    def test_old_public_directory_changes_do_not_change_request_snapshot(self):
        (self.source/'files/main.tex').write_bytes(b'New unrelated version');self.bind();self.assertEqual((self.out/'request/source-package/files/main.tex').read_bytes(),self.f.data['sources/main.tex'])

    def test_request_tamper_and_wrong_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,'anchor'):b.verify_request(self.request,'0'*64)
        path=self.request/'binding.json';spec=json.loads(path.read_bytes());spec['privacy_verified']=True;path.write_bytes(b.m.encoded(spec));pin=self.reseal(self.request)
        with self.assertRaisesRegex(ValueError,'request bundle hashes'):b.verify_request(self.request,pin)

    def test_resealed_report_cannot_promote_visual_review(self):
        self.bind();p=self.out/'report.json';x=json.loads(p.read_bytes());x['pdf_visual_review']=True;p.write_bytes(b.m.encoded(x));pin=self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'binding file hashes'):b.verify_binding(self.out,pin)

    def test_resealed_nested_pdf_must_match_worker_capture(self):
        self.bind();(self.out/'compile/artifacts/document.pdf').write_bytes(b'%PDF-forged')
        inner=self.reseal(self.out/'compile');outer=self.reseal(self.out,compile_bundle_sha256=inner)
        with self.assertRaisesRegex(ValueError,'worker/artifact'):b.verify_binding(self.out,outer)

    def test_exact_tree_and_symlink_rejection(self):
        r=self.bind();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):b.verify_binding(self.out,r['manifest_sha256'])
        (self.out/'extra').rmdir();p=self.out/'report.json';p.unlink();p.symlink_to(self.f.bundle/'receipt.json')
        with self.assertRaises(ValueError):b.verify_binding(self.out,r['manifest_sha256'])

    def test_relocation_without_processes_original_roots_or_git(self):
        r=self.bind();copy=self.root/'copy';shutil.copytree(self.out,copy)
        for folder in (self.source,self.request,self.f.bundle,self.out):shutil.rmtree(folder)
        with patch('subprocess.run',side_effect=AssertionError('no subprocess')):self.assertTrue(b.verify_binding(copy,r['manifest_sha256'])['reproduced'])
        env=dict(os.environ);env['PATH']='';out=subprocess.run([sys.executable,b.__file__,'verify-binding','--bundle',str(copy),'--sha256',r['manifest_sha256']],capture_output=True,env=env);self.assertEqual(out.returncode,0,out.stderr)

    def test_compile_limits_and_output_separation(self):
        self.write_source({'main.tex':self.f.data['sources/main.tex'],**{f'asset{i}.png':b'x' for i in range(32)}})
        with self.assertRaises(ValueError):b.prepare(self.source,self.source_pin,self.root/'too-many')
        self.write_source({'main.tex':self.f.data['sources/main.tex']})
        with patch.object(b.latex.c.common,'MAX_TOTAL',1),self.assertRaisesRegex(ValueError,'compile source byte limit'):b.prepare(self.source,self.source_pin,self.root/'too-large')
        with self.assertRaises(ValueError):b.prepare(self.source,self.source_pin,self.source/'output')
        with self.assertRaises(ValueError):b.bind(self.request,self.req['manifest_sha256'],self.f.bundle,self.f.anchor,self.f.bundle/'output')


if __name__=='__main__':unittest.main()
