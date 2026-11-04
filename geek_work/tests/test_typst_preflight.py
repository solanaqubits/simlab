import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_typst_preflight as t


class TypstPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir();self.output=self.root/'bundle';self.selection=self.root/'selection.json'
        self.files={'main.typ':b'#include "chapters/one.typ"\n#bibliography("refs.bib")\n','chapters/one.typ':b'#image("../assets/plot.png")\n#import "/defs.typ"\n','defs.typ':b'Static definitions placeholder','refs.bib':b'@article{k,title={Fixture}}','assets/plot.png':b'opaque'}
        self.write_files()

    def write_files(self):
        for name,raw in self.files.items():p=self.project/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.spec=dict(schema='geek-work-typst-preflight-selection-1',entry='main.typ',files=list(self.files))

    def check(self):
        self.selection.write_bytes(t.m.encoded(self.spec));return t.check(self.project,self.selection,t.m.sha(self.selection.read_bytes()),self.output)

    def codes(self,report):return {x['code'] for x in report['findings']}

    def reseal(self):
        p=self.output/'manifest.json';x=json.loads(p.read_bytes());x['files']={n:t.m.sha((self.output/n).read_bytes()) for n in x['files']};p.write_bytes(t.m.encoded(x));return t.m.sha(p.read_bytes())

    def test_file_relative_root_relative_and_bibliography_graph(self):
        r=self.check();self.assertEqual(r['status'],'no_dependency_findings_in_supported_subset');report=json.loads((self.output/'report.json').read_bytes())
        self.assertEqual(set(report['reachable_typst']),{'main.typ','chapters/one.typ','defs.typ'});self.assertIn('assets/plot.png',{x['target'] for x in report['dependencies']});self.assertFalse(report['reference_semantics_checked'])
        self.assertTrue(t.verify(self.output,r['manifest_sha256'])['reproduced'])

    def test_missing_dependency_is_selection_finding_not_disk_discovery(self):
        self.spec['files'].remove('assets/plot.png');r=self.check();self.assertEqual(r['status'],'review_required');report=json.loads((self.output/'report.json').read_bytes());self.assertIn('dependency_not_selected',self.codes(report));self.assertTrue((self.project/'assets/plot.png').exists())

    def test_cycles_and_unreached_typst(self):
        self.files['defs.typ']=b'#include "/main.typ"';self.files['unused.typ']=b'#include "missing.typ"';self.write_files();report=t.analyze(self.spec,self.files)
        self.assertIn('dependency_cycle',self.codes(report));self.assertEqual(report['unreached_selected_typst'],['unused.typ']);self.assertNotIn('dependency_not_selected',self.codes(report))

    def test_comments_nested_comments_and_escaped_hash(self):
        source=b'// #include "gone.typ"\n/* outer /* #image("gone.png") */ closed */\n\\#include "ignored.typ"\nPlain text'
        edges,findings=t.extract('main.typ',source);self.assertEqual(edges,[]);self.assertEqual(findings,[])

    def test_quoted_path_comment_characters_and_quoted_hash(self):
        edges,issues=t.extract('main.typ',b'#image("plot#one.png") // comment\n')
        self.assertEqual(edges[0]['target'],'plot#one.png');self.assertFalse(issues)
        _,issues=t.extract('main.typ',b'"Markup #include("hidden.typ")"')
        self.assertIn('unanalysed_quoted_region',{x['code'] for x in issues})

    def test_dynamic_paths_packages_and_unknown_expressions_need_review(self):
        cases=[b'#include filename',b'#import "@preview/package:1.0.0"',b'#image("a.png" + suffix)',b'#let f = x => x',b'#bibliography(("a.bib", "b.bib"))']
        for source in cases:
            with self.subTest(source=source):
                _,issues=t.extract('main.typ',source);self.assertTrue(issues)
        edges,issues=t.extract('main.typ',b'#include "a.typ" + suffix');self.assertFalse(edges);self.assertTrue(issues)

    def test_bare_nested_calls_and_additional_arguments_are_conservative(self):
        edges,issues=t.extract('main.typ',b'#figure(image("plot.png"), caption: [Fixture])')
        self.assertEqual(edges[0]['target'],'plot.png');self.assertIn('bare_code_candidate_requires_review',{x['code'] for x in issues})
        _,issues=t.extract('main.typ',b'#image("plot.png", width: 20pt)');self.assertIn('additional_arguments_require_review',{x['code'] for x in issues})

    def test_raw_urls_unterminated_and_escaped_paths_are_explicit(self):
        cases=[b'`#include "gone.typ"`',b'https://example.invalid #include "ok.typ"',b'/* unclosed',b'#image("unclosed',b'#include "a\\u{2e}typ"']
        for source in cases:
            with self.subTest(source=source):self.assertTrue(t.extract('main.typ',source)[1])
        edges,_=t.extract('main.typ',cases[1]);self.assertEqual(edges[0]['target'],'ok.typ')

    def test_path_normalization_and_escape_refusal(self):
        self.assertEqual(t.target('a/b.typ','../c.typ'),'c.typ');self.assertEqual(t.target('a/b.typ','./c.typ'),'a/c.typ');self.assertEqual(t.target('a/b.typ','/c.typ'),'c.typ')
        for value in ('../../outside.typ','//bad.typ','https://outside/x.typ','@local/pkg:1.0.0','./.secret.typ','a\\b.typ'):
            with self.subTest(value=value),self.assertRaises(ValueError):t.target('a/b.typ',value)

    def test_symlink_missing_and_invalid_utf8_fail_before_output(self):
        p=self.project/'defs.typ';p.unlink();p.symlink_to(self.project/'main.typ')
        with self.assertRaises(ValueError):self.check()
        p.unlink()
        with self.assertRaises(ValueError):self.check()
        p.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):self.check()
        self.assertFalse(self.output.exists())

    def test_selection_bounds_collisions_and_hash(self):
        for names in (['main.typ','MAIN.typ'],['main.typ','main.typ/child.typ'],['../main.typ'],['main.tex']):
            with self.subTest(names=names),self.assertRaises(ValueError):t.config(dict(schema=self.spec['schema'],entry=names[0],files=names))
        self.selection.write_bytes(t.m.encoded(self.spec))
        with self.assertRaisesRegex(ValueError,'selection SHA'):t.check(self.project,self.selection,'0'*64,self.output)
        with patch.object(t,'MAX_TOTAL',1),self.assertRaisesRegex(ValueError,'total limit'):self.check()
        with patch.object(t,'MAX_TOKENS',1),self.assertRaisesRegex(ValueError,'token limit'):t.extract('main.typ',b'a b c')

    def test_resealed_report_and_source_cannot_hide_findings(self):
        self.check();p=self.output/'report.json';x=json.loads(p.read_bytes());x['compilation_performed']=True;p.write_bytes(t.m.encoded(x));pin=self.reseal()
        with self.assertRaisesRegex(ValueError,'preflight hashes'):t.verify(self.output,pin)

    def test_exact_tree_and_relocated_verification_without_execution(self):
        r=self.check();copy=self.root/'relocated';shutil.copytree(self.output,copy);shutil.rmtree(self.project);shutil.rmtree(self.output);self.selection.unlink()
        with patch('subprocess.run',side_effect=AssertionError('no process')):self.assertTrue(t.verify(copy,r['manifest_sha256'])['reproduced'])
        (copy/'extra').mkdir()
        with self.assertRaises(ValueError):t.verify(copy,r['manifest_sha256'])

    def test_review_findings_exit_two_for_check_and_verify(self):
        self.spec['files'].remove('defs.typ');self.selection.write_bytes(t.m.encoded(self.spec))
        r=subprocess.run([sys.executable,t.__file__,'check','--root',str(self.project),'--selection',str(self.selection),'--selection-sha256',t.m.sha(self.selection.read_bytes()),'--output',str(self.output)],capture_output=True)
        self.assertEqual(r.returncode,2,r.stderr);pin=json.loads(r.stdout)['manifest_sha256']
        r=subprocess.run([sys.executable,t.__file__,'verify','--bundle',str(self.output),'--sha256',pin],capture_output=True);self.assertEqual(r.returncode,2,r.stderr)

    def test_compile_request_uses_exact_snapshot_without_running_compiler(self):
        with patch('subprocess.run',side_effect=AssertionError('no compiler')):result=self.check()
        raw=(self.output/'request.json').read_bytes();request=json.loads(raw);self.assertEqual(result['compile_request_sha256'],t.m.sha(raw))
        t.compiler.validate_request(request,'geek-work-manuscript-compile-request-1','.typ')
        for row in request['files']:self.assertEqual(t.m.sha((self.output/'sources'/row['path']).read_bytes()),row['sha256'])
        self.assertEqual(request['entry'],'main.typ')

    def test_no_instruction_execution_and_disjoint_outputs(self):
        self.files['main.typ']=b'#eval("raise SystemExit")\n#import "@preview/do-not-fetch:1.0.0"';self.write_files()
        with patch('subprocess.run',side_effect=AssertionError('no execution')):self.assertEqual(self.check()['status'],'review_required')
        with self.assertRaises(ValueError):t.check(self.project,self.selection,t.m.sha(self.selection.read_bytes()),self.project/'out')


if __name__=='__main__':unittest.main()
