import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_memory as fixture
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_references as r
sys.path.pop(0)

class ReferenceTests(unittest.TestCase):
    def setUp(self):fixture.MemoryTests.setUp(self)
    def refresh(self):self.req['expected_graph_sha256']=r.k.digest(r.k.canonical(self.g))
    def build(self):return r.build(self.g,self.root,self.req)
    def text(self,text):self.g['cards'][1]['text']=text;self.refresh()
    def test_exact_span_unicode(self):
        self.text('Источник α https://example.org/x?q=1#part далее')
        row=self.build()['references'][0]
        self.assertEqual(self.g['cards'][1]['text'][row['start']:row['end']],row['literal'])
        self.assertEqual(row['field'],'/text')
    def test_duplicates_preserved(self):
        self.text('https://example.org https://example.org')
        report=self.build();self.assertEqual(len(report['references']),2);self.assertEqual(report['unique_literals'],1)
    def test_escaped_pointer(self):
        self.g['cards'][1]['detail']={'a/b~c':['https://example.org']};self.refresh()
        self.assertEqual(self.build()['references'][0]['field'],'/detail/a~1b~0c/0')
    def test_no_reference(self):self.assertEqual(self.build()['references'],[])
    def test_source_missing_is_visible(self):
        self.text('https://example.org');(self.root/'source.txt').unlink()
        self.assertIn('source_missing',self.build()['references'][0]['source_issues'])
    def test_stale_graph(self):
        self.req['expected_graph_sha256']='0'*64
        with self.assertRaisesRegex(r.k.Refusal,'graph_changed'):self.build()
    def test_stale_revision(self):
        self.req['cards'][0]['revision']=2
        with self.assertRaisesRegex(r.k.Refusal,'revision_changed'):self.build()
    def test_count_budget_refuses(self):
        self.text('https://a.example https://b.example')
        with patch.object(r,'MAX_REFERENCES',1),self.assertRaisesRegex(r.k.Refusal,'reference_count_limit'):self.build()
    def test_text_budget(self):
        with patch.object(r,'MAX_TEXT_BYTES',1),self.assertRaisesRegex(r.k.Refusal,'reference_text_limit'):self.build()
    def test_git_reference_flags(self):
        self.assertIn('mutable_git_reference',r.flags('https://github.com/a/b/blob/main/x'))
        self.assertIn('pinned_git_syntax',r.flags('https://github.com/a/b/blob/'+'a'*40+'/x'))
    def test_version_is_only_syntax(self):
        self.assertIn('versioned_identifier_syntax',r.flags('https://hexagonmath.org/2610.00577v1'))
    def test_no_url_repair(self):
        self.text('[x](https://example.org/path).')
        row=self.build()['references'][0];self.assertEqual(row['literal'],'https://example.org/path).')
        self.assertIn('ambiguous_trailing_punctuation',row['flags'])
    def test_local_and_credentials_flagged(self):
        self.assertIn('private_or_local_literal',r.flags('http://127.0.0.1/x'))
        self.assertIn('credentials_present',r.flags('https://u:p@example.org/x'))
        self.assertIn('private_or_local_literal',r.flags('https://[::1]/x'))
    def test_malformed_url(self):self.assertIn('malformed_url',r.flags('https://[invalid'))
    def test_replay_and_no_mutation(self):
        before=copy.deepcopy(self.g);report=self.build()
        self.assertEqual(r.verify(report,r.k.digest(r.k.canonical(report)),self.g,self.root,self.req)['status'],'verified_reference_queue')
        self.assertEqual(self.g,before);self.assertEqual(report['network_requests'],0)
    def test_reanchored_tamper(self):
        report=self.build();report['unique_literals']=99
        with self.assertRaisesRegex(r.k.Refusal,'reference_report_changed'):
            r.verify(report,r.k.digest(r.k.canonical(report)),self.g,self.root,self.req)
    def test_replay_detects_changes_between_mismatched_sources(self):
        self.text('https://example.org');(self.root/'source.txt').write_text('bad one')
        report=self.build();(self.root/'source.txt').write_text('bad two')
        with self.assertRaisesRegex(r.k.Refusal,'reference_report_changed'):
            r.verify(report,r.k.digest(r.k.canonical(report)),self.g,self.root,self.req)
    def test_scanning_does_not_resolve_or_connect(self):
        self.text('http://localhost/x https://example.org')
        with patch('socket.getaddrinfo',side_effect=AssertionError('DNS forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
            report=self.build()
        self.assertEqual(report['network_requests'],0)

    def summary(self,report=None):
        report=self.build() if report is None else report
        return r.summarize(report,r.k.digest(r.k.canonical(report)),self.g,self.root,self.req)
    def test_summary_no_sensitive_literals_or_identifiers(self):
        self.text('https://secret_user:secret_pass@private.example/path?token=secret_token')
        result=self.summary();serialized=r.k.canonical(result).decode()
        for secret in ('secret_user','secret_pass','private.example','secret_token',self.g['cards'][1]['id']):
            self.assertNotIn(secret,serialized)
        self.assertEqual(result['flag_occurrences'],{'credentials_present':1})
    def test_summary_duplicates_and_flag_counts(self):
        self.text('http://localhost/x http://localhost/x')
        result=self.summary()
        self.assertEqual((result['references'],result['unique_literals'],result['repeated_occurrences']),(2,1,1))
        self.assertEqual(result['flag_occurrences']['private_or_local_literal'],2)
    def test_summary_empty(self):
        result=self.summary();self.assertEqual(result['references'],0)
        self.assertEqual(result['flag_occurrences'],{})
    def test_summary_rejects_reanchored_tamper(self):
        report=self.build();report['unique_literals']=9
        with self.assertRaisesRegex(r.k.Refusal,'reference_report_changed'):self.summary(report)
    def test_summary_rejects_wrong_anchor(self):
        with self.assertRaisesRegex(r.k.Refusal,'reference_anchor'):
            r.summarize(self.build(),'0'*64,self.g,self.root,self.req)
    def test_summary_retains_issue_count_without_paths(self):
        self.text('https://example.org');(self.root/'source.txt').unlink()
        result=self.summary();self.assertEqual(result['occurrences_with_source_issues'],1)
        self.assertNotIn('source.txt',r.k.canonical(result).decode())
        self.assertEqual(result['availability_checked'],0);self.assertEqual(result['content_verified'],0)
