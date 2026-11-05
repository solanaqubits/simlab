import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_pdf_container as fixtures

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_diagnostics as d


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ContainerPagesTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.output=self.f.root/'diagnostics.json'
    def packet(self,fault=None):
        self.f.fake.fault=fault;result=self.f.render();return result['manifest_sha256']
    def assess(self,pin):
        with patch.object(d.c,'capture',side_effect=AssertionError('offline only')):return d.assess(self.f.output,pin)
    def test_success_no_live_query_or_parent_mutation(self):
        pin=self.packet();before=(self.f.output/'report.json').read_bytes();r=self.assess(pin)
        self.assertEqual(r['status'],'diagnostics_recorded');self.assertEqual(r['failure_classes'],[]);self.assertEqual(r['live_container_state'],'not_checked');self.assertTrue(r['all_recorded_removals_confirmed']);self.assertEqual(before,(self.f.output/'report.json').read_bytes())
        self.assertTrue(all(row['recorded_create_id']=='a'*64 for row in r['operations']))
    def test_timeout_is_not_misclassified_as_missing_next_phase(self):
        r=self.assess(self.packet('create_timeout'));self.assertIn('client_timeout',r['failure_classes']);row=r['operations'][0]
        self.assertEqual(row['first_problem_phase'],'create');self.assertEqual(row['recorded_create_id'],'a'*64);self.assertIn('before',row['missing_phases']);self.assertEqual(row['recorded_cleanup'],'removed');self.assertEqual(row['live_container_state'],'not_checked')
    def test_cleanup_unconfirmed_does_not_claim_current_presence(self):
        r=self.assess(self.packet('cleanup'));self.assertIn('cleanup_unconfirmed',r['failure_classes']);self.assertFalse(r['all_recorded_removals_confirmed']);self.assertEqual(r['live_container_state'],'not_checked');self.assertEqual(r['next_action'],'inspect_recorded_container_on_trusted_host')
    def test_wrong_image_and_configuration_localize_phase(self):
        r=self.assess(self.packet('image'));self.assertIn('runtime_image_rejected',r['failure_classes']);self.assertEqual(r['operations'][0]['first_problem_phase'],'image')
    def test_configuration_rejection_is_not_a_poppler_error(self):
        r=self.assess(self.packet('network'));self.assertIn('container_configuration_or_state_rejected',r['failure_classes']);self.assertEqual(r['operations'][0]['first_problem_phase'],'before');self.assertNotIn('client_nonzero_exit',r['failure_classes'])
    def test_worker_profile_rejection(self):
        r=self.assess(self.packet('profile'));self.assertIn('worker_profile_rejected',r['failure_classes'])
    def test_nonzero_process_and_raw_capture_paths(self):
        r=self.assess(self.packet('process'));self.assertIn('client_nonzero_exit',r['failure_classes']);row=r['operations'][-1];self.assertEqual(row['first_problem_phase'],'start');self.assertIn(row['folder']+'/start.stderr',row['evidence_paths']['start']);self.assertGreater(row['recorded_stderr_bytes'],0)
    def test_format_failure_when_processes_completed(self):
        r=self.assess(self.packet('bad_png'));self.assertIn('format_bounds_or_coverage_rejected',r['failure_classes']);self.assertTrue(all(row['recorded_status']=='completed' for row in r['operations']));self.assertIn('PNG',r['pipeline_findings'][0]['detail'])
    def test_interruption_and_missing_pipeline_are_distinct(self):
        with patch.object(d.c,'TOTAL_TIMEOUT',0):pin=self.packet()
        r=self.assess(pin);self.assertEqual(r['operations'],[]);self.assertIsNone(r['all_recorded_removals_confirmed']);self.assertIn('incomplete_pipeline',r['failure_classes']);self.assertEqual(r['next_action'],'inspect_recorded_failure_evidence')
    def test_explicit_interruption_marker(self):
        original=d.c.m.require;calls=0
        def require(ok,message):
            nonlocal calls
            if message=='operation process failure':
                calls+=1
                if calls==5:raise InterruptedError('fixture boundary')
            return original(ok,message)
        with patch.object(d.c.m,'require',side_effect=require):pin=self.packet()
        r=self.assess(pin);self.assertIn('operator_interruption',r['failure_classes']);self.assertEqual(r['next_action'],'review_interruption_before_retry')
    def test_warning_is_attention_without_invented_failure(self):
        r=self.assess(self.packet('diagnostic'));self.assertEqual(r['status'],'diagnostics_require_attention');self.assertEqual(r['failure_classes'],[]);self.assertTrue(r['recorded_container_stderr_present']);self.assertEqual(r['next_action'],'review_recorded_diagnostics')
    def test_report_reproduction_relocation_and_tamper(self):
        pin=self.packet('create_timeout');result=d.check(self.f.output,pin,self.output);old=self.output.read_bytes();moved=self.f.root/'moved';shutil.copytree(self.f.output,moved);shutil.rmtree(self.f.output)
        with patch.object(d.c,'capture',side_effect=AssertionError('no Docker')):self.assertTrue(d.verify_report(moved,pin,self.output,result['report_sha256'])['reproduced'])
        report=json.loads(old);report['live_container_state']='absent';self.output.write_bytes(d.m.encoded(report))
        with self.assertRaises(ValueError):d.verify_report(moved,pin,self.output,d.m.sha(self.output.read_bytes()))
    def test_wrong_anchor_and_output_inside_archive_refused(self):
        pin=self.packet()
        with self.assertRaises(ValueError):d.check(self.f.output,'0'*64,self.output)
        with self.assertRaises(ValueError):d.check(self.f.output,pin,self.f.output/'inside.json')
        d.check(self.f.output,pin,self.output)
        with self.assertRaises(FileExistsError):d.check(self.f.output,pin,self.output)
    def test_invalid_capture_type_is_not_a_claim_about_runtime_image(self):
        original=self.f.fake.capture
        def capture(command,*args,**kwargs):
            out,err,row=original(command,*args,**kwargs)
            if command[:3]==['docker','image','inspect']:row=dict(row,returncode=False)
            return out,err,row
        with patch.object(self.f.fake,'capture',side_effect=capture):pin=self.packet()
        r=self.assess(pin);self.assertIn('capture_metadata_rejected',r['failure_classes']);self.assertNotIn('runtime_image_rejected',r['failure_classes'])

    def test_cli_failure_status_survives_verify(self):
        pin=self.packet('create_timeout');tool=Path(d.__file__)
        run=subprocess.run([sys.executable,str(tool),'check','--bundle',str(self.f.output),'--sha256',pin,'--output',str(self.output)],capture_output=True);self.assertEqual(run.returncode,2,run.stderr);result=json.loads(run.stdout)
        run=subprocess.run([sys.executable,str(tool),'verify-report','--bundle',str(self.f.output),'--sha256',pin,'--report',str(self.output),'--report-sha256',result['report_sha256']],capture_output=True);self.assertEqual(run.returncode,2,run.stderr);self.assertTrue(json.loads(run.stdout)['reproduced'])


if __name__=='__main__':unittest.main()
