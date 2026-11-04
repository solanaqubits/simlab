#!/usr/bin/env python3
"""Freeze bounded experiment plans and reproduce exact numeric claim maps offline."""
import argparse
import csv
from decimal import Decimal
from fractions import Fraction
import io
import json
from pathlib import Path
import re
import geek_work_manuscript_claims as k
import geek_work_manuscript as m
import geek_work_batch_hunks as tree

SCHEMA='geek-work-experiment-plan-1'
OUTCOMES=('recovered','inconsistent','excluded','insufficient_data')


def number(value):
    if type(value) is int:
        m.require(value.bit_length()<=4096,'numeric integer limit');return Fraction(value)
    m.require(type(value) in (str,Decimal),'exact decimal text or JSON number required')
    text=str(value);m.require(len(text)<=256 and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?',text),'bounded exact decimal')
    if 'e' in text.lower():m.require(abs(int(text.lower().split('e')[1]))<=256,'decimal exponent limit')
    return Fraction(text)


def rational(value):
    m.require(max(value.numerator.bit_length(),value.denominator.bit_length())<=4096,'rational arithmetic limit')
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def structured(value,depth=0):
    m.require(depth<=8,'parameter nesting limit')
    if type(value) is dict:
        m.require(len(value)<=64,'parameter object limit')
        for key,item in value.items():k.text(key);structured(item,depth+1)
    elif type(value) is list:
        m.require(len(value)<=512,'parameter array limit')
        for item in value:structured(item,depth+1)
    elif type(value) is str:k.text(value)
    elif type(value) is int:m.require(abs(value)<=10**12,'parameter integer limit')
    else:m.require(value is None or type(value) is bool,'parameters: floats forbidden, decimals as strings')


def plan_template(domain='general'):
    return dict(schema=SCHEMA,id='new-experiment',domain=domain,title='Draft experiment',hypothesis='Specify a falsifiable hypothesis',readiness='draft',
        sources=[],parameters={},holdout=dict(source_ids=[],exposure='unknown',note='Not established'),
        controls=[dict(kind=kind,description='Define before execution',expected='Specify expected behavior') for kind in ('positive','null','injection')],
        criteria={name:'Define before execution' for name in OUTCOMES},
        budget=dict(max_attempts=1,wall_time_seconds=60,memory_bytes=268435456,token_limit=None,cost_usd=None),
        seeds=[0],analysis_change_policy='Preserve failed attempts and post-hoc changes as separate plans; never overwrite the frozen baseline',non_claims=['A frozen hash does not establish time, blinding or scientific validity'])


def sources(rows):
    k.rows(rows,32);seen=set();paths=set()
    for row in rows:
        k.obj(row,'id path sha256 role');k.ident(row['id']);k.path_name(row['path']);k.digest(row['sha256'])
        m.require(row['role'] in ('data','code','reference','holdout','run_record'),'source role')
        m.require(row['id'] not in seen and row['path'] not in paths,'duplicate source id/path');seen.add(row['id']);paths.add(row['path'])
    return {row['id']:row for row in rows}


def validate_plan(spec,freezing=False):
    k.obj(spec,'schema id domain title hypothesis readiness sources parameters holdout controls criteria budget seeds analysis_change_policy non_claims')
    m.require(spec['schema']==SCHEMA,'experiment plan schema');k.ident(spec['id']);k.ident(spec['domain'])
    for key in ('title','hypothesis','analysis_change_policy'):k.text(spec[key])
    m.require(spec['readiness'] in ('draft','ready_for_protocol_review'),'plan readiness')
    inputs=sources(spec['sources']);structured(spec['parameters']);k.obj(spec['holdout'],'source_ids exposure note');holdout=spec['holdout']
    k.text(holdout['note']);m.require(holdout['exposure'] in ('not_accessed_declared','previously_inspected','unknown'),'holdout exposure declaration')
    k.rows(holdout['source_ids'],32);m.require(all(type(x) is str for x in holdout['source_ids']) and len(set(holdout['source_ids']))==len(holdout['source_ids']),'unique holdout IDs')
    m.require(set(holdout['source_ids'])<=set(inputs),'holdout source reference');m.require(set(holdout['source_ids'])=={i for i,row in inputs.items() if row['role']=='holdout'},'holdout role/ID coverage')
    kinds=[]
    for row in k.rows(spec['controls'],16,3):
        k.obj(row,'kind description expected');m.require(row['kind'] in ('positive','null','injection'),'control kind');kinds.append(row['kind']);k.text(row['description']);k.text(row['expected'])
    m.require(set(kinds)=={'positive','null','injection'},'control coverage');k.obj(spec['criteria'],' '.join(OUTCOMES))
    for value in spec['criteria'].values():k.text(value)
    budget=spec['budget'];k.obj(budget,'max_attempts wall_time_seconds memory_bytes token_limit cost_usd')
    for key in ('max_attempts','wall_time_seconds','memory_bytes'):m.require(type(budget[key]) is int and 1<=budget[key]<=10**12,'positive declared budget')
    m.require(budget['token_limit'] is None or type(budget['token_limit']) is int and 0<=budget['token_limit']<=10**12,'token limit or null')
    if budget['cost_usd'] is not None:m.require(type(budget['cost_usd']) is str and number(budget['cost_usd'])>=0,'decimal cost limit or null')
    m.require(all(type(x) is int and 0<=x<=2**32-1 for x in k.rows(spec['seeds'],32,1)),'bounded integer seeds')
    k.strings(spec['non_claims']);m.require(bool(spec['non_claims']),'explicit non-claims required')
    if freezing:m.require(spec['readiness']=='ready_for_protocol_review' and any(row['role']=='code' for row in inputs.values()),'ready plan with pinned code required')
    return spec


def claim_map(spec):
    k.obj(spec,'schema id sources claims');m.require(spec['schema']=='geek-work-numeric-claims-1','numeric map schema');k.ident(spec['id']);inputs=sources(spec['sources']);ids=set()
    for row in k.rows(spec['claims'],64,1):
        k.obj(row,'id statement value unit uncertainty operation operands');k.ident(row['id']);m.require(row['id'] not in ids,'duplicate claim ID');ids.add(row['id']);k.text(row['statement']);k.text(row['unit']);number(row['value'])
        m.require(type(row['value']) is str,'claim value must be exact text')
        if row['uncertainty'] is not None:k.text(row['uncertainty'])
        m.require(row['operation'] in ('identity','sum','product','difference','ratio'),'supported arithmetic operation')
        operands=k.rows(row['operands'],16,1)
        m.require(row['operation'] not in ('identity','difference','ratio') or len(operands)==(1 if row['operation']=='identity' else 2),'operation arity')
        for ref in operands:
            k.obj(ref,'source_id selector');m.require(type(ref['source_id']) is str and ref['source_id'] in inputs,'operand source reference')
            selector=ref['selector'];m.require(type(selector) is dict,'selector object')
            if set(selector)=={'json_pointer'}:
                ptr=selector['json_pointer'];m.require(type(ptr) is str and len(ptr)<=512 and (ptr=='' or ptr.startswith('/')) and not re.search(r'~(?![01])',ptr),'RFC6901 pointer')
            else:
                k.obj(selector,'csv_row column');m.require(type(selector['csv_row']) is int and 1<=selector['csv_row']<=10000,'CSV data row');k.text(selector['column'])
    return spec


def value_at(blob,selector):
    text=k.utf8(blob)
    if 'json_pointer' in selector:
        def constant(x):raise ValueError('nonfinite JSON number')
        data=json.loads(text,parse_float=Decimal,parse_constant=constant,object_pairs_hook=lambda pairs:unique(pairs))
        ptr=selector['json_pointer']
        if ptr:
            for part in ptr[1:].split('/'):
                key=part.replace('~1','/').replace('~0','~')
                if type(data) is list:
                    m.require(bool(re.fullmatch(r'0|[1-9][0-9]*',key)),'canonical array index');index=int(key);m.require(index<len(data),'array index');data=data[index]
                else:m.require(type(data) is dict and key in data,'JSON pointer target');data=data[key]
        return number(data)
    reader=csv.reader(io.StringIO(text,newline=''));header=next(reader,None)
    m.require(header is not None and len(set(header))==len(header) and selector['column'] in header,'unique CSV header/column')
    data=None
    for index,row in enumerate(reader,1):
        m.require(index<=10000 and len(row)==len(header),'bounded rectangular CSV')
        if index==selector['csv_row']:data=row[header.index(selector['column'])]
    m.require(data is not None,'CSV row missing');return number(data)


def unique(pairs):
    result={}
    for key,value in pairs:m.require(key not in result,'duplicate JSON key');result[key]=value
    return result


def numeric_report(spec,files):
    inputs={row['id']:files['sources/'+row['path']] for row in spec['sources']};rows=[]
    for claim in spec['claims']:
        values=[value_at(inputs[x['source_id']],x['selector']) for x in claim['operands']];op=claim['operation'];value=values[0]
        if op in ('sum','product'):
            for item in values[1:]:value=value+item if op=='sum' else value*item;rational(value)
        elif op=='difference':value-=values[1]
        elif op=='ratio':m.require(values[1]!=0,'zero denominator');value/=values[1]
        actual=rational(value);match=value==number(claim['value'])
        rows.append(dict(id=claim['id'],status=('number_present' if op=='identity' else 'recomputed_here') if match else 'value_mismatch',matches=match,expected=claim['value'],actual=actual,unit_declared=claim['unit'],uncertainty_declared=claim['uncertainty'],operation=op,operands=claim['operands'],operand_values=[rational(x) for x in values]))
    return dict(schema='geek-work-numeric-claims-report-1',status='numeric_map_consistent' if all(x['matches'] for x in rows) else 'numeric_map_mismatch',claims=rows,declared_run_record_source_ids=[x['id'] for x in spec['sources'] if x['role']=='run_record'],units_verified=False,uncertainty_verified=False,run_execution_verified=False,independence_verified=False,scientific_verification=False,publication_authorized=False,limits='Exact selected numeric values and bounded arithmetic only. Sources may themselves be wrong. Operations share this verifier, not an independent oracle. Unit labels, uncertainties and experiment execution are not verified. No source code, formulas or instructions are executed.')


def snapshot(root,spec):
    files={};total=0
    for row in spec['sources']:
        blob=k.read_source(root,row['path']);m.require(m.sha(blob)==row['sha256'],'source SHA mismatch');total+=len(blob);m.require(total<=k.MAX_TOTAL,'source total limit');files['sources/'+row['path']]=blob
    return files


def derived(kind,spec,files):
    if kind=='plan':
        validate_plan(spec,True)
        return dict(schema='geek-work-experiment-frozen-report-1',status='plan_frozen_review_required',plan_sha256=m.sha(files['spec.json']),input_count=len(spec['sources']),experiment_executed=False,budget_enforced=False,holdout_blinding_verified=False,chronology_verified=False,protocol_semantics_verified=False,scientific_verification=False,publication_authorized=False,limits='Byte-frozen declared plan and pinned text sources only. No execution, trusted timestamp or proof of preregistration/blinding. Criteria and budgets are declarations, not enforced rules. Revisions require a new artifact and separate history.')
    claim_map(spec);return numeric_report(spec,files)


def capture(kind,spec_path,anchor,root,output):
    # Existing disjoint-output helper rejects nested/overlapping source paths.
    import geek_work_file_operations as ops
    ops.outside(output,root,spec_path);m.require(not output.exists() and not output.is_symlink(),'new experiment archive required');k.digest(anchor)
    blob=m.read(spec_path);m.require(m.sha(blob)==anchor,'spec anchor mismatch');spec=m.load(blob)
    (validate_plan(spec,True) if kind=='plan' else claim_map(spec));files={'spec.json':blob,**snapshot(root,spec)};report=derived(kind,spec,files);files['report.json']=m.encoded(report);m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'report byte limit')
    manifest=m.encoded(dict(schema='geek-work-experiment-archive-1',kind=kind,spec_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}));tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=report['status'],manifest_sha256=m.sha(manifest))


