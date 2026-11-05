#!/usr/bin/env python3
"""Explicit per-hunk manuscript decisions with byte-preserving staged results."""
import argparse
import difflib
import html
import json
from pathlib import Path
import geek_work_manuscript as m
import geek_work_manuscript_batch as b
import geek_work_manuscript_claims as k

MAX_HUNKS=128
MAX_BUNDLE=8*1024*1024
FILES=m.FILES|{'hunks.json','hunk-review.html','decisions.template.json'}


def lines(raw):
    # Only LF delimits lines. Preserve CRLF, bare CR, Unicode and missing final LF.
    parts=raw.split(b'\n')
    return [p+b'\n' for p in parts[:-1]]+([parts[-1]] if parts[-1] else [])


def hunks(before,after):
    m.source(before);m.source(after);m.require(before!=after,'no change')
    left,right=lines(before),lines(after)
    def offsets(items):
        result=[0]
        for item in items:result.append(result[-1]+len(item))
        return result
    lo,ro=offsets(left),offsets(right);rows=[]
    for tag,i,j,x,y in difflib.SequenceMatcher(None,left,right,autojunk=False).get_opcodes():
        if tag=='equal':continue
        rows.append(dict(id=f'h{len(rows)+1:03d}',kind=tag,before_start=lo[i],before_end=lo[j],
                         after_start=ro[x],after_end=ro[y],before_text=before[lo[i]:lo[j]].decode('utf-8'),
                         after_text=after[ro[x]:ro[y]].decode('utf-8')))
    m.require(1<=len(rows)<=MAX_HUNKS,'hunk count limit')
    return rows


def assemble(before,rows,decisions):
    m.require(len(rows)==len(decisions),'decision count mismatch')
    result=[];cursor=0
    for row,decision in zip(rows,decisions):
        start,end=row['before_start'],row['before_end']
        result.extend((before[cursor:start],row['after_text'].encode('utf-8') if decision['decision']=='accept' else before[start:end]));cursor=end
    result.append(before[cursor:]);raw=b''.join(result);m.source(raw);return raw


