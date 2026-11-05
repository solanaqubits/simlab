import json
import os
from pathlib import Path
import sys
import unittest

TOOLS=Path(__file__).parents[1]/'tools'
sys.path.insert(0,str(TOOLS));import geek_work_claude as a;sys.path.pop(0)


class ClaudeAdapterTests(unittest.TestCase):
    def sample(self):
        return dict(subtype='success',is_error=False,result='```json\n{"accept":true,"failure_classes":[],"reason":"Faithful"}\n```',
                    usage=dict(input_tokens=10,cache_creation_input_tokens=20,cache_read_input_tokens=30,output_tokens=5,
                               server_tool_use=dict(web_search_requests=0)),modelUsage={'pinned-model':{}},total_cost_usd=0.001,num_turns=1)

    def test_cached_tokens_count_as_input_work(self):
        p=a.parse_reply(json.dumps(self.sample()),'pinned-model')
        self.assertEqual(p['tokens'],dict(input_tokens=60,output_tokens=5))
        self.assertEqual(p['failure_classes'],[])
        self.assertEqual(p['provider_estimated_cost_usd'],'0.001')
        self.assertNotIn('monetary_cost',p)

    def test_missing_telemetry_is_not_zero(self):
        doc=self.sample();del doc['usage']['cache_read_input_tokens'];doc.pop('total_cost_usd')
        p=a.parse_reply(json.dumps(doc),'pinned-model')
        self.assertIsNone(p['tokens']['input_tokens']);self.assertIsNone(p['provider_estimated_cost_usd'])

    def test_model_change_and_extra_provider_turn_fail(self):
        doc=self.sample();doc['num_turns']=2
        p=a.parse_reply(json.dumps(doc),'other-model')
        self.assertIn('provider_model_mismatch',p['failure_classes'])
        self.assertIn('unexpected_provider_turn_count',p['failure_classes'])

    def test_refusal_and_broken_json_are_outcomes(self):
        doc=self.sample();doc['result']='I cannot do this';doc['is_error']=True
        p=a.parse_reply(json.dumps(doc),'pinned-model')
        self.assertIsNone(p['response']);self.assertIn('invalid_response',p['failure_classes'])
        self.assertIn('provider_error',p['failure_classes'])

    def test_no_tools_or_fallback_in_command(self):
        c=a.command('/bin/claude','fixed','0.1')
        self.assertIn('--safe-mode',c);self.assertIn('--no-session-persistence',c)
        self.assertEqual(c[c.index('--tools')+1],'')
        self.assertNotIn('--fallback-model',c);self.assertNotIn('--continue',c)
        self.assertIn('--strict-mcp-config',c)

    def test_real_local_timeout_kills_process_group(self):
        script='import os,time; print(os.getpid(),flush=True); os.fork(); time.sleep(60)'
        r=a.invoke([sys.executable,'-u','-c',script],b'',os.environ.copy(),0.15)
        self.assertTrue(r['timed_out']);self.assertEqual(r['returncode'],-9)
        self.assertLess(r['wall_time_ms'],3000)
        self.assertTrue(r['stdout'].strip())

    def test_tool_use_cannot_be_silently_accepted(self):
        doc=self.sample();doc['usage']['server_tool_use']['web_search_requests']=1
        p=a.parse_reply(json.dumps(doc),'pinned-model')
        self.assertIn('unexpected_provider_tool_use',p['failure_classes'])


if __name__=='__main__':unittest.main()
