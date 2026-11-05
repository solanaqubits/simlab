import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_typst_references as fixtures

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_typst_bibliography as b


class TypstBibliographyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.TypstReferenceTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.output=self.f.root/'bibliography'

    def check(self,files):
        parent,_=self.f.check(files);result=b.check(self.f.output,parent['manifest_sha256'],self.output)
        return result,json.loads((self.output/'report.json').read_bytes())

    def codes(self,report):return {row['code'] for row in report['findings']}

    def test_matching_key_is_candidate_without_promoting_parent_or_contents(self):
        result,report=self.check({'main.typ':'See @book\n#bibliography("refs.bib")','refs.bib':'@book{book,title={Fixture}}'})
        self.assertEqual(result['status'],b.CLEAN);self.assertEqual(report['parent_reference_status'],'review_required')
        self.assertEqual(report['references'][0]['classification'],'literal_bibliography_key_candidate')
        self.assertFalse(report['bibliography_contents_verified']);self.assertFalse(report['reference_semantics_checked']);self.assertEqual(b.verify(self.output,result['manifest_sha256']),result)

    def test_missing_key_remains_unclassified(self):
        result,report=self.check({'main.typ':'@missing\n#bibliography("refs.bib")','refs.bib':'@book{present,title={Fixture}}'})
        self.assertEqual(result['status'],'review_required');self.assertIn('unclassified_reference_candidate',self.codes(report))

    def test_label_and_bib_key_collision_requires_review(self):
        _,report=self.check({'main.typ':'= Heading <same>\n@same\n#bibliography("refs.bib")','refs.bib':'@book{same,title={Fixture}}'})
        self.assertIn('label_bibliography_collision',self.codes(report))

    def test_duplicate_keys_in_selected_bibliography(self):
        _,report=self.check({'main.typ':'@same\n#bibliography("refs.bib")','refs.bib':'@book{same,title={One}}\n@article{same,title={Two}}'})
        self.assertIn('repeated_bibliography_key_candidate',self.codes(report));self.assertEqual(report['references'][0]['bibliography_key_occurrences'],2)

    def test_multiple_bibliographies_and_cross_file_duplicate(self):
        _,report=self.check({'main.typ':'@same\n#bibliography("a.bib")\n#bibliography("b.bib")','a.bib':'@book{same,title={A}}','b.bib':'@book{same,title={B}}'})
        self.assertIn('multiple_bibliography_dependencies_require_review',self.codes(report));self.assertIn('repeated_bibliography_key_candidate',self.codes(report))

    def test_unselected_and_unreached_bib_never_resolve_reference(self):
        _,report=self.check({'main.typ':'@hidden\n#bibliography("missing.bib")','unused.bib':'@book{hidden,title={Hidden}}'})
        self.assertEqual(report['keys'],[]);self.assertEqual(report['unscanned_selected_bibliographies'],['unused.bib']);self.assertIn('bibliography_not_selected',self.codes(report))

    def test_yaml_remains_unsupported_without_parse(self):
        _,report=self.check({'main.typ':'@book\n#bibliography("refs.yaml")','refs.yaml':'book:\n  title: Fixture'})
        self.assertEqual(report['keys'],[]);self.assertIn('unsupported_bibliography_format_requires_review',self.codes(report))

    def test_malformed_and_parenthesized_entries_cannot_be_clean(self):
        for content in ('@book{book,title={Unclosed','@book(book,title={Unsupported})','Not BibTeX'):
            with self.subTest(content=content):
                local=TypstBibliographyTests();local.setUp()
                try:
                    result,report=local.check({'main.typ':'@book\n#bibliography("refs.bib")','refs.bib':content});self.assertEqual(result['status'],'review_required')
                    self.assertTrue(local.codes(report)&{'bibtex_scanner_requires_review','no_bibtex_key_candidates_requires_review'})
                finally:local.doCleanups()

    def test_nested_at_in_title_comments_and_preamble_do_not_create_keys(self):
        _,report=self.check({'main.typ':'@real\n#bibliography("refs.bib")','refs.bib':'% @book{commented,title={X}}\n@comment{ignored}\n@string{x="x"}\n@preamble{"header"}\n@book{real,title={Nested @article{fake,title={X}}}}'})
        self.assertEqual([row['key'] for row in report['keys']],['real'])

    def test_dynamic_parent_findings_remain_review(self):
        result,report=self.check({'main.typ':'#let x = 1\n@book\n#bibliography("refs.bib")','refs.bib':'@book{book,title={Fixture}}'})
        self.assertEqual(result['status'],'review_required');self.assertIn('parent_reference_finding_requires_review',self.codes(report))

    def test_label_only_project_unchanged_parent_and_offline_relocation(self):
        result,report=self.check({'main.typ':'= A <a>\n@a'});self.assertEqual(result['status'],b.CLEAN);self.assertEqual(report['references'][0]['classification'],'literal_label_candidate')
        moved=self.f.root/'moved';shutil.copytree(self.output,moved);shutil.rmtree(self.output);shutil.rmtree(self.f.project);shutil.rmtree(self.f.pre);shutil.rmtree(self.f.output);self.f.selection.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('offline')):self.assertEqual(b.verify(moved,result['manifest_sha256']),result)

    def test_tampered_resealed_report_and_extra_paths_refused(self):
        result,_=self.check({'main.typ':'= A <a>\n@a'})
        (self.output/'extra').mkdir()
        with self.assertRaises(ValueError):b.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').rmdir();path=self.output/'report.json';report=json.loads(path.read_bytes());report['bibliography_contents_verified']=True;path.write_bytes(b.m.encoded(report))
        manifest=self.output/'manifest.json';spec=json.loads(manifest.read_bytes());spec['files']['report.json']=b.m.sha(path.read_bytes());manifest.write_bytes(b.m.encoded(spec))
        with self.assertRaises(ValueError):b.verify(self.output,b.m.sha(manifest.read_bytes()))

    def test_key_bounds_existing_output_and_anchor_refused(self):
        parent,_=self.f.check({'main.typ':'@a\n#bibliography("refs.bib")','refs.bib':'@book{a,title={A}}\n@book{b,title={B}}'})
        with self.assertRaises(ValueError):b.check(self.f.output,'0'*64,self.output)
        with patch.object(b,'MAX_KEYS',1),self.assertRaisesRegex(ValueError,'key limit'):b.check(self.f.output,parent['manifest_sha256'],self.output)
        self.assertFalse(self.output.exists());self.output.mkdir()
        with self.assertRaises(ValueError):b.check(self.f.output,parent['manifest_sha256'],self.output)

    def test_cli_review_status_survives_verification(self):
        parent,_=self.f.check({'main.typ':'@missing'});tool=Path(b.__file__)
        run=subprocess.run([sys.executable,str(tool),'check','--bundle',str(self.f.output),'--sha256',parent['manifest_sha256'],'--output',str(self.output)],capture_output=True)
        self.assertEqual(run.returncode,2,run.stderr);result=json.loads(run.stdout)
        run=subprocess.run([sys.executable,str(tool),'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True)
        self.assertEqual(run.returncode,2,run.stderr);self.assertEqual(json.loads(run.stdout),result)


if __name__=='__main__':unittest.main()
