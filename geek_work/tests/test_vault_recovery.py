import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_memory as fixture
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_vault_recovery as r
sys.path.pop(0)

class VaultRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixture.MemoryTests.setUp(self)
        self.vault=self.root/'view'
        self.view=r.v.export(self.g,self.root,self.req,self.vault)
        self.out=self.root/'recovery'
    def pack(self):
        self.info=r.snapshot(self.g,self.root,self.vault,self.view['seal_sha256'],self.out)
        return self.info
    def verify(self):return r.verify(self.out,self.info['snapshot_sha256'])
    def test_snapshot_verified(self):
        before=copy.deepcopy(self.g);self.pack();res=self.verify()
        self.assertEqual(res['status'],'verified_recovery');self.assertEqual(before,self.g)
        self.assertFalse(res['full_provenance_checked']);self.assertFalse(res['scientific_verification'])
    def test_move_with_old_root_gone(self):
        self.pack()
        with tempfile.TemporaryDirectory() as tmp:
            moved=Path(tmp)/'new-root';shutil.copytree(self.out,moved)
            shutil.rmtree(self.root)
            self.assertEqual(r.verify(moved,self.info['snapshot_sha256'])['status'],'verified_recovery')
    def test_full_graph_and_selected_sources(self):
        self.pack();self.assertEqual(len(r.k.load(self.out/'graph.json')['cards']),3)
        self.assertEqual(self.info['selected_source_files'],1)
    def test_source_missing_refused(self):
        (self.root/'source.txt').unlink()
        with self.assertRaises(r.k.Refusal):self.pack()
    def test_source_tampered(self):
        self.pack();(self.out/'sources/source.txt').write_text('changed')
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_file_changed'):self.verify()
    def test_note_tampered(self):
        self.pack();(self.out/'vault/Index.md').write_text('changed')
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_file_changed'):self.verify()
    def test_extra_file(self):
        self.pack();(self.out/'unknown').write_text('extra')
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_file_set'):self.verify()
    def test_missing_file(self):
        self.pack();(self.out/'graph.json').unlink()
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_file_set'):self.verify()
    def test_wrong_anchor(self):
        self.pack()
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_anchor'):r.verify(self.out,'0'*64)
    def test_symlink_source(self):
        self.pack();p=self.out/'sources/source.txt';p.unlink();p.symlink_to(self.root/'source.txt')
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_symlink'):self.verify()
    def test_ui_configuration_not_copied(self):
        (self.vault/'.obsidian').mkdir();(self.vault/'.obsidian/secret').write_text('ui only')
        self.pack();self.assertFalse((self.out/'vault/.obsidian').exists());self.verify()
    def test_output_exclusive(self):
        self.pack()
        with self.assertRaises(FileExistsError):self.pack()
    def test_budget_limit(self):
        with patch.object(r,'MAX_TOTAL',1),self.assertRaisesRegex(r.k.Refusal,'snapshot_byte_limit'):self.pack()
        self.assertFalse(self.out.exists())
    def test_file_limit(self):
        with patch.object(r,'MAX_FILES',1),self.assertRaisesRegex(r.k.Refusal,'snapshot_file_limit'):self.pack()
    def test_tool_pin_tamper(self):
        self.pack();seal=r.k.load(self.out/'seal.json');seal['tool_pins']={}
        (self.out/'seal.json').write_bytes(r.k.canonical(seal));self.info['snapshot_sha256']=r.v.digest(seal)
        with self.assertRaisesRegex(r.k.Refusal,'snapshot_tools'):self.verify()
