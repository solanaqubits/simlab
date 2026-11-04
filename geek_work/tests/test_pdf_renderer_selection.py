import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_pages as p
import test_pdf_pages as fixtures


class RendererSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfPageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tools=self.f.root/'selected-tools';self.tools.mkdir()
        for name in ('pdfinfo','pdftoppm'):
            path=self.tools/name;path.write_text('#!/usr/bin/python3\nimport sys\nsys.stderr.write("Synthetic selected renderer 25.12.0\\n")\n');path.chmod(0o755)

    def test_explicit_profile_ignores_path_and_pins_both_binaries(self):
        with patch.object(p.shutil,'which',side_effect=AssertionError('no PATH lookup')):
            runtime=p.profile(self.tools)
        p.validate_profile(runtime)
        for name,row in runtime['tools'].items():
            self.assertEqual(row['path'],str(self.tools/name));self.assertEqual(row['sha256'],p.m.sha((self.tools/name).read_bytes()))
            self.assertIn('25.12.0',row['version'])
        self.assertFalse(runtime['shared_libraries_pinned']);self.assertFalse(runtime['os_sandboxed'])

    def test_missing_second_tool_refused_before_execution_without_fallback(self):
        (self.tools/'pdftoppm').unlink()
        with patch.object(p,'run',side_effect=AssertionError('no partial execution')),self.assertRaisesRegex(ValueError,'executable missing'):p.profile(self.tools)

    def test_nonexecutable_or_missing_directory_refused(self):
        (self.tools/'pdfinfo').chmod(0o644)
        with self.assertRaisesRegex(ValueError,'executable missing'):p.profile(self.tools)
        with self.assertRaisesRegex(ValueError,'directory missing'):p.profile(self.tools/'absent')

    def test_changed_selected_binary_rejects_old_anchor_before_pdf_execution(self):
        runtime=p.profile(self.tools);anchor=p.m.sha(p.m.encoded(runtime))
        with (self.tools/'pdfinfo').open('a') as stream:stream.write('# changed binary\n')
        with self.assertRaisesRegex(ValueError,'profile anchor mismatch'):p.render(self.f.binding,self.f.anchor,anchor,self.f.output,self.tools)
        self.assertFalse(self.f.output.exists())

    def test_selected_profile_reaches_render_and_offline_verify_never_uses_runtime(self):
        runtime=p.profile(self.tools);anchor=p.m.sha(p.m.encoded(runtime))
        with patch.object(p,'profile',return_value=runtime) as observe,patch.object(p,'run',side_effect=self.f.worker):
            result=p.render(self.f.binding,self.f.anchor,anchor,self.f.output,self.tools)
        observe.assert_called_once_with(self.tools)
        shutil.rmtree(self.tools)
        with patch.object(p,'profile',side_effect=AssertionError('offline')),patch.object(p,'run',side_effect=AssertionError('offline')):
            self.assertEqual(p.verify(self.f.output,result['manifest_sha256'])['status'],'page_packet_consistent')

    def test_cli_profile_selects_explicit_directory(self):
        r=subprocess.run([sys.executable,str(Path(p.__file__)),'profile','--tool-dir',str(self.tools)],capture_output=True,check=True)
        result=json.loads(r.stdout);self.assertEqual(result['profile'],p.profile(self.tools));self.assertEqual(result['profile_sha256'],p.m.sha(p.m.encoded(result['profile'])))


if __name__=='__main__':unittest.main()
