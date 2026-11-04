import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS=Path(__file__).parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import geek_work_model_proposer as m
sys.path.pop(0)

MODEL='claude-haiku-4-5-20251001'


class Engine:
    def __init__(self,output):self.output=output;self.inputs=[]
    def preflight(self,plan):return {'fixture':True}
    def execute(self,plan,snapshot,public,wall_ms):
        self.inputs.append(public)
        return (dict(stdout=self.output,stderr=b'',returncode=0,exit_code=0,issue=None,wall_time_ms=1),
                dict(config_checked=True,cleanup_confirmed=True,stopped_before_removal=True,oom_killed=False))


class ModelProposerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.baseline=b'import json,sys\nprint(json.dumps(sum(json.load(sys.stdin))))\n'
        self.ident=dict(path='/fixture/claude',sha256='a'*64,cli_version='fixture-cli')
        self.corpus=dict(schema='geek-work-tool-corpus-1',cases=[dict(id='private-key',input=[2,3],expected=5)])
        self.plan=m.prepare(self.corpus,self.baseline,'Preserve sum behavior.','sha256:'+'b'*64,MODEL,self.ident,repetitions=1)
        self.proposal=dict(schema='geek-work-proposal-1',baseline_sha256=m.ev.digest(self.baseline),
                           files=[dict(path='candidate.py',content=self.baseline.decode())])
        self.env=dict(subtype='success',is_error=False,num_turns=2,modelUsage={MODEL:{}},
            usage=dict(input_tokens=100,cache_creation_input_tokens=20,cache_read_input_tokens=30,
                       output_tokens=100,server_tool_use={}),permission_denials=[],total_cost_usd=.001,
            structured_output=self.proposal,result='This text must not be used as a proposal.')
        self.engine=Engine(m.ev.encoded(self.proposal));self.calls=[];self.raw_override=None

    def sha(self):return m.ev.digest(m.ev.encoded(self.plan))
    def invoke(self,argv,prompt,env,limits):
        self.calls.append(dict(argv=argv,prompt=prompt,env_keys=sorted(env)))
        return self.raw_override or dict(stdout=m.ev.encoded(self.env),stderr=b'',returncode=0,issue=None,wall_time_ms=10)
    def run_call(self,name='run',identities=None):
        with mock.patch.object(m,'identity',side_effect=identities or [self.ident,self.ident]):
            return m.run(self.plan,self.baseline,self.sha(),Path('/fixture/claude'),self.root/name,
                         invoker=self.invoke,engine=self.engine)
    def verify(self):return m.verify(self.root/'run',self.sha())
    def reseal(self,root=None):
        root=root or self.root/'run';(root/'seal.json').unlink();m.p.seal(root)
    def parsed(self):return m.inspect_reply(m.ev.encoded(self.env),self.plan,m.ev.digest(self.baseline))

    def test_text_only_flags_and_public_prompt(self):
        r=self.run_call();self.assertEqual(r['status'],'MODEL_PROPOSAL_READY');self.assertEqual(self.verify(),r)
        args=self.calls[0]['argv'];public=json.loads(self.calls[0]['prompt'])
        self.assertEqual(args[args.index('--tools')+1],'');self.assertIn('--safe-mode',args)
        self.assertIn('--no-session-persistence',args);self.assertIn('--strict-mcp-config',args)
        self.assertEqual(args[args.index('--setting-sources')+1],'')
        self.assertEqual(set(public),{'schema','task','baseline','output_contract'})
        self.assertNotIn('private-key',json.dumps(public));self.assertNotIn('expected',public)
        self.assertEqual(len(self.calls),1);self.assertEqual(r['transport'],'fixture')

    def test_structured_output_required_without_text_fallback(self):
        self.env['result']=json.dumps(self.proposal);self.env.pop('structured_output')
        r=self.run_call();self.assertEqual(r['status'],'MODEL_PROPOSAL_REJECTED')
        self.assertFalse((self.root/'run/handoff').exists());self.assertEqual(len(self.calls),1)
        self.assertIn('invalid_structured_proposal',r['assessment']['failure_classes']);self.verify()

    def test_wrong_model_or_multiple_models_rejected(self):
        for models in ({'other':{}},{MODEL:{},'fallback':{}}):
            self.env['modelUsage']=models;self.assertIn('provider_model_mismatch',self.parsed()['failure_classes'])

    def test_turn_tools_permission_and_provider_error_rejected(self):
        original=copy.deepcopy(self.env)
        for change,error in [(('num_turns',4),'provider_turn_cap'),(('is_error',True),'provider_error'),
                             (('permission_denials',[{'tool':'Read'}]),'unexpected_permission_denials')]:
            self.env=copy.deepcopy(original);self.env[change[0]]=change[1];self.assertIn(error,self.parsed()['failure_classes'])
        self.env=copy.deepcopy(original);self.env['usage']['server_tool_use']={'web_search_requests':1}
        self.assertIn('unexpected_server_tool_use',self.parsed()['failure_classes'])

    def test_unknown_usage_stays_null_and_blocks_export(self):
        self.env['usage'].pop('cache_read_input_tokens')
        r=self.run_call();self.assertEqual(r['status'],'MODEL_PROPOSAL_REJECTED')
        self.assertIsNone(r['assessment']['token_usage']['input_tokens'])
        self.assertFalse(self.engine.inputs);self.verify()

    def test_token_and_cost_limits_enforced_after_response(self):
        self.env['usage']['input_tokens']=16001;self.env['usage']['output_tokens']=5000;self.env['total_cost_usd']=.11
        errors=self.parsed()['failure_classes']
        for e in ('total_token_cap','aggregate_output_cap','estimated_cost_cap'):self.assertIn(e,errors)

    def test_aggregate_turn_cap_not_single_turn_comparison(self):
        self.env['usage']['output_tokens']=2000
        self.assertEqual(self.parsed()['failure_classes'],[])

    def test_unknown_estimate_never_becomes_zero(self):
        self.env.pop('total_cost_usd');r=self.run_call()
        self.assertIsNone(r['assessment']['provider_estimated_cost_usd']);self.assertIsNone(r['actual_monetary_cost'])
        self.assertIn('unknown_cost_estimate',r['assessment']['failure_classes'])

    def test_cost_estimate_separate_from_ledger_billing(self):
        r=self.run_call();d=m.g.parse((self.root/'run/ledger.json').read_bytes())
        self.assertEqual(r['assessment']['provider_estimated_cost_usd'],'0.001')
        self.assertIsNone(d['tasks'][0]['attempts'][0]['monetary_cost']);self.assertFalse(r['financial_qualification'])
        self.assertEqual(r['assessment']['token_usage'],dict(input_tokens=150,output_tokens=100))

    def test_wrong_sha_and_extra_files_or_metadata_rejected(self):
        original=copy.deepcopy(self.proposal)
        for mode in ('sha','files','metadata'):
            self.proposal=copy.deepcopy(original)
            if mode=='sha':self.proposal['baseline_sha256']='0'*64
            if mode=='files':self.proposal['files']*=2
            if mode=='metadata':self.proposal['files'][0]['symlink']='/host/grader'
            self.env['structured_output']=self.proposal
            self.assertIn('invalid_structured_proposal',self.parsed()['failure_classes'])

    def test_transport_failure_does_not_export_valid_reply(self):
        self.raw_override=dict(stdout=m.ev.encoded(self.env),stderr=b'',returncode=-9,issue='EXEC_TIMEOUT',wall_time_ms=45001)
        r=self.run_call();self.assertEqual(r['status'],'MODEL_PROPOSAL_REJECTED');self.assertFalse(self.engine.inputs)
        self.assertIn('EXEC_TIMEOUT',r['assessment']['failure_classes']);self.verify()

    def test_cli_before_drift_prevents_call_after_drift_records_attempt(self):
        other=dict(self.ident,sha256='c'*64)
        with self.assertRaisesRegex(ValueError,'cli_identity_mismatch'):self.run_call('before',[other])
        self.assertFalse(self.calls)
        r=self.run_call(identities=[self.ident,other]);self.assertIn('cli_changed',r['assessment']['failure_classes'])
        self.assertEqual(len(self.calls),1);self.assertFalse(self.engine.inputs);self.verify()

    def test_plan_drift_prevents_call(self):
        sha=self.sha();self.plan['evaluation']['corpus']['cases'][0]['expected']=99
        with self.assertRaisesRegex(ValueError,'expected_plan_mismatch'):
            m.run(self.plan,self.baseline,sha,Path('/fixture'),self.root/'run',invoker=self.invoke)
        self.assertFalse(self.calls)

    def test_model_alias_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'dated_model_id'):m.profile('haiku',self.ident)

    def test_no_duplicate_keys_or_malformed_envelopes(self):
        for raw in (b'{"structured_output":null,"structured_output":{}}',b'[]',b'null',b'not json'):
            parsed=m.inspect_reply(raw,self.plan,m.ev.digest(self.baseline))
            self.assertIn('invalid_provider_envelope',parsed['failure_classes'])

    def test_relay_does_not_execute_model_code(self):
        doc=copy.deepcopy(self.proposal)
        doc['files'][0]['content']="raise RuntimeError('MODEL_CODE_EXECUTED')\n"
        result=subprocess.run([sys.executable,'-I','-c',m.relay_program(doc).decode()],capture_output=True,check=True)
        self.assertEqual(result.stdout,m.ev.encoded(doc))

    def test_environment_does_not_inherit_prompt_redirect_or_debug_overrides(self):
        with mock.patch.dict(os.environ,{'ANTHROPIC_BASE_URL':'https://untrusted.invalid','CLAUDE_CODE_SYSTEM_PROMPT':'secret',
                                       'ANTHROPIC_API_KEY':'fixture-secret'},clear=False):
            env=m.environment(m.LIMITS)
        self.assertNotIn('ANTHROPIC_BASE_URL',env);self.assertNotIn('CLAUDE_CODE_SYSTEM_PROMPT',env)
        self.assertEqual(env['ANTHROPIC_API_KEY'],'fixture-secret')

    def test_output_directory_is_not_overwritten(self):
        self.run_call()
        with self.assertRaises(FileExistsError):self.run_call(identities=[self.ident])
        self.assertEqual(len(self.calls),1)

    def test_resealed_financial_claim_rejected(self):
        self.run_call();path=self.root/'run/receipt.json';r=m.g.parse(path.read_bytes())
        r['actual_monetary_cost']='0';path.write_bytes(m.ev.encoded(r));self.reseal()
        with self.assertRaisesRegex(ValueError,'receipt_telemetry'):self.verify()

    def test_resealed_prompt_or_relay_rejected(self):
        self.run_call();path=self.root/'run/relay.py';path.write_bytes(b'print("fake")');self.reseal()
        with self.assertRaisesRegex(ValueError,'relay_changed'):self.verify()

    def test_incomplete_handoff_retains_model_attempt(self):
        self.engine.preflight=mock.Mock(side_effect=ValueError('fixture daemon failure'))
        r=self.run_call();self.assertEqual(r['status'],'MODEL_PROPOSAL_REJECTED')
        self.assertEqual(r['handoff_errors'],['handoff_incomplete']);self.assertEqual(len(self.calls),1)
        self.assertEqual(r['assessment']['token_usage']['output_tokens'],100);self.verify()

    def test_complete_evaluation_and_replay(self):
        self.run_call();r=m.evaluate(self.root/'run',self.sha(),self.root/'evaluation',Engine(b'5'))
        self.assertEqual(r['status'],'CORRECTNESS_PRESERVED');self.assertFalse(r['automatic_promotion'])
        self.assertEqual(m.verify_evaluation(self.root/'evaluation',self.sha()),r)

    def test_model_rejection_cannot_enter_evaluation(self):
        self.env['modelUsage']={'other':{}};self.run_call()
        with self.assertRaisesRegex(ValueError,'model_proposal_not_ready'):
            m.evaluate(self.root/'run',self.sha(),self.root/'evaluation',Engine(b'5'))
        self.assertFalse((self.root/'evaluation').exists())

    def test_bounded_transport_empty_cwd_timeout_and_flood(self):
        limits=dict(m.LIMITS,wall_ms=2000,transport_output_bytes=1024)
        r=m.invoke([sys.executable,'-c','import os;print(os.listdir("."))'],b'',{'PATH':'/usr/bin:/bin'},limits)
        self.assertEqual(r['stdout'].strip(),b'[]')
        r=m.invoke([sys.executable,'-c','import os;os.write(1,b"x"*10000)'],b'',{},limits)
        self.assertEqual(r['issue'],'OUTPUT_LIMIT');self.assertLessEqual(len(r['stdout']),1024)
        limits['wall_ms']=100
        r=m.invoke([sys.executable,'-c','import time;time.sleep(5)'],b'x'*100000,{},limits)
        self.assertEqual(r['issue'],'EXEC_TIMEOUT')


if __name__=='__main__':unittest.main()
