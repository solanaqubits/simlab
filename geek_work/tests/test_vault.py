import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_memory as fixtures
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_vault as v


class VaultTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.MemoryTests();f.setUp();self.addCleanup(f.doCleanups)
        self.root,self.g,self.req=f.root,f.g,f.req;self.out=self.root/'vault'
    def refresh(self):self.req['expected_graph_sha256']=v.digest(self.g)
    def export(self):self.info=v.export(self.g,self.root,self.req,self.out);return self.info
    def verify(self):return v.verify(self.out,self.info['seal_sha256'],self.g,self.root)
    def lint(self,planned=None):return v.lint(self.out,self.info['seal_sha256'],self.g,self.root,planned)
    def note(self):return self.out/(v.target('claim:result')+'.md')
    def reseal(self):
        s=v.k.load(self.out/'seal.json');s['files']={n:v.k.digest((self.out/n).read_bytes()) for n in s['files']}
        (self.out/'seal.json').write_bytes(v.k.canonical(s));self.info['seal_sha256']=v.digest(s)

    def test_export_preserves_source_and_dependency(self):
        before=copy.deepcopy(self.g);result=self.export();self.assertEqual(result['cards'],2);self.assertEqual(self.g,before)
        context=v.k.load(self.out/'context.json');self.assertEqual(len(context['cards']),2)
        self.assertEqual(self.verify()['status'],'verified_projection')

    def test_generated_links_are_resolved(self):
        self.export();self.assertEqual(self.lint()['status'],'clean_generated_notes')
        self.assertIn('## Backlinks',self.note().read_text())

    def test_full_detail_preserved(self):
        self.g['cards'][1]['detail']['formula']='∀ ε > 0, x² ≠ 0; [[fake]]';self.refresh();self.export()
        self.assertIn('∀ ε > 0, x² ≠ 0; [[fake]]',self.note().read_text())
        self.assertEqual(self.lint()['issues'],[])

    def test_escape_source_links_html_and_fences(self):
        self.g['cards'][1]['text']='![[phantom]] <script>bad()</script> ``` # heading';self.refresh();self.export()
        text=self.note().read_text();self.assertIn('&lt;script&gt;',text);self.assertIn('\\[\\[phantom',text)
        self.assertEqual(self.lint()['issues'],[])

    def test_dynamic_fence(self):
        block=v.block({'x':'```\n[[fake]]\n````'})
        self.assertTrue(block.startswith('`````json'));self.assertEqual(v.wiki_targets(block),[])

    def test_same_titles_have_distinct_files(self):
        self.g['cards'][0]['title']=self.g['cards'][1]['title'];self.refresh();self.export()
        self.assertEqual(len(list((self.out/'Cards').glob('*.md'))),2)

    def test_unknown_link_not_auto_created(self):
        self.export();self.note().write_text(self.note().read_text()+'\n[[future-note]]\n')
        r=self.lint();self.assertEqual(r['issues'][0]['kind'],'unresolved_reference')
        self.assertFalse((self.out/'future-note.md').exists());self.assertFalse(r['write_back_enabled'])

    def test_declared_future_link_still_needs_review(self):
        self.export();self.note().write_text(self.note().read_text()+'\n[[future-note]]\n')
        r=self.lint(['future-note']);self.assertEqual(r['status'],'needs_review')
        self.assertEqual(r['issues'][0]['kind'],'planned_reference')

    def test_planned_path_escape(self):
        self.export()
        with self.assertRaisesRegex(v.k.Refusal,'planned_references'):self.lint(['../escape'])

    def test_missing_target(self):
        self.export();(self.out/(v.target('claim:premise')+'.md')).unlink()
        self.assertTrue(any(x['kind']=='missing_note' for x in self.lint()['issues']))

    def test_changed_note_breaks_verification(self):
        self.export();self.note().write_text('edited')
        with self.assertRaisesRegex(v.k.Refusal,'projection_changed'):self.verify()

    def test_resealed_note_not_accepted(self):
        self.export();self.note().write_text('proved');self.reseal()
        with self.assertRaisesRegex(v.k.Refusal,'projection_manifest'):self.verify()

    def test_graph_drift(self):
        self.export();self.g['cards'][1]['scope']='changed'
        with self.assertRaisesRegex(v.k.Refusal,'graph_changed'):self.verify()

    def test_source_drift(self):
        self.export();(self.root/'source.txt').write_text('changed')
        with self.assertRaisesRegex(v.k.Refusal,'projection_manifest'):self.verify()

    def test_missing_source_visible_on_export(self):
        (self.root/'source.txt').unlink();self.export()
        self.assertIn('source_missing',v.k.load(self.out/'context.json')['cards'][0]['issues'])

    def test_stale_graph_request(self):
        self.req['expected_graph_sha256']='a'*64
        with self.assertRaisesRegex(v.k.Refusal,'graph_changed'):self.export()

    def test_stale_revision(self):
        self.req['cards'][0]['revision']=2
        with self.assertRaisesRegex(v.k.Refusal,'revision_changed'):self.export()

    def test_exclusive_directory(self):
        self.export()
        with self.assertRaises(FileExistsError):self.export()

    def test_unknown_selection(self):
        self.req['cards'][0]['id']='claim:unknown'
        with self.assertRaises(v.k.Refusal):self.export()

    def test_symlink_card(self):
        self.export();self.note().unlink();self.note().symlink_to(self.root/'source.txt')
        with self.assertRaisesRegex(v.k.Refusal,'symlink'):self.verify()

    def test_ui_config_explicitly_outside_audit(self):
        self.export();(self.out/'.obsidian').mkdir();(self.out/'.obsidian'/'config.json').write_text('{}')
        self.assertTrue(self.verify()['ui_config_not_audited'])

    def test_extra_note_refused_by_verify(self):
        self.export();(self.out/'extra.md').write_text('proposal')
        with self.assertRaisesRegex(v.k.Refusal,'file_set'):self.verify()

    def test_objection_closure(self):
        self.g['links'].append(dict(**{'from':'claim:objection','to':'claim:result'},relation='contradicts',scope='Objection'))
        self.refresh();self.assertEqual(self.export()['cards'],3)
        self.assertTrue(any('linked_objection_requires_review' in row['issues'] for row in v.k.load(self.out/'context.json')['cards']))

    def test_boundary_not_fake_note(self):
        self.g['links'].append(dict(**{'from':'claim:objection','to':'claim:result'},relation='related_to',scope='Outside selection'))
        self.refresh();self.export();self.assertEqual(len(list((self.out/'Cards').glob('*.md'))),2)
        self.assertIn('claim:objection',(self.out/'Boundary.md').read_text());self.assertEqual(self.lint()['issues'],[])

    def test_export_budget(self):
        with patch.object(v,'MAX_TOTAL',10),self.assertRaisesRegex(v.k.Refusal,'vault_byte_limit'):self.export()

    def test_wrong_anchor(self):
        self.export()
        with self.assertRaisesRegex(v.k.Refusal,'seal_anchor'):v.verify(self.out,'a'*64,self.g,self.root)
