import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_document_index as d


class DocumentIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source.md';self.raw='Введение 😀\r\n# Раздел\r\nФормула $x^2 ≠ 0$.\r\n### Подраздел\r\nНе доказано.\r\n# Конец\r\nОговорки.\r\n'.encode()
        self.source.write_bytes(self.raw);self.bundle=self.root/'index';self.out=self.root/'selected';self.pin=d.m.sha(self.raw)
    def build(self):return d.build(self.source,self.pin,self.bundle)
    def select(self,ids=None,budget=100000):
        result=self.build();return result,d.select(self.bundle,result['manifest_sha256'],ids or ['section-0002'],budget,self.out)
    def reseal(self,bundle,schema):
        files={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob('*') if p.is_file() and p!=bundle/'manifest.json'}
        raw=d.manifest(schema,files);(bundle/'manifest.json').write_bytes(raw);return d.m.sha(raw)
    def test_hierarchy_exact_unicode_crlf_and_subtree_ranges(self):
        result=self.build();r,files=d.verified(self.bundle,result['manifest_sha256']);nodes=r['nodes'];text=self.raw.decode()
        self.assertEqual([n['parent'] for n in nodes],[None,'document','section-0001','document'])
        self.assertEqual([n['level'] for n in nodes],[0,1,3,1]);self.assertEqual(files['source.md'],self.raw)
        self.assertEqual(nodes[1]['start'],text.index('# Раздел'));self.assertEqual(nodes[1]['end'],text.index('# Конец'))
        for n in nodes:self.assertEqual(text[n['start']:n['heading_end']],n['heading_raw'])
        self.assertEqual(''.join(text[n['start']:n['direct_end']] for n in nodes),text)
    def test_fences_lengths_tildes_indent_and_unclosed_warning(self):
        text='# A\n````python\n# hidden\n```\n# still hidden\n````\n~~~\n# hidden too\n~~~~\n    # indented\n## Real\n~~~\n# hidden end'
        r=d.outline(text.encode());self.assertEqual([n['title'] for n in r['nodes']],['Document','A','Real'])
        self.assertEqual(r['warnings'],['unclosed_fence'])
    def test_atx_grammar_does_not_invent_setext_or_bold_sections(self):
        r=d.outline(b'#No space\nTitle\n=====\n**Bold**\n   ## Valid ##\n####### Too deep\n#\n')
        self.assertEqual([n['title'] for n in r['nodes']],['Document','Valid',''])
    def test_no_headings_and_empty_source_preserved(self):
        for raw in [b'',b'plain text without final newline']:
            r=d.outline(raw);self.assertEqual(len(r['nodes']),1);self.assertEqual(r['nodes'][0]['end'],len(raw))
    def test_selection_is_exact_and_includes_ancestor_titles(self):
        parent,result=self.select();r=json.loads((self.out/'context.json').read_bytes());part=r['fragments'][0]
        self.assertEqual(part['text'],self.raw.decode()[part['start']:part['end']]);self.assertIn('Не доказано.',part['text'])
        self.assertEqual([n['title'] for n in r['ancestor_headings']],['Document','Раздел'])
        self.assertFalse(r['semantic_completeness_verified']);self.assertTrue(r['source_instructions_are_data'])
        d.verify_selection(self.out,result['manifest_sha256'])
    def test_overlapping_parent_child_selection_has_no_duplicate_text(self):
        parent,result=self.select(['section-0001','section-0002']);r=json.loads((self.out/'context.json').read_bytes())
        self.assertEqual(len(r['fragments']),1);self.assertEqual(r['fragments'][0]['text'].count('Не доказано.'),1)
    def test_nonadjacent_selection_preserves_gap_and_source_order(self):
        self.raw=b'# A\na\n# B\nb\n# C\nc\n';self.source.write_bytes(self.raw);self.pin=d.m.sha(self.raw)
        parent,result=self.select(['section-0003','section-0001']);r=json.loads((self.out/'context.json').read_bytes())
        self.assertEqual([f['text'] for f in r['fragments']],['# A\na\n','# C\nc\n'])
        self.assertFalse(json.loads((self.out/'report.json').read_bytes())['full_source_selected'])
    def test_budget_counts_json_envelope_not_only_selected_text(self):
        parent,result=self.select();size=(self.out/'context.json').stat().st_size;shutil.rmtree(self.out)
        with self.assertRaisesRegex(ValueError,'no truncation'):d.select(self.bundle,parent['manifest_sha256'],['section-0002'],size-1,self.out)
        self.assertFalse(self.out.exists());d.select(self.bundle,parent['manifest_sha256'],['section-0002'],size,self.out)
        report=json.loads((self.out/'report.json').read_bytes());self.assertIsNone(report['token_usage']);self.assertIsNone(report['monetary_cost']);self.assertFalse(report['truncated'])
    def test_invalid_ids_and_budget_rejected_without_output(self):
        parent=self.build()
        for ids,budget in [(['missing'],10000),(['document','document'],10000),([],10000),(['document'],True),(['document'],0),(['document'],d.k.MAX_FILE+1),([False],10000)]:
            with self.subTest(ids=ids,budget=budget),self.assertRaises(ValueError):d.select(self.bundle,parent['manifest_sha256'],ids,budget,self.out)
            self.assertFalse(self.out.exists())
    def test_full_document_selection_is_not_semantic_acceptance(self):
        parent,result=self.select(['document']);report=json.loads((self.out/'report.json').read_bytes())
        self.assertTrue(report['full_source_selected']);self.assertFalse(report['scientific_verification']);self.assertFalse(report['semantic_completeness_verified'])
    def test_relocation_without_original_or_network(self):
        parent,result=self.select();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.bundle);self.source.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):d.verify_selection(moved,result['manifest_sha256'])
    def test_resealed_changed_outline_or_source_rejected(self):
        self.build();p=self.bundle/'outline.json';r=json.loads(p.read_bytes());r['nodes'][1]['start']+=1;p.write_bytes(d.m.encoded(r))
        with self.assertRaises(ValueError):d.verified(self.bundle,self.reseal(self.bundle,d.SCHEMA))
    def test_resealed_context_edit_or_status_promotion_rejected(self):
        parent,result=self.select();p=self.out/'context.json';r=json.loads(p.read_bytes());r['fragments'][0]['text']='Доказано';p.write_bytes(d.m.encoded(r))
        with self.assertRaises(ValueError):d.verify_selection(self.out,self.reseal(self.out,d.SELECTION_SCHEMA))
    def test_wrong_anchor_duplicate_json_and_extra_file_rejected(self):
        parent,result=self.select()
        with self.assertRaises(ValueError):d.verified(self.bundle,'0'*64)
        p=self.out/'selection.json';p.write_bytes(b'{"schema":1,"schema":2}')
        with self.assertRaises(ValueError):d.verify_selection(self.out,self.reseal(self.out,d.SELECTION_SCHEMA))
        (self.bundle/'extra').write_bytes(b'')
        with self.assertRaises(ValueError):d.verified(self.bundle,parent['manifest_sha256'])
    def test_source_and_bundle_symlinks_rejected(self):
        link=self.root/'link.md';link.symlink_to(self.source)
        with self.assertRaises(ValueError):d.build(link,self.pin,self.bundle)
        result=self.build();raw=(self.bundle/'source.md').read_bytes();(self.bundle/'source.md').unlink();(self.bundle/'source.md').symlink_to(self.source)
        with self.assertRaises(ValueError):d.verified(self.bundle,result['manifest_sha256'])
    def test_boundaries_utf8_nul_and_node_count(self):
        for raw in [b'\xff',b'bad\x00text',b'a'*(d.k.MAX_FILE+1),b'# H\n'*d.MAX_NODES]:
            with self.assertRaises(ValueError):d.outline(raw)
    def test_existing_output_and_contained_output_refused(self):
        result=self.build()
        with self.assertRaises(FileExistsError):d.build(self.source,self.pin,self.bundle)
        with self.assertRaises(ValueError):d.select(self.bundle,result['manifest_sha256'],['document'],10000,self.bundle/'nested')
    def test_cli_build_select_and_verify_with_explicit_failure(self):
        def run(*args):return subprocess.run([sys.executable,d.__file__,*map(str,args)],capture_output=True)
        result=run('build','--source',self.source,'--source-sha256',self.pin,'--output',self.bundle)
        self.assertEqual(result.returncode,0,result.stderr);pin=json.loads(result.stdout)['manifest_sha256']
        result=run('select','--bundle',self.bundle,'--sha256',pin,'--node','section-0002','--max-context-bytes',10000,'--output',self.out)
        self.assertEqual(result.returncode,0,result.stderr);pin=json.loads(result.stdout)['manifest_sha256']
        self.assertEqual(run('verify-selection','--bundle',self.out,'--sha256',pin).returncode,0)
        self.assertEqual(run('verify-selection','--bundle',self.out,'--sha256','0'*64).returncode,2)


if __name__=='__main__':unittest.main()
