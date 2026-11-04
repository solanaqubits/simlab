import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('manuscript',Path(__file__).parents[1]/'tools/geek_work_manuscript.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ManuscriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.base=self.root/'main.tex';self.candidate=self.root/'candidate.tex';self.bundle=self.root/'proposal'
        self.before='\\section{Тест}\r\n$E=mc^2$\\cite{a}\r\n'.encode()
        self.after='\\section{Тест}\r\n$E=mc^2$\\cite{a}\r\nExplicit caveat.\r\n'.encode()
        self.base.write_bytes(self.before);self.candidate.write_bytes(self.after)
    def propose(self):return m.propose(self.base,self.candidate,'paper/main.tex','synthetic-fixture','Add caveat',self.bundle)
    def test_accept_preserves_formula_and_original_bytes(self):
        p=self.propose();r=m.decide(self.bundle,p['manifest_sha256'],self.base,'accept','reviewer',self.root/'accepted')
        self.assertEqual((self.root/'accepted/result.tex').read_bytes(),self.after)
        self.assertEqual(self.base.read_bytes(),self.before);self.assertFalse(r['live_document_modified']);self.assertFalse(r['scientific_verification'])
    def test_reject_outputs_exact_baseline(self):
        p=self.propose();m.decide(self.bundle,p['manifest_sha256'],self.base,'reject','reviewer',self.root/'rejected')
        self.assertEqual((self.root/'rejected/result.tex').read_bytes(),self.before)
    def test_stale_base_rejects_both_decisions(self):
        p=self.propose();self.base.write_bytes(b'concurrent human edit')
        for decision in ('accept','reject'):
            with self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):m.decide(self.bundle,p['manifest_sha256'],self.base,decision,'reviewer',self.root/decision)
            self.assertFalse((self.root/decision).exists())
    def test_anchor_and_tamper(self):
        p=self.propose()
        with self.assertRaises(ValueError):m.verified(self.bundle,'0'*64)
        (self.bundle/'after.txt').write_bytes(b'tamper')
        with self.assertRaises(ValueError):m.verified(self.bundle,p['manifest_sha256'])
    def test_preview_recomputed_even_if_resealed(self):
        self.propose();(self.bundle/'review.html').write_text('<script>bad()</script>')
        manifest=json.loads((self.bundle/'manifest.json').read_bytes());manifest['files']['review.html']=m.sha((self.bundle/'review.html').read_bytes())
        raw=m.encoded(manifest);(self.bundle/'manifest.json').write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'preview mismatch'):m.verified(self.bundle,m.sha(raw))
    def test_html_escapes_source_and_labels(self):
        self.candidate.write_bytes(b'<script>alert(1)</script>')
        p=m.propose(self.base,self.candidate,'main.tex','<img src=x>','<iframe>',self.bundle)
        _,data=m.verified(self.bundle,p['manifest_sha256']);page=data['review.html'].decode()
        self.assertNotIn('<script>',page);self.assertNotIn('<img',page);self.assertIn('&lt;script&gt;',page);self.assertIn("default-src 'none'",page)
    def test_line_ending_only_change_is_explicit(self):
        self.candidate.write_bytes(self.before.replace(b'\r\n',b'\n'))
        p=self.propose();_,data=m.verified(self.bundle,p['manifest_sha256'])
        self.assertIn(b'crlf',data['review.html']);self.assertNotEqual(m.metadata(self.before),m.metadata(self.candidate.read_bytes()))
    def test_all_extensions_and_bad_paths(self):
        for name in ['a.tex','a.typ','a.md','a.bib']:self.assertEqual(m.document(name).suffix,Path(name).suffix)
        for name in ['../a.tex','/a.tex','a/../b.tex','a.exe','a\\b.tex','a\nb.tex']:
            with self.assertRaises(ValueError):m.document(name)
    def test_no_change_invalid_utf8_and_size_limits(self):
        self.candidate.write_bytes(self.before)
        with self.assertRaises(ValueError):self.propose()
        self.candidate.write_bytes(b'\xff')
        with self.assertRaises(UnicodeError):self.propose()
        self.candidate.write_bytes(self.after)
        with patch.object(m,'MAX_SOURCE',4),self.assertRaises(ValueError):self.propose()
        self.assertFalse(self.bundle.exists())
    def test_symlink_and_extra_file(self):
        self.candidate.unlink();self.candidate.symlink_to(self.base)
        with self.assertRaises(ValueError):self.propose()
        self.candidate.unlink();self.candidate.write_bytes(self.after);p=self.propose();(self.bundle/'extra').write_text('x')
        with self.assertRaises(ValueError):m.verified(self.bundle,p['manifest_sha256'])
    def test_exclusive_creation(self):
        p=self.propose()
        with self.assertRaises(FileExistsError):self.propose()
        out=self.root/'accepted';m.decide(self.bundle,p['manifest_sha256'],self.base,'accept','reviewer',out)
        with self.assertRaises(FileExistsError):m.decide(self.bundle,p['manifest_sha256'],self.base,'accept','reviewer',out)
    def test_cli(self):
        tool=str(Path(m.__file__))
        result=json.loads(subprocess.check_output(['python3',tool,'propose','--base',str(self.base),'--candidate',str(self.candidate),'--document','main.tex','--author','fixture','--reason','caveat','--output',str(self.bundle)],text=True))
        result=json.loads(subprocess.check_output(['python3',tool,'decide','--bundle',str(self.bundle),'--sha256',result['manifest_sha256'],'--current',str(self.base),'--decision','accept','--reviewer','fixture','--output',str(self.root/'out')],text=True))
        self.assertEqual(result['result_sha256'],m.sha(self.after))
