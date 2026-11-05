import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_pages as p
import test_release_compile as fixtures


def png(width=1,height=1):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff'))+chunk(b'IEND',b'')


class PdfPageTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReleaseCompileTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root
        self.binding=self.f.out;self.anchor=self.f.bind()['manifest_sha256'];self.output=self.root/'pages'
        self.runtime=dict(schema='geek-work-pdf-renderer-profile-1',tools={n:dict(path='/unavailable/'+n,sha256='0'*64,version='Synthetic fixture') for n in ('pdfinfo','pdftoppm')},dpi=96,max_pages=16,max_pixels=16_000_000,memory_bytes=512*1024*1024,process_timeout_seconds=15,total_timeout_seconds=60,shared_libraries_pinned=False,os_sandboxed=False)
        self.renderer_anchor=p.m.sha(p.m.encoded(self.runtime));self.calls=[];self.info=b'Pages: 1\nEncrypted: no\n'

    def worker(self,args,cwd=None,timeout=None):
        self.calls.append((args,cwd,timeout))
        if args[0].endswith('pdfinfo'):return self.info,b''
        (cwd/(args[-1]+'.png')).write_bytes(png());return b'',b''

    def render(self):
        with patch.object(p,'profile',return_value=self.runtime),patch.object(p,'run',side_effect=self.worker):
            return p.render(self.binding,self.anchor,self.renderer_anchor,self.output)

    def reseal(self):
        f=self.output/'manifest.json';x=json.loads(f.read_bytes());x['files']={n:p.m.sha((self.output/n).read_bytes()) for n in x['files']};f.write_bytes(p.m.encoded(x));return p.m.sha(f.read_bytes())

    def test_render_binds_pdf_and_page_with_fixed_arguments(self):
        pdf=(self.binding/'compile/artifacts/document.pdf').read_bytes();r=self.render();report=json.loads((self.output/'report.json').read_bytes())
        self.assertEqual(report['pdf']['sha256'],p.m.sha(pdf));self.assertEqual(report['pages']['0001.png']['width'],1);self.assertFalse(r['pdf_visual_review'])
        self.assertEqual(self.calls[1][0][1:],['-f','1','-l','1','-r','96','-png','-singlefile','input.pdf','page-0001']);self.assertFalse(self.calls[0][1].exists())
        self.assertEqual((self.binding/'compile/artifacts/document.pdf').read_bytes(),pdf)

    def test_multi_page_exact_coverage(self):
        self.info=b'Pages: 2\nEncrypted: no\n';r=self.render();self.assertEqual(r['page_count'],2);self.assertTrue((self.output/'pages/0002.png').exists())
        self.assertEqual(p.verify(self.output,r['manifest_sha256'])['page_count'],2)

    def test_warning_binding_is_preserved(self):
        shutil.rmtree(self.binding);self.f.f.warning();self.anchor=self.f.bind()['manifest_sha256'];r=self.render()
        self.assertEqual(r['source_binding_status'],'source_bound_compile_needs_review');self.assertTrue(json.loads((self.output/'report.json').read_bytes())['diagnostics_review_required'])

    def test_failure_binding_is_not_rendered(self):
        shutil.rmtree(self.binding);self.f.failure();self.anchor=self.f.bind()['manifest_sha256']
        with patch.object(p,'profile',side_effect=AssertionError('no runtime')),self.assertRaisesRegex(ValueError,'compiled PDF'):p.render(self.binding,self.anchor,self.renderer_anchor,self.output)
        self.assertFalse(self.output.exists())

    def test_profile_pin_and_missing_tools_fail(self):
        with patch.object(p,'profile',return_value=self.runtime),self.assertRaisesRegex(ValueError,'profile anchor'):p.render(self.binding,self.anchor,'0'*64,self.output)
        with patch.object(p.shutil,'which',return_value=None),self.assertRaisesRegex(ValueError,'tool missing'):p.profile()
        self.assertFalse(self.output.exists())

    def test_encryption_ambiguity_and_page_count_caps(self):
        for data in (b'Pages: 1\nEncrypted: yes\n',b'Pages: 17\nEncrypted: no\n',b'Pages: 0\nEncrypted: no\n',b'Pages: 1\nPages: 2\nEncrypted: no\n'):
            with self.subTest(data=data),self.assertRaises(ValueError):p.page_count(data)

    def test_process_failure_cleans_temp_without_completed_packet(self):
        def fail(args,cwd=None,timeout=None):
            self.calls.append((args,cwd,timeout))
            if args[0].endswith('pdfinfo'):return self.info,b''
            raise subprocess.TimeoutExpired(args,timeout)
        with patch.object(p,'profile',return_value=self.runtime),patch.object(p,'run',side_effect=fail),self.assertRaises(subprocess.TimeoutExpired):p.render(self.binding,self.anchor,self.renderer_anchor,self.output)
        self.assertFalse(self.output.exists());self.assertFalse(self.calls[-1][1].exists())

    def test_total_renderer_deadline_prevents_next_page(self):
        with patch.object(p.time,'monotonic',side_effect=[0,p.TOTAL_TIMEOUT+1]),self.assertRaisesRegex(ValueError,'total renderer timeout'):self.render()
        self.assertFalse(self.output.exists());self.assertFalse(self.calls[0][1].exists())

    def test_bad_png_or_pixel_bounds_refuse_packet(self):
        for raw in (b'bad',png()+b'trailing',png(8193,1),png(8192,8192),png()[:-1]):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):p.png(raw)
        raw=bytearray(png());raw[29]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):p.png(bytes(raw))

    def test_total_image_limit(self):
        with patch.object(p,'MAX_IMAGES',1),self.assertRaisesRegex(ValueError,'total limit'):self.render()
        self.assertFalse(self.output.exists())

    def test_resealed_report_cannot_claim_visual_acceptance(self):
        self.render();f=self.output/'report.json';x=json.loads(f.read_bytes());x['pdf_visual_review']=True;f.write_bytes(p.m.encoded(x));pin=self.reseal()
        with self.assertRaisesRegex(ValueError,'page packet hashes'):p.verify(self.output,pin)

    def test_page_tamper_missing_or_extra_files_rejected(self):
        r=self.render();f=self.output/'pages/0001.png';raw=f.read_bytes();f.write_bytes(png(2,1))
        with self.assertRaises(ValueError):p.verify(self.output,r['manifest_sha256'])
        f.write_bytes(raw);(self.output/'extra').mkdir()
        with self.assertRaises(ValueError):p.verify(self.output,r['manifest_sha256'])
        (self.output/'extra').rmdir();f.unlink()
        with self.assertRaises(ValueError):p.verify(self.output,r['manifest_sha256'])

    def test_profile_promotion_rejected(self):
        self.render();f=self.output/'profile.json';x=json.loads(f.read_bytes());x['os_sandboxed']=True;f.write_bytes(p.m.encoded(x));pin=self.reseal()
        with self.assertRaisesRegex(ValueError,'unsupported renderer guarantees'):p.verify(self.output,pin)

    def test_relocation_verifies_without_native_tools_or_original_inputs(self):
        r=self.render();copy=self.root/'relocated';shutil.copytree(self.output,copy)
        for path in (self.binding,self.output,self.f.source,self.f.request):shutil.rmtree(path)
        with patch.object(p,'run',side_effect=AssertionError('no native command')),patch.object(p,'profile',side_effect=AssertionError('no installed runtime')):
            self.assertEqual(p.verify(copy,r['manifest_sha256'])['status'],'page_packet_consistent')

    def test_output_separation_and_existing_output(self):
        with self.assertRaises(ValueError):p.render(self.binding,self.anchor,self.renderer_anchor,self.binding/'pages')
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError,'new page output'):self.render()

    def test_renderer_diagnostics_are_preserved_for_review(self):
        old=self.worker
        def warning(args,cwd=None,timeout=None):
            result=old(args,cwd,timeout)
            return (result[0],b'Fixture font diagnostic') if args[0].endswith('pdftoppm') else result
        with patch.object(self,'worker',warning):r=self.render()
        self.assertEqual((self.output/'diagnostics/0001.stderr').read_bytes(),b'Fixture font diagnostic')
        self.assertTrue(json.loads((self.output/'report.json').read_bytes())['renderer_diagnostics_present']);p.verify(self.output,r['manifest_sha256'])

    def test_native_runner_bounds_captures_and_exit_status(self):
        out,err=p.run([sys.executable,'-c','print("fixture")']);self.assertEqual(out,b'fixture\n')
        with self.assertRaisesRegex(ValueError,'process failed'):p.run([sys.executable,'-c','raise SystemExit(2)'])
        with self.assertRaisesRegex(ValueError,'capture limit'):p.run([sys.executable,'-c','print("x"*70000)'])


if __name__=='__main__':unittest.main()
