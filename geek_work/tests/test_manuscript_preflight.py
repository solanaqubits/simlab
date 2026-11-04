import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import geek_work_manuscript_preflight as p


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.blobs = {'main.tex': br'\input{chapter}\bibliography{refs}\includegraphics{plot.png}',
                      'chapter.tex': br'\label{sec:a}\ref{sec:a}\cite[p. 2]{known}',
                      'refs.bib': b'@article{known, title={A {nested} title}}',
                      'plot.png': b'opaque asset bytes, not a decoded PNG'}
        self.write()

    def write(self):
        for name, raw in self.blobs.items():
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def selection(self):
        return dict(schema='geek-work-manuscript-preflight-selection-1', entry='main.tex', files=sorted(self.blobs))

    def analyze(self):
        return p.analyze(self.selection(), self.blobs)

    def codes(self):
        return [f['code'] for f in self.analyze()['findings']]

    def test_reachable_literal_graph_and_asset_identity(self):
        report = self.analyze()
        self.assertEqual(report['status'], 'no_findings_in_supported_subset')
        self.assertEqual(report['reachable_tex'], ['chapter.tex', 'main.tex'])
        self.assertEqual(report['active_bibliographies'], ['refs.bib'])
        self.assertFalse(report['full_syntax_coverage'])
        self.assertFalse(report['compilation_verified'])
        self.assertEqual(report['files']['plot.png']['sha256'], p.m.sha(self.blobs['plot.png']))

    def test_unresolved_references_citations_and_duplicates(self):
        self.blobs['chapter.tex'] += br'\label{sec:a}\ref{missing}\cite{absent}'
        self.blobs['refs.bib'] += b'\n@book{known, title={Duplicate}}'
        self.assertCountEqual(self.codes(), ['duplicate_label', 'duplicate_bib_key', 'unresolved_reference', 'unresolved_citation'])

    def test_unreachable_definitions_do_not_satisfy_references(self):
        self.blobs['chapter.tex'] += br'\ref{unused}\cite{unloaded}'
        self.blobs['orphan.tex'] = br'\label{unused}'
        self.blobs['orphan.bib'] = b'@book{unloaded,title={Not loaded}}'
        self.assertCountEqual(self.codes(), ['unresolved_reference', 'unresolved_citation'])

    def test_comments_escaped_percent_and_line_locations(self):
        self.blobs['chapter.tex'] = b'% \\ref{comment}\n\\% \\ref{visible}\n'
        report = self.analyze()
        self.assertEqual([(x['value'], x['line']) for x in report['findings']], [('visible', 2)])

    def test_dynamic_conditional_and_opaque_content_require_review(self):
        self.blobs['chapter.tex'] = br'\begin{verbatim}\ref{fake}\end{verbatim}\verb|\cite{fake}|\ifdefined\X\ref{real}\fi\input{\macro}'
        report = self.analyze()
        self.assertTrue(any(f['code'] == 'manual_review' for f in report['findings']))
        self.assertNotIn('fake', [f['value'] for f in report['findings']])
        self.assertIn('unresolved_reference', self.codes())

    def test_missing_selection_not_read_or_confused_with_missing_disk(self):
        self.blobs['main.tex'] += br'\input{secret}\includegraphics{unknown}'
        (self.project / 'secret.tex').write_text('private text')
        report = self.analyze()
        self.assertIn('dependency_not_selected', self.codes())
        self.assertIn('manual_review', self.codes())
        self.assertNotIn('secret.tex', report['files'])

    def test_cycle_terminates_and_reports(self):
        self.blobs['chapter.tex'] += br'\input{main}'
        self.assertEqual(self.codes(), ['include_cycle'])

    def test_bibliography_body_and_unsupported_syntax(self):
        self.blobs['refs.bib'] = b'@comment{ignore @book{fake, title={fake}}}\n@article{known,title={A @book{hidden,} }}'
        self.assertEqual(self.codes(), [])
        self.blobs['refs.bib'] = b'@article(known,title="a ) @book{fake,}")'
        self.assertIn('manual_review', self.codes())
        self.assertIn('unresolved_citation', self.codes())
        self.blobs['refs.bib'] = b'@article{known,title={unclosed}'
        self.assertIn('manual_review', self.codes())

    def test_snapshot_reproduce_and_tamper(self):
        out = self.root / 'bundle'
        result = p.check(self.project, self.selection(), out)
        self.assertEqual(p.verify(out, result['manifest_sha256'])['status'], 'reproduced')
        (out / 'sources' / 'plot.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'recomputed report'):
            p.verify(out, result['manifest_sha256'])
        self.assertEqual((self.project / 'plot.png').read_bytes(), self.blobs['plot.png'])

    def test_resealed_wrong_report_extra_files_and_anchor(self):
        out = self.root / 'bundle'
        result = p.check(self.project, self.selection(), out)
        with self.assertRaisesRegex(ValueError, 'anchor'):
            p.verify(out, '0' * 64)
        (out / 'sources' / 'extra').mkdir()
        with self.assertRaisesRegex(ValueError, 'file set'):
            p.verify(out, result['manifest_sha256'])
        (out / 'sources' / 'extra').rmdir()
        report = json.loads((out / 'report.json').read_bytes())
        report['compilation_verified'] = True
        raw = p.m.encoded(report)
        (out / 'report.json').write_bytes(raw)
        manifest = p.m.encoded(dict(schema='geek-work-manuscript-preflight-bundle-1', report_sha256=p.m.sha(raw)))
        (out / 'manifest.json').write_bytes(manifest)
        with self.assertRaisesRegex(ValueError, 'recomputed report'):
            p.verify(out, p.m.sha(manifest))

    def test_selection_path_and_case_collisions(self):
        for files in [['../x.tex'], ['/x.tex'], ['.private.tex'], ['main.tex', 'MAIN.tex'], ['main.tex', 'main.tex/a.tex']]:
            with self.subTest(files=files), self.assertRaises(ValueError):
                p.config(dict(schema=self.selection()['schema'], entry='main.tex', files=files))
        self.blobs['main.tex'] += br'\input{../outside}\includegraphics{https://example.org/a.png}'
        self.assertEqual(self.codes(), ['manual_review', 'manual_review'])

    def test_symlink_intermediate_leaf_and_fifo_refused(self):
        (self.project / 'link').symlink_to(self.project, target_is_directory=True)
        (self.project / 'leaf.tex').symlink_to(self.project / 'main.tex')
        os.mkfifo(self.project / 'pipe.tex')
        for name in ['link/main.tex', 'leaf.tex', 'pipe.tex']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.read_selected(self.project, name)

    def test_limits_and_exclusive_outputs(self):
        out = self.root / 'bundle'
        with patch.object(p, 'MAX_TOTAL', 10), self.assertRaisesRegex(ValueError, 'total byte limit'):
            p.check(self.project, self.selection(), out)
        self.assertFalse(out.exists())
        with patch.object(p, 'MAX_FILE', 10), self.assertRaisesRegex(ValueError, 'file byte limit'):
            p.check(self.project, self.selection(), out)
        p.check(self.project, self.selection(), out)
        with self.assertRaises(FileExistsError):
            p.check(self.project, self.selection(), out)

    def test_failed_write_has_no_completion_manifest(self):
        original = Path.open
        out = self.root / 'bundle'
        def failing(path, *args, **kwargs):
            if path == out / 'report.json':
                raise OSError('injected failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', failing), self.assertRaises(OSError):
            p.check(self.project, self.selection(), out)
        self.assertFalse((out / 'manifest.json').exists())
        self.assertEqual((self.project / 'main.tex').read_bytes(), self.blobs['main.tex'])

    def test_cli_check_and_verify(self):
        selection = self.root / 'selection.json'
        selection.write_text(json.dumps(self.selection()))
        out = self.root / 'cli'
        base = [sys.executable, p.__file__]
        result = json.loads(subprocess.check_output(base + ['check', '--root', str(self.project), '--selection', str(selection), '--output', str(out)]))
        verified = json.loads(subprocess.check_output(base + ['verify', '--bundle', str(out), '--sha256', result['manifest_sha256']]))
        self.assertEqual(verified['status'], 'reproduced')
