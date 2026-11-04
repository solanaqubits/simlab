#!/usr/bin/env python3
"""Preserve numeric revisions and bind selected document numbers; no scientific promotion."""
import argparse
from fractions import Fraction
from pathlib import Path

import geek_work_experiment as numeric
import geek_work_manuscript_claims as claims
import geek_work_manuscript as m
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops
import geek_work_manuscript_status as status
import knowledge

SCHEMA='geek-work-numeric-history-1'
MAX_TOTAL=64*1024*1024
MAX_FILE=16*1024*1024
MAX_FILES=128
FLAGS=dict(chronology_verified=False,reason_verified=False,units_verified=False,
           uncertainty_verified=False,semantic_support_verified=False,
           scientific_verification=False,independence_verified=False,
           live_document_modified=False,publication_authorized=False)


def validate(raw):
    spec=knowledge.strict_json(raw)
    claims.obj(spec,'schema before after manuscript revisions')
    m.require(spec['schema']==SCHEMA,'numeric history schema')
    paths=[]
    for key in ('before','after','manuscript'):
        ref=spec[key];claims.obj(ref,'path sha256');claims.path_name(ref['path']);claims.digest(ref['sha256'])
        paths.append(ref['path'].casefold())
    for i,path in enumerate(paths):
        for other in paths[i+1:]:m.require(path!=other and not path.startswith(other+'/') and not other.startswith(path+'/'),'overlapping archive paths')
    m.require(spec['before']['sha256']!=spec['after']['sha256'],'distinct numeric revisions required')
    ids=set();numbers=set()
    for row in claims.rows(spec['revisions'],32,1):
        claims.obj(row,'id numeric_claim reason manuscript_claim report_material value_span')
        for key in ('id','numeric_claim','manuscript_claim','report_material'):claims.ident(row[key])
        claims.text(row['reason'])
        m.require(row['id'] not in ids and row['numeric_claim'] not in numbers,'duplicate revision or numeric claim')
        ids.add(row['id']);numbers.add(row['numeric_claim'])
    return spec


