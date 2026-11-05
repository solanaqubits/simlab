import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_runtime_context as c
spec=importlib.util.spec_from_file_location('pdf_container_worker',c.RUNTIME/'container/worker.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


class RuntimeContextTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.runtime=self.root/'recipe';(self.runtime/'container').mkdir(parents=True);self.cache=self.root/'cache';self.cache.mkdir();self.bootstrap=self.root/'bootstrap';self.bootstrap.write_bytes(b'fixture bootstrap')
        self.archive=self.cache/'fixture-1-0.conda';self.archive.write_bytes(b'fixture archive')
        lock=c.m.encoded(dict(platform='linux-64',selected_version='25.12.0',packages=[dict(url='https://example.invalid/fixture-1-0.conda',sha256=c.m.sha(self.archive.read_bytes()))]))
        (self.runtime/'poppler-25.12.0-linux-64.lock.json').write_bytes(lock)
        for name in ('Dockerfile','worker.py'):shutil.copyfile(c.RUNTIME/'container'/name,self.runtime/'container'/name)
        for name,value in (('RUNTIME',self.runtime),('LOCK_SHA',c.m.sha(lock)),('BOOTSTRAP_SHA',c.m.sha(self.bootstrap.read_bytes()))):
            patcher=patch.object(c,name,value);patcher.start();self.addCleanup(patcher.stop)
        self.output=self.root/'context'

    def prepare(self):return c.prepare(self.cache,self.bootstrap,self.output)

    def test_exact_context_no_commands_and_not_a_built_image(self):
        with patch.object(subprocess,'run',side_effect=AssertionError('no execution')):result=self.prepare();checked=c.verify(self.output,result['manifest_sha256'])
        self.assertEqual(checked['status'],'offline_runtime_context_consistent');self.assertFalse(result['image_built']);self.assertEqual((self.output/'packages'/self.archive.name).read_bytes(),self.archive.read_bytes())

    def test_wrong_bootstrap_refused_before_output(self):
        self.bootstrap.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'micromamba SHA'):self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_missing_or_symlink_package_refused(self):
        raw=self.archive.read_bytes();self.archive.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'package SHA'):self.prepare()
        self.archive.unlink()
        with self.assertRaises(ValueError):self.prepare()
        other=self.root/'other';other.write_bytes(raw);self.archive.symlink_to(other)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists())

    def test_changed_lock_requires_reviewed_new_pin(self):
        (self.runtime/'poppler-25.12.0-linux-64.lock.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'lock changed'):self.prepare()

    def test_context_limit_disjointness_and_existing_output(self):
        with patch.object(c,'MAX_TOTAL',1),self.assertRaisesRegex(ValueError,'byte limit'):self.prepare()
        with self.assertRaises(ValueError):c.prepare(self.cache,self.bootstrap,self.cache/'inside')
        self.output.mkdir()
        with self.assertRaises(ValueError):self.prepare()

    def test_relocation_without_original_cache_or_bootstrap(self):
        result=self.prepare();moved=self.root/'relocated';shutil.copytree(self.output,moved);shutil.rmtree(self.output);shutil.rmtree(self.cache);self.bootstrap.unlink()
        self.assertEqual(c.verify(moved,result['manifest_sha256'])['packages'],1)

    def test_wrong_anchor_extra_paths_and_resealed_promotion_refused(self):
        result=self.prepare()
        with self.assertRaises(ValueError):c.verify(self.output,'0'*64)
        (self.output/'extra').mkdir()
        with self.assertRaises(ValueError):c.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').rmdir();path=self.output/'report.json';report=json.loads(path.read_bytes());report['image_built']=True;path.write_bytes(c.m.encoded(report))
        manifest=self.output/'manifest.json';value=json.loads(manifest.read_bytes());value['files']['report.json']=c.m.sha(path.read_bytes());manifest.write_bytes(c.m.encoded(value))
        with self.assertRaises(ValueError):c.verify(self.output,c.m.sha(manifest.read_bytes()))

    def test_altered_recipe_refused_even_with_new_outer_manifest(self):
        result=self.prepare();path=self.output/'Dockerfile';path.write_bytes(path.read_bytes()+b'\nRUN echo changed\n')
        manifest=self.output/'manifest.json';value=json.loads(manifest.read_bytes());value['files']['Dockerfile']=c.m.sha(path.read_bytes());manifest.write_bytes(c.m.encoded(value))
        with self.assertRaises(ValueError):c.verify(self.output,c.m.sha(manifest.read_bytes()))


class WorkerBoundsTests(unittest.TestCase):
    def invoke(self,args,raw=b'%PDF synthetic'):
        stdout=io.BytesIO();observed=[]
        def run(argv,cwd,max_stdout):
            self.assertEqual((Path(cwd)/'input.pdf').read_bytes(),raw);observed.append((argv,Path(cwd),max_stdout));return b'fixture result',b'fixture diagnostic'
        stderr=io.BytesIO()
        with patch.object(w.sys,'argv',['worker',*args]),patch.object(w.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw))),patch.object(w.sys,'stdout',SimpleNamespace(buffer=stdout)),patch.object(w.sys,'stderr',SimpleNamespace(buffer=stderr)),patch.object(w,'run',side_effect=run):w.main()
        self.assertFalse(observed[0][1].exists());return observed[0],stdout.getvalue(),stderr.getvalue()

    def test_info_uses_fixed_command_and_preserves_stderr(self):
        row,out,err=self.invoke(['info']);self.assertEqual(row[0],['/opt/poppler/bin/pdfinfo','input.pdf']);self.assertEqual(row[2],65536);self.assertEqual(err,b'fixture diagnostic')

    def test_page_uses_fixed_dpi_and_stdout_png(self):
        row,out,err=self.invoke(['page','2']);self.assertEqual(row[0],['/opt/poppler/bin/pdftoppm','-f','2','-l','2','-r','96','-png','-singlefile','input.pdf']);self.assertEqual(row[2],8*1024*1024)

    def test_page_out_of_range_and_extra_arguments_refused(self):
        for args in (['page','0'],['page','17'],['page','1;id'],['info','other'],['page','٢']):
            with self.subTest(args=args),patch.object(w.sys,'argv',['worker',*args]),self.assertRaises(ValueError):w.main()

    def test_empty_and_oversize_pdf_refused_before_process(self):
        for raw in (b'',b'123'):
            with patch.object(w,'MAX_PDF',2),patch.object(w.sys,'argv',['worker','info']),patch.object(w.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw))),patch.object(w,'run',side_effect=AssertionError('no process')),self.assertRaisesRegex(ValueError,'input size'):w.main()

    def test_failed_process_preserves_bounded_partial_diagnostics(self):
        out=io.BytesIO();err=io.BytesIO()
        with patch.object(w.sys,'stdout',SimpleNamespace(buffer=out)),patch.object(w.sys,'stderr',SimpleNamespace(buffer=err)),self.assertRaisesRegex(ValueError,'process failed'):
            w.run([sys.executable,'-c','import sys;sys.stdout.write("partial");sys.stderr.write("detail");raise SystemExit(2)'])
        self.assertEqual(out.getvalue(),b'partial');self.assertEqual(err.getvalue(),b'detail')

    def test_bounded_runner_exit_and_capture(self):
        out,err=w.run([sys.executable,'-c','print("fixture")']);self.assertEqual(out,b'fixture\n')
        with self.assertRaisesRegex(ValueError,'process failed'):w.run([sys.executable,'-c','raise SystemExit(2)'])
        with self.assertRaisesRegex(ValueError,'capture limit'):w.run([sys.executable,'-c','print("x"*70000)'])


if __name__=='__main__':unittest.main()
