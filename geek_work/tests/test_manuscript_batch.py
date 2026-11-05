import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_manuscript_batch as b


class BatchReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.base=self.root/'base';self.candidate=self.root/'candidate';self.bundle=self.root/'bundle';self.out=self.root/'decision'
        self.names=['paper/main.tex','paper/refs.bib','notes.md']
        self.before={'paper/main.tex':b'\\cite{old}\r\n','paper/refs.bib':b'@article{old, title={Title}}\r\n','notes.md':'Guard α\n'.encode()}
        self.after={**self.before,'paper/main.tex':b'\\cite{new}\r\n','paper/refs.bib':b'@article{new, title={Title}}\r\n'}
        for root,files in [(self.base,self.before),(self.candidate,self.after)]:
            for name,raw in files.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    def propose(self):return b.propose(self.base,self.candidate,self.names,'synthetic-fixture','Paired citation edit',self.bundle)
    def decide(self,anchor,decision='accept'):return b.decide(self.bundle,anchor,self.base,decision,'fixture-reviewer',self.out)
    def test_accept_all_and_guard_with_exact_bytes(self):
        p=self.propose();self.assertEqual(p['changed'],2);r=self.decide(p['manifest_sha256'])
        for name,raw in self.after.items():self.assertEqual((self.out/'result'/name).read_bytes(),raw)
        for name,raw in self.before.items():self.assertEqual((self.base/name).read_bytes(),raw)
        self.assertFalse(r['live_document_modified']);self.assertFalse(r['reference_consistency_checked'])
    def test_reject_all(self):
        p=self.propose();self.decide(p['manifest_sha256'],'reject')
        for name,raw in self.before.items():self.assertEqual((self.out/'result'/name).read_bytes(),raw)
    def test_stale_bib_and_unchanged_guard_block_whole_batch(self):
        p=self.propose()
        for name in ('paper/refs.bib','notes.md'):
            (self.base/name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'STALE_BASE_REJECTED'):self.decide(p['manifest_sha256'])
            self.assertFalse(self.out.exists());(self.base/name).write_bytes(self.before[name])
    def test_missing_candidate_and_no_changes(self):
        p=self.candidate/'paper/refs.bib';p.unlink()
        with self.assertRaises(ValueError):self.propose()
        self.assertFalse(self.bundle.exists());p.write_bytes(self.before['paper/refs.bib'])
        (self.candidate/'paper/main.tex').write_bytes(self.before['paper/main.tex'])
        with self.assertRaisesRegex(ValueError,'no changes'):self.propose()
    def test_selection_duplicates_traversal_and_prefix_conflicts(self):
        for names in [[],['../a.tex'],['a.tex','A.tex'],['a.tex','a.tex/b.md'],['.git/a.md'],['a:b.tex']]:
            with self.assertRaises(ValueError):b.selection(names)
    def test_intermediate_symlink_cannot_escape(self):
        external=self.root/'outside';external.mkdir();(external/'a.tex').write_text('private')
        (self.base/'linked').symlink_to(external,target_is_directory=True)
        with self.assertRaises(ValueError):b.project_file(self.base,'linked/a.tex')
    def test_fifo_and_leaf_symlink(self):
        os.mkfifo(self.base/'pipe.tex')
        with self.assertRaises(ValueError):b.project_file(self.base,'pipe.tex')
        (self.base/'link.md').symlink_to(self.base/'notes.md')
        with self.assertRaises(ValueError):b.project_file(self.base,'link.md')
    def test_tampered_index_and_extra_entry(self):
        p=self.propose();(self.bundle/'review.html').write_text('modified')
        with self.assertRaises(ValueError):self.decide(p['manifest_sha256'])
        self.assertFalse(self.out.exists())
        manifest=json.loads((self.bundle/'manifest.json').read_bytes())
        (self.bundle/'review.html').write_bytes(b.index(manifest['entries']))
        (self.bundle/'files/extra').mkdir()
        with self.assertRaises(ValueError):self.decide(p['manifest_sha256'])
    def test_resealed_wrong_change_flag_rejected(self):
        self.propose();path=self.bundle/'manifest.json';m=json.loads(path.read_bytes());m['entries'][0]['changed']=not m['entries'][0]['changed'];raw=b.m.encoded(m);path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'change flag'):self.decide(b.m.sha(raw))
    def test_bundle_limit_and_output_exclusivity(self):
        with patch.object(b,'MAX_BUNDLE',1),self.assertRaises(ValueError):self.propose()
        self.assertFalse(self.bundle.exists());p=self.propose();self.decide(p['manifest_sha256'])
        with self.assertRaises(FileExistsError):self.decide(p['manifest_sha256'])
    def test_unselected_files_are_not_copied(self):
        (self.base/'secret.md').write_text('private');(self.candidate/'secret.md').write_text('changed')
        p=self.propose();r=self.decide(p['manifest_sha256']);self.assertNotIn('secret.md',r['files']);self.assertFalse((self.out/'result/secret.md').exists())
    def test_write_failure_has_no_completion_receipt(self):
        p=self.propose();original=Path.open
        def fail(path,*args,**kwargs):
            if path==self.out/'result/paper/refs.bib':raise OSError('injected write failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',fail),self.assertRaises(OSError):self.decide(p['manifest_sha256'])
        self.assertFalse((self.out/'receipt.json').exists());self.assertEqual((self.base/'paper/main.tex').read_bytes(),self.before['paper/main.tex'])
    def test_cli(self):
        selection=self.root/'selection.json';selection.write_text(json.dumps(self.names))
        cmd=['python3',b.__file__]
        p=json.loads(subprocess.check_output(cmd+['propose','--base-root',str(self.base),'--candidate-root',str(self.candidate),'--selection',str(selection),'--author','fixture','--reason','Paired edit','--output',str(self.bundle)],text=True))
        r=json.loads(subprocess.check_output(cmd+['decide','--bundle',str(self.bundle),'--sha256',p['manifest_sha256'],'--current-root',str(self.base),'--decision','accept','--reviewer','fixture','--output',str(self.out)],text=True))
        self.assertEqual(r['selected_files'],3)