def verify(bundle,anchor):
    k.digest(anchor);blob=m.read(bundle/'manifest.json');m.require(m.sha(blob)==anchor,'experiment archive anchor mismatch');manifest=m.load(blob);k.obj(manifest,'schema kind spec_sha256 files');m.require(manifest['schema']=='geek-work-experiment-archive-1' and manifest['kind'] in ('plan','claims'),'experiment archive schema')
    spec_blob=m.read(bundle/'spec.json');m.require(m.sha(spec_blob)==manifest['spec_sha256'],'spec binding');spec=m.load(spec_blob)
    (validate_plan(spec,True) if manifest['kind']=='plan' else claim_map(spec));files={'spec.json':spec_blob,**snapshot(bundle/'sources',spec)};report=derived(manifest['kind'],spec,files);files['report.json']=m.encoded(report);m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'report byte limit')
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'archive file hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'archive reproduction mismatch')
    return dict(status=report['status'],manifest_sha256=anchor,integrity_reproduced=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('plan-template');q.add_argument('--output',type=Path,required=True)
    for action in ('freeze','map'):
        q=sub.add_parser(action);q.add_argument('--spec',type=Path,required=True);q.add_argument('--sha256',required=True);q.add_argument('--root',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);args=parser.parse_args()
    if args.action=='plan-template':
        with args.output.open('xb') as f:f.write(m.encoded(plan_template()))
        result=dict(status='draft_plan_created')
    elif args.action=='verify':result=verify(args.bundle,args.sha256)
    else:result=capture('plan' if args.action=='freeze' else 'claims',args.spec,args.sha256,args.root,args.output)
    print(m.encoded(result).decode(),end='')
    if result['status']!='draft_plan_created':raise SystemExit(2 if result['status']!='numeric_map_mismatch' else 3)


if __name__=='__main__':main()