def artifacts(before,after,document,author,reason):
    data=m.artifacts(before,after,document,author,reason);rows=hunks(before,after)
    m.require(assemble(before,rows,[{'decision':'accept'} for _ in rows])==after,'candidate reconstruction')
    data['hunks.json']=m.encoded(dict(schema='geek-work-manuscript-hunks-1',algorithm='lf-sequence-matcher-v1',hunks=rows))
    data['decisions.template.json']=m.encoded(dict(schema='geek-work-hunk-selection-1',proposal_sha256=None,reviewer=None,
        decisions=[dict(hunk_id=r['id'],decision=None,reason=None) for r in rows]))
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Manuscript hunk review</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:1em}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1em}</style>
<h1>Review every hunk</h1><p>Each hunk needs an explicit accept/reject and reason. IDs belong only to this anchored proposal. Byte offsets are zero-based and end-exclusive. JSON-escaped text shows line endings. These are textual regions, not independent mathematical claims.</p><p><a href="review.html">Full baseline and candidate</a></p>'''
    for row in rows:
        page+='<h2>'+row['id']+' — '+row['kind']+'</h2><pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre>'
    data['hunk-review.html']=(page+'</html>\n').encode()
    m.require(all(len(raw)<=m.MAX_ARTIFACT for raw in data.values()) and sum(map(len,data.values()))<=MAX_BUNDLE,'proposal byte limit')
    return data,rows


def write_files(output,data):
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in data.items():
        with (output/name).open('xb') as f:f.write(raw)


def propose(base,candidate,document,author,reason,output):
    data,rows=artifacts(m.read(base,m.MAX_SOURCE),m.read(candidate,m.MAX_SOURCE),document,author,reason)
    manifest=m.encoded(dict(schema='geek-work-hunk-proposal-1',document=document,author=author,reason=reason,
        files={n:m.sha(raw) for n,raw in data.items()},scientific_verification=False))
    write_files(output,{**data,'manifest.json':manifest})
    return dict(status='hunk_proposal_ready',manifest_sha256=m.sha(manifest),hunks=len(rows),live_document_modified=False)


def verified(bundle,anchor):
    k.digest(anchor);b.directory(bundle,FILES|{'manifest.json'})
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'manifest anchor mismatch')
    spec=m.load(raw);k.obj(spec,'schema document author reason files scientific_verification')
    m.require(spec['schema']=='geek-work-hunk-proposal-1' and spec['scientific_verification'] is False,'proposal scope')
    m.require(type(spec['files']) is dict and set(spec['files'])==FILES,'proposal file set')
    data={n:m.read(bundle/n) for n in FILES}
    m.require(sum(map(len,data.values()))<=MAX_BUNDLE,'proposal byte limit')
    m.require(all(m.sha(raw)==spec['files'][n] for n,raw in data.items()),'artifact hash mismatch')
    expected,rows=artifacts(data['before.txt'],data['after.txt'],spec['document'],spec['author'],spec['reason'])
    m.require(data==expected,'hunk/preview reproduction mismatch')
    return spec,data,rows,raw


def selection(raw,anchor,rows):
    spec=m.load(raw);k.obj(spec,'schema proposal_sha256 reviewer decisions')
    m.require(spec['schema']=='geek-work-hunk-selection-1' and spec['proposal_sha256']==anchor,'selection/proposal mismatch');k.text(spec['reviewer'])
    choices={}
    for row in k.rows(spec['decisions'],MAX_HUNKS,1):
        k.obj(row,'hunk_id decision reason');k.text(row['hunk_id']);k.text(row['reason'])
        m.require(type(row['decision']) is str and row['decision'] in {'accept','reject'},'explicit accept/reject required')
        m.require(row['hunk_id'] not in choices,'duplicate hunk decision');choices[row['hunk_id']]=row
    m.require(set(choices)=={row['id'] for row in rows},'every hunk requires exactly one decision')
    return spec,[choices[row['id']] for row in rows]


def result_receipt(spec,data,rows,anchor,selection_raw):
    selected,choices=selection(selection_raw,anchor,rows);result=assemble(data['before.txt'],rows,choices)
    name='result'+m.document(spec['document']).suffix
    receipt=dict(schema='geek-work-hunk-decision-1',document=spec['document'],proposal_sha256=anchor,
        selection_sha256=m.sha(selection_raw),reviewer=selected['reviewer'],decisions=choices,
        accepted=sum(r['decision']=='accept' for r in choices),rejected=sum(r['decision']=='reject' for r in choices),
        observed_base_sha256=m.sha(data['before.txt']),result_file=name,result_sha256=m.sha(result),
        live_document_modified=False,scientific_verification=False,reference_consistency_checked=False,
        compilation_checked=False,reviewer_identity_verified=False,
        limits='Single-file staged text; point-in-time baseline comparison only. Mixed choices may break dependencies; review/preflight/compile the assembled result before separate application.')
    return name,result,receipt


def decide(bundle,anchor,current,decisions,decisions_sha256,output):
    spec,data,rows,proposal_raw=verified(bundle,anchor);k.digest(decisions_sha256)
    raw=m.read(decisions);m.require(m.sha(raw)==decisions_sha256,'selection SHA mismatch')
    name,result,receipt=result_receipt(spec,data,rows,anchor,raw)
    m.require(m.read(current,m.MAX_SOURCE)==data['before.txt'],'STALE_BASE_REJECTED')
    payload={'decisions.json':raw,name:result,'receipt.json':m.encoded(receipt)}
    manifest=m.encoded(dict(schema='geek-work-hunk-decision-bundle-1',proposal_sha256=anchor,files={n:m.sha(x) for n,x in payload.items()}))
    write_files(output,payload)
    write_files(output/'proposal',{**data,'manifest.json':proposal_raw})
    with (output/'manifest.json').open('xb') as f:f.write(manifest)
    return dict(status='hunk_decision_staged',manifest_sha256=m.sha(manifest),**receipt)


def verify_decision(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular decision directory')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'decision anchor mismatch')
    manifest=m.load(raw);k.obj(manifest,'schema proposal_sha256 files')
    m.require(manifest['schema']=='geek-work-hunk-decision-bundle-1','decision schema')
    spec,data,rows,_=verified(bundle/'proposal',manifest['proposal_sha256'])
    name='result'+m.document(spec['document']).suffix;expected={'decisions.json','receipt.json',name}
    m.require(type(manifest['files']) is dict and set(manifest['files'])==expected,'decision file set')
    b.directory(bundle,expected|{'proposal','manifest.json'});payload={n:m.read(bundle/n) for n in expected}
    m.require(all(m.sha(raw)==manifest['files'][n] for n,raw in payload.items()),'decision artifact hash mismatch')
    _,result,receipt=result_receipt(spec,data,rows,manifest['proposal_sha256'],payload['decisions.json'])
    m.require(payload[name]==result and payload['receipt.json']==m.encoded(receipt),'decision reproduction mismatch')
    return dict(status='hunk_decision_consistent',manifest_sha256=anchor,result_sha256=m.sha(result),
        accepted=receipt['accepted'],rejected=receipt['rejected'],live_document_checked=False,
        historical_baseline_check_verified=False,reviewer_identity_verified=False,scientific_verification=False,
        limits='Anchored byte and decision reproduction only; not authorization, semantic correctness or independent evidence of the historical current-file observation.')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('propose')
    for n in ('base','candidate','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('document','author','reason'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('decide')
    for n in ('bundle','current','decisions','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','decisions-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify-decision');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    if a.action=='propose':r=propose(a.base,a.candidate,a.document,a.author,a.reason,a.output)
    elif a.action=='decide':r=decide(a.bundle,a.sha256,a.current,a.decisions,a.decisions_sha256,a.output)
    else:r=verify_decision(a.bundle,a.sha256)
    print(m.encoded(r).decode(),end='')


if __name__=='__main__':main()
