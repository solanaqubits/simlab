import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('runner_once',Path(__file__).parents[1]/'ci/self-hosted/run_once.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class SelfhostedValidationTests(unittest.TestCase):
    def setUp(self):
        self.run=dict(head_sha='a'*40,event='workflow_dispatch',actor={'login':'solanaqubits'},
                      triggering_actor={'login':'solanaqubits'},status='queued')
        self.jobs=[dict(status='queued',labels=['self-hosted','geek-work-isolated'])]
    def test_exact_manual_run(self):r.validate_run(self.run,'a'*40)
    def test_wrong_sha(self):
        with self.assertRaises(ValueError):r.validate_run(self.run,'b'*40)
    def test_pr_refused(self):
        self.run['event']='pull_request'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_other_actor(self):
        self.run['triggering_actor']['login']='someone'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_complete_refused(self):
        self.run['status']='completed'
        with self.assertRaises(ValueError):r.validate_run(self.run,'a'*40)
    def test_queued_job(self):r.validate_jobs(self.jobs,'geek-work-isolated')
    def test_already_assigned(self):
        self.jobs[0]['status']='in_progress'
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'geek-work-isolated')
    def test_wrong_labels(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'geek-work-other')
    def test_multiple_jobs(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs*2,'geek-work-isolated')
    def test_label_injection(self):
        with self.assertRaises(ValueError):r.validate_jobs(self.jobs,'x; bad')
