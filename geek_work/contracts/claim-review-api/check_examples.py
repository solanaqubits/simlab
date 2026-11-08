#!/usr/bin/env python3
"""Offline schema/spec checks only. No HTTP server or CLI jobs are started.

Developer check uses already-installed jsonschema; not a new runtime dependency.
"""
import copy
import json
from pathlib import Path
from importlib.metadata import version
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parent


def run():
    schemas={kind:json.loads((ROOT/(kind+'.schema.json')).read_bytes()) for kind in ('request','response')}
    validators={kind:Draft202012Validator(schema) for kind,schema in schemas.items()}
    for schema in schemas.values():Draft202012Validator.check_schema(schema)
    valid=[]; invalid=[]
    for file in sorted((ROOT/'examples').glob('*.json')):
        kind='request' if '.request.' in file.name else 'response'
        validators[kind].validate(json.loads(file.read_bytes()));valid.append(file.name)

    def reject(name,kind,value):
        assert not validators[kind].is_valid(value),name
        invalid.append(name)

    for kind in ('request','response'):
        for file in sorted((ROOT/'examples').glob('*.'+kind+'.json')):
            original=json.loads(file.read_bytes())
            changed=copy.deepcopy(original);changed['unexpected']='not allowed'
            reject(file.name+':extra-field',kind,changed)
            changed=copy.deepcopy(original);del changed['request_id']
            reject(file.name+':missing-request-id',kind,changed)
    request=json.loads((ROOT/'examples/builds.request.json').read_bytes())
    for key,value in [('context_id','../outside'),('draft_id','/etc/passwd'),('draft_sha256','0'*63),('operation','run-shell'),('draft_sha256','0'*64+'\n'),('context_id',request['context_id']+'\n')]:
        bad=copy.deepcopy(request);bad[key]=value;reject('request:'+key,'request',bad)
    for key in ('path','argv','source_sha256','expectations_sha256','extraction_report'):
        bad=copy.deepcopy(request);bad[key]='candidate supplied';reject('request:'+key,'request',bad)
    chunk=json.loads((ROOT/'examples/artifacts-read.request.json').read_bytes())
    for key,value in [('offset',-1),('offset',True),('max_bytes',0),('max_bytes',65537)]:
        bad=copy.deepcopy(chunk);bad[key]=value;reject('chunk:'+key+':'+str(value),'request',bad)
    draft=json.loads((ROOT/'examples/drafts.request.json').read_bytes())
    for val in ('not base64!','a','e30=\n'):
        bad=copy.deepcopy(draft);bad['record_base64']=val;reject('draft:bad-base64:'+repr(val),'request',bad)
    response=json.loads((ROOT/'examples/job-built.response.json').read_bytes())
    for flag in response['assurances']:
        bad=copy.deepcopy(response);bad['assurances'][flag]=True;reject('flag:'+flag,'response',bad)
    for name,edit in [
        ('wrong-exit',lambda j:j.update(exit_code=2)),
        ('missing-transport',lambda j:j['reports'].pop()),
        ('duplicate-report-kind',lambda j:j['reports'].__setitem__(0,copy.deepcopy(j['reports'][1]))),
        ('built-extraction-needs-context',lambda j:j['reports'][0].update(status='needs_context')),
        ('built-transport-not-preserved',lambda j:j['reports'][2].update(status='review_required')),
        ('made-up-extraction-status',lambda j:j['reports'][0].update(status='verified')),
        ('built-has-failure',lambda j:j.update(failure={'code':'timeout','message':'bad'})),
    ]:
        bad=copy.deepcopy(response);edit(bad['data']);reject(name,'response',bad)
    blocked=json.loads((ROOT/'examples/job-blocked.response.json').read_bytes())
    blocked['data']['package_available']=True;reject('blocked-package-available','response',blocked)
    failed=json.loads((ROOT/'examples/job-failed.response.json').read_bytes())
    failed['data']['reports']=response['data']['reports'];reject('failed-with-validation-results','response',failed)
    limits=json.loads((ROOT/'limits.json').read_bytes())
    assert schemas['response']['$defs']['context']['properties']['data']['properties']['limits']['const']==limits
    assert limits['record_bytes']+limits['expectations_bytes']==limits['extraction_combined_bytes']
    assert ((limits['record_bytes']+2)//3)*4==1398104
    assert ((limits['artifact_chunk_bytes']+2)//3)*4==87384
    assert limits['waiting_queue_depth']==0 and limits['active_jobs_per_context']==1
    return dict(schema_draft='2020-12',jsonschema_version=version('jsonschema'),
                valid_examples=len(valid),negative_schema_cases=len(invalid),
                examples=valid,negative_cases=invalid,limits_consistent=True,
                http_server_implemented=False,http_tests_run=False,cli_jobs_run=False)


if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
