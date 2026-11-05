import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_typst_gate as g
import test_compile_verify as fixtures


class TypstGateTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ArchiveVerificationTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.project=self.root/'project';self.project.mkdir();(self.project/'main.typ').write_bytes(self.f.input)
        self.selection=self.root/'selection.json';self.selection.write_bytes(g.m.encoded(dict(schema='geek-work-typst-preflight-selection-1',entry='main.typ',files=['main.typ'])))
        self.preflight=self.root/'preflight';self.pin=g.pre.check(self.project,self.selection,g.m.sha(self.selection.read_bytes()),self.preflight)['manifest_sha256'];self.out=self.root/'gate'

    def bind(self):return g.bind(self.preflight,self.pin,self.f.bundle,self.f.anchor,self.out)
    def fake_build(self,root,request,pin,output):
        self.assertEqual((root/'main.typ').read_bytes(),self.f.input);self.assertEqual(g.m.sha(request.read_bytes()),pin)
        shutil.copytree(self.f.bundle,output);return dict(manifest_sha256=self.f.anchor)
    def reseal(self):
        p=self.out/'manifest.json';spec=json.loads(p.read_bytes());spec['files']={n:g.m.sha((self.out/n).read_bytes()) for n in spec['files']};p.write_bytes(g.m.encoded(spec));return g.m.sha(p.read_bytes())

    def test_bind_and_offline_verify_match_sources(self):
        with patch.object(g.compiled.c,'build',side_effect=AssertionError('no execution')):r=self.bind();v=g.verify(self.out,r['manifest_sha256'])
        self.assertEqual(r['status'],g.CLEAN);self.assertFalse(r['compiler_invoked_here']);self.assertTrue(v['reproduced']);self.assertFalse(v['pdf_visual_review'])

    def test_run_uses_copied_snapshot_not_original_project(self):
        (self.project/'main.typ').write_bytes(b'Changed live project')
        with patch.object(g.compiled.c,'build',side_effect=self.fake_build) as build:r=g.run(self.preflight,self.pin,self.out)
        self.assertTrue(r['compiler_invoked_here']);self.assertEqual(build.call_count,1);self.assertEqual((self.project/'main.typ').read_bytes(),b'Changed live project')
        g.verify(self.out,r['manifest_sha256'])

    def test_review_required_refuses_before_builder_or_output(self):
        shutil.rmtree(self.preflight);(self.project/'main.typ').write_bytes(b'#include filename')
        self.pin=g.pre.check(self.project,self.selection,g.m.sha(self.selection.read_bytes()),self.preflight)['manifest_sha256']
        with patch.object(g.compiled.c,'build',side_effect=AssertionError('must not run')),self.assertRaisesRegex(ValueError,'PREFLIGHT_REVIEW_REQUIRED'):g.run(self.preflight,self.pin,self.out)
        self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_REVIEW_REQUIRED'):self.bind()

    def test_bad_preflight_pin_refuses_before_builder(self):
        with patch.object(g.compiled.c,'build',side_effect=AssertionError('must not run')),self.assertRaises(ValueError):g.run(self.preflight,'0'*64,self.out)
        self.assertFalse(self.out.exists())

    def test_individually_consistent_wrong_compile_is_rejected(self):
        value=self.f.input+b'New version';self.f.data['sources/main.typ']=value
        req=json.loads(self.f.data['request.json']);req['files'][0]['sha256']=g.m.sha(value);self.f.data['request.json']=g.m.encoded(req)
        self.f.change('receipt.json',lambda x:x.update(request_sha256=g.m.sha(self.f.data['request.json'])))
        self.assertEqual(g.compiled.verify(self.f.bundle,self.f.anchor)['status'],'compiled_bundle_consistent')
        with self.assertRaisesRegex(ValueError,'COMPILE_REQUEST_MISMATCH'):self.bind()
        self.assertFalse(self.out.exists())

    def test_equivalent_request_encoding_keeps_distinct_hashes(self):
        self.f.data['request.json']=json.dumps(json.loads(self.f.data['request.json']),separators=(',',':')).encode()
        self.f.change('receipt.json',lambda x:x.update(request_sha256=g.m.sha(self.f.data['request.json'])))
        self.bind();report=json.loads((self.out/'report.json').read_bytes());self.assertFalse(report['request_bytes_identical'])

    def test_nonempty_compile_log_requires_review_and_exit_two(self):
        self.f.data['compiler.log']=b'Warning: fixture';self.f.seal();r=self.bind();self.assertEqual(r['status'],'preflight_bound_typst_compile_needs_review')
        out=subprocess.run([sys.executable,g.__file__,'verify','--bundle',str(self.out),'--sha256',r['manifest_sha256']],capture_output=True)
        self.assertEqual(out.returncode,2,out.stderr);self.assertIsNotNone(json.loads(out.stdout)['pdf'])

    def failure(self,drift=False):
        receipt=json.loads(self.f.data['receipt.json']);receipt.update(status='timeout',timed_out=True,exit_code=None,client_exit_code=None);receipt.pop('pdf_sha256',None)
        self.f.data={n:x for n,x in self.f.data.items() if n=='request.json' or n.startswith('sources/')};self.f.data['receipt.json']=g.m.encoded(receipt)
        if drift:self.f.data['sources/main.typ']+=b'drift'
        shutil.rmtree(self.f.bundle);self.f.bundle.mkdir();self.f.seal()

    def test_failure_archive_retains_status_and_no_pdf_promotion(self):
        self.failure();r=self.bind();self.assertEqual(r['status'],'preflight_bound_typst_failure_archive');self.assertIsNone(r['pdf']);g.verify(self.out,r['manifest_sha256'])

    def test_run_retains_complete_failure_instead_of_claiming_compiled(self):
        self.failure()
        with patch.object(g.compiled.c,'build',side_effect=self.fake_build):result=g.run(self.preflight,self.pin,self.out)
        self.assertEqual(result['status'],'preflight_bound_typst_failure_archive');self.assertTrue(result['compiler_invoked_here']);self.assertIsNone(result['pdf'])
        self.assertEqual(g.verify(self.out,result['manifest_sha256'])['status'],result['status'])

    def test_failure_with_source_drift_is_not_bound(self):
        self.failure(True)
        with self.assertRaisesRegex(ValueError,'COMPILE_SOURCE_MISMATCH'):self.bind()
        self.assertFalse(self.out.exists())

    def test_builder_exception_has_no_gate_completion_manifest(self):
        with patch.object(g.compiled.c,'build',side_effect=RuntimeError('Injected')),self.assertRaises(RuntimeError):g.run(self.preflight,self.pin,self.out)
        self.assertTrue((self.out/'preflight/manifest.json').exists());self.assertFalse((self.out/'manifest.json').exists())

    def test_copied_preflight_tamper_is_not_sealed(self):
        def changed(root,request,pin,output):
            result=self.fake_build(root,request,pin,output);(root/'main.typ').write_bytes(b'Changed snapshot');return result
        with patch.object(g.compiled.c,'build',side_effect=changed),self.assertRaises(ValueError):g.run(self.preflight,self.pin,self.out)
        self.assertFalse((self.out/'manifest.json').exists())

    def test_resealed_report_cannot_claim_visual_approval(self):
        self.bind();p=self.out/'report.json';spec=json.loads(p.read_bytes());spec['pdf_visual_review']=True;p.write_bytes(g.m.encoded(spec));pin=self.reseal()
        with self.assertRaisesRegex(ValueError,'gate artifact hashes'):g.verify(self.out,pin)

    def test_exact_archive_tree_and_nested_pdf_tamper(self):
        r=self.bind();(self.out/'extra').mkdir()
        with self.assertRaises(ValueError):g.verify(self.out,r['manifest_sha256'])
        (self.out/'extra').rmdir();(self.out/'compile/document.pdf').write_bytes(b'%PDF-forged')
        with self.assertRaises(ValueError):g.verify(self.out,r['manifest_sha256'])

    def test_relocation_verifies_without_old_roots_or_processes(self):
        r=self.bind();copy=self.root/'relocated';shutil.copytree(self.out,copy)
        for path in (self.out,self.project,self.preflight,self.f.bundle):shutil.rmtree(path)
        with patch.object(g.compiled.c,'build',side_effect=AssertionError('no compile')):self.assertTrue(g.verify(copy,r['manifest_sha256'])['reproduced'])
        env=dict(os.environ);env['PATH']='';result=subprocess.run([sys.executable,g.__file__,'verify','--bundle',str(copy),'--sha256',r['manifest_sha256']],capture_output=True,env=env)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_new_disjoint_output_required(self):
        with self.assertRaises(ValueError):g.run(self.preflight,self.pin,self.preflight/'output')
        self.out.mkdir()
        with patch.object(g.compiled.c,'build',side_effect=AssertionError('must not run')),self.assertRaisesRegex(ValueError,'new output'):g.run(self.preflight,self.pin,self.out)


if __name__=='__main__':unittest.main()