def collect(raw,root,replay=False):
    spec=validate(raw);files={};total=0;folders={}
    for key,verifier in (('before',numeric.verify),('after',numeric.verify),('manuscript',claims.verify)):
        folder=status.folder(root,'inputs/'+key if replay else spec[key]['path'])
        verifier(folder,spec[key]['sha256']);folders[key]=folder
        meta=knowledge.strict_json(m.read(folder/'manifest.json'))
        if key!='manuscript':m.require(meta['kind']=='claims','numeric claim archive required')
        for name in sorted(set(meta['files'])|{'manifest.json'}):
            parts=claims.path_name(name).parts
            parent=folder if len(parts)==1 else status.folder(folder,'/'.join(parts[:-1]))
            blob=m.read(parent/parts[-1],MAX_FILE);total+=len(blob)
            m.require(total<=MAX_TOTAL and len(files)<MAX_FILES,'history snapshot limit')
            files['inputs/'+key+'/'+name]=blob
    def parsed(key,name):return knowledge.strict_json(files['inputs/'+key+'/'+name])
    old,new=parsed('before','spec.json'),parsed('after','spec.json')
    m.require(old['id']==new['id'],'numeric map identity changed')
    old_claims={r['id']:r for r in old['claims']};new_claims={r['id']:r for r in new['claims']}
    old_results={r['id']:r for r in parsed('before','report.json')['claims']}
    new_results={r['id']:r for r in parsed('after','report.json')['claims']}
    mapping=parsed('manuscript','map.json');doc_claims={r['id']:r for r in mapping['claims']}
    materials={r['id']:r for r in mapping['materials']}
    docs={r['id']:claims.utf8(files['inputs/manuscript/document-'+r['id']+'.txt']) for r in mapping['documents']}
    rows=[]
    for row in spec['revisions']:
        cid=row['numeric_claim'];mid=row['manuscript_claim'];material=row['report_material']
        m.require(cid in old_claims and cid in new_claims,'numeric claim missing from a revision')
        m.require(mid in doc_claims and material in materials,'unknown manuscript claim or material')
        document_claim=doc_claims[mid];statement=document_claim['statement'];span=row['value_span']
        claims.span(span,docs,'document')
        m.require(span['document']==statement['document'] and statement['start']<=span['start']<span['end']<=statement['end'],'numeric span outside selected statement')
        m.require(materials[material]['kind']=='measurement_report','measurement report material required')
        m.require(files['inputs/manuscript/material-'+material+'.txt']==files['inputs/after/report.json'],'manuscript material is not the pinned after report')
        m.require(any(e['citation']['material']==material for e in document_claim['evidence']),'selected statement must cite the after report')
        value=numeric.number(span['quote']);actual=new_results[cid]['actual']
        recomputed=Fraction(int(actual['numerator']),int(actual['denominator']))
        rows.append(dict(id=row['id'],numeric_claim=cid,reason_declared=row['reason'],
            before=dict(history_role='superseded_in_this_history',claim=old_claims[cid],result=old_results[cid]),
            after=dict(history_role='replacement_in_this_history',claim=new_claims[cid],result=new_results[cid]),
            changed_claim_fields=sorted(k for k in old_claims[cid] if old_claims[cid][k]!=new_claims[cid][k]),
            manuscript_claim=document_claim,report_material=materials[material],value_span=span,
            document_value=numeric.rational(value),
            document_matches_declared=value==numeric.number(new_claims[cid]['value']),
            document_matches_recomputed=value==recomputed))
    report=dict(schema=SCHEMA,status='review_required',numeric_map_id=old['id'],
        anchors={k:spec[k]['sha256'] for k in ('before','after','manuscript')},revisions=rows,
        source_inventory_changed=old['sources']!=new['sources'],
        unlinked_before_claims=sorted(set(old_claims)-{r['numeric_claim'] for r in rows}),
        unlinked_after_claims=sorted(set(new_claims)-{r['numeric_claim'] for r in rows}),
        history_order='caller_declared_not_a_timestamp',**FLAGS)
    encoded=m.encoded(report);m.require(len(encoded)<=m.MAX_ARTIFACT,'history report byte limit')
    files.update({'history.json':raw,'report.json':encoded})
    return files,report


def manifest(files):return m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()},**FLAGS))


def build(spec_path,anchor,root,output):
    spec_path,root,output=map(Path,(spec_path,root,output));claims.digest(anchor);ops.outside(output,root,spec_path)
    raw=m.read(spec_path);m.require(m.sha(raw)==anchor,'history spec anchor mismatch')
    files,report=collect(raw,root);meta=manifest(files);tree.write_tree(output,{**files,'manifest.json':meta})
    return dict(status=report['status'],manifest_sha256=m.sha(meta),**FLAGS)


def verify(bundle,anchor):
    bundle=Path(bundle);claims.digest(anchor);meta=m.read(bundle/'manifest.json')
    m.require(m.sha(meta)==anchor,'history manifest anchor mismatch')
    files,report=collect(m.read(bundle/'history.json'),bundle,True)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(meta==manifest(files),'history manifest reproduction mismatch')
    for name,blob in files.items():m.require(m.read(bundle/name,MAX_FILE)==blob,'history artifact reproduction mismatch')
    return dict(status=report['status'],integrity_reproduced=True,manifest_sha256=anchor,**FLAGS)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','verify'])
    p.add_argument('--spec',type=Path);p.add_argument('--root',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--bundle',type=Path);p.add_argument('--sha256',required=True);a=p.parse_args()
    try:
        if a.action=='build':
            m.require(a.bundle is None and all(v is not None for v in (a.spec,a.root,a.output)),'build requires spec/root/output')
            result=build(a.spec,a.sha256,a.root,a.output)
        else:
            m.require(a.bundle is not None and all(v is None for v in (a.spec,a.root,a.output)),'verify requires bundle/sha256')
            result=verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,UnicodeError) as error:
        print(m.encoded(dict(status='refused',reason=str(error))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
