import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_typst_references as r


class TypstReferenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.project=self.root/'project';self.project.mkdir();self.selection=self.root/'selection.json';self.pre=self.root/'preflight';self.output=self.root/'references'

    def prepare(self,files):
        for name,raw in files.items():
            path=self.project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw.encode() if isinstance(raw,str) else raw)
        self.selection.write_bytes(r.m.encoded(dict(schema='geek-work-typst-preflight-selection-1',entry='main.typ',files=list(files))))
        result=r.pre.check(self.project,self.selection,r.m.sha(self.selection.read_bytes()),self.pre);return result['manifest_sha256']

    def check(self,files):
        anchor=self.prepare(files);result=r.check(self.pre,anchor,self.output);report=json.loads((self.output/'report.json').read_bytes());return result,report

    def codes(self,report):return {row['code'] for row in report['findings']}

    def test_cross_file_forward_reference_and_exact_unicode_offsets(self):
        result,report=self.check({'main.typ':'Пример @chapter\n#include "chapter.typ"','chapter.typ':'= Later <chapter>'})
        self.assertEqual(result['status'],r.CLEAN);row=report['references'][0]
        text=(self.project/row['file']).read_text();self.assertEqual(text[row['start']:row['end']],'@chapter')
        self.assertEqual(row['literal_label_occurrences'],1);self.assertFalse(report['reference_semantics_checked'])
        self.assertEqual(r.verify(self.output,result['manifest_sha256']),result)

    def test_repeated_label_candidates_across_files(self):
        _,report=self.check({'main.typ':'= First <same>\n#include "other.typ"','other.typ':'= Second <same>\n@same'})
        self.assertEqual(report['references'][0]['literal_label_occurrences'],2);self.assertIn('repeated_literal_label_candidate',self.codes(report))

    def test_unmatched_reference_is_not_claimed_invalid_citation(self):
        result,report=self.check({'main.typ':'See @book\n#bibliography("refs.bib")','refs.bib':'@book{book,title={Fixture}}'})
        self.assertEqual(result['status'],'review_required');finding=next(x for x in report['findings'] if x['code']=='reference_not_in_literal_label_inventory')
        self.assertTrue(finding['bibliography_candidate']);self.assertIn('bibliography_contents_require_review',self.codes(report));self.assertFalse(report['bibliography_contents_checked'])

    def test_unmatched_reference_without_bibliography(self):
        _,report=self.check({'main.typ':'See @missing'})
        row=next(x for x in report['findings'] if x['code']=='reference_not_in_literal_label_inventory');self.assertFalse(row['bibliography_candidate'])

    def test_comments_escapes_raw_and_strings_do_not_supply_labels(self):
        _,report=self.check({'main.typ':'// <line> @line\n/* <block> /* @nested */ */\n\\<escaped> \\@escaped\n`<raw> @raw`\n"<quoted> @quoted"'})
        self.assertEqual(report['labels'],[]);self.assertEqual(report['references'],[])
        self.assertIn('preflight_findings_require_review',self.codes(report));self.assertIn('quoted_reference_region_requires_review',self.codes(report))

    def test_extended_ascii_label_names_and_supplement(self):
        result,report=self.check({'main.typ':'= Topic <s:1.a-b>\nSee @s:1.a-b[Section]'})
        self.assertEqual(result['status'],r.CLEAN);self.assertEqual(report['references'][0]['key'],'s:1.a-b')

    def test_unsupported_unicode_math_and_punctuation_never_silently_pass(self):
        _,report=self.check({'main.typ':'<тема> @тема\n<ok> @ok.\n$ x < y $'})
        self.assertEqual(report['status'],'review_required');codes=self.codes(report)
        self.assertIn('unsupported_literal_marker_requires_review',codes);self.assertIn('ambiguous_reference_boundary_requires_review',codes);self.assertIn('math_region_requires_review',codes)

    def test_functional_forms_and_unknown_code_require_review(self):
        _,report=self.check({'main.typ':'label("dynamic") ref(<literal>) cite(<book>)\n#let dynamic = "name"'})
        self.assertIn('functional_reference_construct_requires_review',self.codes(report));self.assertIn('preflight_findings_require_review',self.codes(report))

    def test_repeated_include_and_unreached_selection_are_explicit(self):
        _,report=self.check({'main.typ':'#include "a.typ"\n#include "a.typ"','a.typ':'= A <a>','unused.typ':'= Hidden <hidden>'})
        self.assertEqual(report['unreached_selected_typst'],['unused.typ']);self.assertEqual([x['key'] for x in report['labels']],['a']);self.assertIn('repeated_module_dependency_requires_review',self.codes(report))

    def test_resealed_report_cannot_promote_semantics(self):
        result,_=self.check({'main.typ':'= A <a>\n@a'});path=self.output/'report.json';report=json.loads(path.read_bytes());report['reference_semantics_checked']=True;path.write_bytes(r.m.encoded(report))
        manifest=self.output/'manifest.json';spec=json.loads(manifest.read_bytes());spec['files']['report.json']=r.m.sha(path.read_bytes());manifest.write_bytes(r.m.encoded(spec))
        with self.assertRaises(ValueError):r.verify(self.output,r.m.sha(manifest.read_bytes()))

    def test_relocation_verifies_without_original_project_or_external_execution(self):
        result,_=self.check({'main.typ':'= A <a>\n@a'});copy=self.root/'relocated';shutil.copytree(self.output,copy)
        shutil.rmtree(self.project);shutil.rmtree(self.pre);shutil.rmtree(self.output);self.selection.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('no process')):
            self.assertEqual(r.verify(copy,result['manifest_sha256'])['status'],r.CLEAN)

    def test_missing_extra_tampered_snapshot_and_wrong_anchor_refused(self):
        result,_=self.check({'main.typ':'= A <a>'})
        with self.assertRaises(ValueError):r.verify(self.output,'0'*64)
        (self.output/'extra').mkdir()
        with self.assertRaises(ValueError):r.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').rmdir();(self.output/'preflight/sources/main.typ').write_text('Changed')
        with self.assertRaises(ValueError):r.verify(self.output,result['manifest_sha256'])

    def test_output_disjointness_existing_output_and_occurrence_bounds(self):
        pin=self.prepare({'main.typ':'<a> @a'})
        with self.assertRaises(ValueError):r.check(self.pre,pin,self.pre/'inside')
        self.output.mkdir()
        with self.assertRaises(ValueError):r.check(self.pre,pin,self.output)
        with patch.object(r,'MAX_OCCURRENCES',1),self.assertRaisesRegex(ValueError,'occurrence limit'):r.check(self.pre,pin,self.root/'over-limit')
        self.assertFalse((self.root/'over-limit').exists())

    def test_cli_preserves_review_required_for_check_and_verify(self):
        pin=self.prepare({'main.typ':'@missing'});tool=Path(r.__file__)
        command=[sys.executable,str(tool),'check','--bundle',str(self.pre),'--sha256',pin,'--output',str(self.output)]
        checked=subprocess.run(command,capture_output=True);self.assertEqual(checked.returncode,2,checked.stderr);result=json.loads(checked.stdout)
        verified=subprocess.run([sys.executable,str(tool),'verify','--bundle',str(self.output),'--sha256',result['manifest_sha256']],capture_output=True)
        self.assertEqual(verified.returncode,2,verified.stderr);self.assertEqual(json.loads(verified.stdout),result)


if __name__=='__main__':unittest.main()
