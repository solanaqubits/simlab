#!/usr/bin/env python3
"""Explicit v3 adapter with a source-bound string-field index; no citation repair."""
import argparse
from pathlib import Path
import subprocess
import sys

import geek_work_fields as fields
import geek_work_structured as v2
import knowledge as k

INSTRUCTION = v2.INSTRUCTION + (
    ' source.field_index lists the exact allowed string-field JSON Pointers for each card. '
    'Copy a pointer from that list and quote its value in the original card. '
    'Arrays and dictionaries are not citable string fields: use a listed element pointer. '
    'Do not merge list items or infer a different pointer from your quote.')
command=v2.command
invoke=v2.invoke
parse_reply=v2.parse_reply
aggregate_output_cap=v2.aggregate_output_cap


def tool_pins():
    return {**v2.tool_pins(),Path(__file__).name:k.digest(Path(__file__).read_bytes()),
            Path(fields.__file__).name:k.digest(Path(fields.__file__).read_bytes())}


def profile(model,version):
    p=v2.profile(model,version)
    p['configuration'].update(adapter='geek-work-addressed-support-3',
        adapter_sha256=k.digest(Path(__file__).read_bytes()),
        structured_adapter_sha256=k.digest(Path(v2.__file__).read_bytes()),
        field_indexer_sha256=k.digest(Path(fields.__file__).read_bytes()),
        instruction_sha256=k.digest(INSTRUCTION.encode()),
        field_index='complete exact string pointers, bound to full unchanged context')
    return p


def validate_request_index(request):
    k.require(type(request) is dict and type(request.get('input')) is dict,
              'invalid_input:request')
    source=request['input'].get('source')
    k.require(type(source) is dict, 'invalid_input:source')
    if 'memory' not in source:
        k.require('field_index' not in source, 'invalid_witness:index_without_memory')
    else:
        expected=fields.make_index(source['memory'])
        k.require(source.get('field_index')==expected, 'invalid_witness:citation_index')


def validate_plan_indices(plan):
    trials=plan.get('trials')
    k.require(type(trials) is list and 0<len(trials)<=32, 'resource_limit:index_trials')
    for trial in trials:
        k.require(type(trial) is dict and 'request' in trial, 'invalid_input:trial')
        validate_request_index(trial['request'])


def check_request(parsed,request):
    try:validate_request_index(request)
    except (k.Refusal,ValueError):return ['invalid_citation_index']
    return v2.check_request(parsed,request)


def run(plan,output,executable,version):
    validate_plan_indices(plan)
    return v2.pilot.run(plan,output,executable,version,adapter=sys.modules[__name__])


def prepare(corpus,graph,root,model,version,seed=277):
    plan=v2.prepare(corpus,graph,root,model,version,seed)
    plan.update(protocol='geek-work-addressed-support-3',model_profile=profile(model,version),tool_pins=tool_pins())
    for trial in plan['trials']:
        request=trial['request'];request['instruction']=INSTRUCTION
        source=request['input']['source']
        if 'memory' in source:source['field_index']=fields.make_index(source['memory'])
    return plan


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    a=subs.add_parser('prepare');a.add_argument('corpus',type=Path);a.add_argument('graph',type=Path)
    a.add_argument('--root',type=Path,required=True);a.add_argument('--model',required=True)
    a.add_argument('--cli-version',required=True,help='Declared profile; execution rechecks the actual CLI version')
    b=subs.add_parser('run');b.add_argument('plan',type=Path);b.add_argument('--claude',type=Path,required=True)
    for cmd in (a,b):cmd.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.command=='prepare':
        result=prepare(k.load(args.corpus),k.load(args.graph),args.root,args.model,args.cli_version)
        k.write_new(args.output,k.canonical(result)+b'\n');return 0
    plan=k.load(args.plan)
    k.require(plan.get('protocol')=='geek-work-addressed-support-3','invalid_input:protocol')
    validate_plan_indices(plan)
    version=subprocess.check_output([str(args.claude),'--version'],text=True,timeout=10).strip()
    result=run(plan,args.output,args.claude,version)
    return 2 if result['halted'] else 0


if __name__=='__main__':sys.exit(main())
