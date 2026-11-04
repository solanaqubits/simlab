#!/usr/bin/env python3
"""Review one manuscript-file proposal without modifying the live document."""
import argparse
import difflib
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_SOURCE=128*1024
MAX_ARTIFACT=2*1024*1024
FILES={'before.txt','after.txt','diff.txt','review.html'}


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def encoded(obj):return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()


def read(path,limit=MAX_ARTIFACT):
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError as error:raise ValueError('regular input required') from error
    with os.fdopen(fd,'rb') as f:
        require(stat.S_ISREG(os.fstat(f.fileno()).st_mode),'regular input required')
        raw=f.read(limit+1);require(len(raw)<=limit,'byte limit');return raw


def load(raw):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'duplicate JSON key');result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def source(raw):
    require(len(raw)<=MAX_SOURCE,'source byte limit')
    text=raw.decode('utf-8');require('\x00' not in text and len(text.split('\n'))<=4000,'text/line limit')
    return text


def document(name):
    require(type(name) is str and bool(name) and len(name)<=200 and '\\' not in name and '\n' not in name and '\r' not in name,'document name')
    p=PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==name,'relative document name required')
    require(p.suffix in ('.tex','.typ','.md','.bib'),'unsupported document extension')
    return p


def metadata(raw):
    return dict(sha256=sha(raw),bytes=len(raw),crlf=raw.count(b'\r\n'),
                bare_lf=raw.count(b'\n')-raw.count(b'\r\n'),
                bare_cr=raw.count(b'\r')-raw.count(b'\r\n'),final_lf=raw.endswith(b'\n'))


def artifacts(before,after,name,author,reason):
    left,right=source(before),source(after);document(name)
    for value in (author,reason):require(type(value) is str and bool(value.strip()) and len(value)<=4000,'author/reason text required')
    details=encoded(dict(before=metadata(before),after=metadata(after))).decode()
    diff='\n'.join(difflib.unified_diff(left.splitlines(),right.splitlines(),fromfile='before/'+name,tofile='after/'+name,lineterm=''))+'\n'
    # Line-ending-only changes remain explicit in metadata, even when text diff is empty.
    report='''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Manuscript proposal</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:1em}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1em}h2{margin-top:2em}</style>
<h1>Manuscript proposal</h1><p>Text review only. No compilation, factual validation or live-file write.</p>'''
    for title,value in [('Document',name),('Reported author/model',author),('Reason',reason),('Byte identity and line endings',details),('Text diff (line endings shown above)',diff),('Before',left),('After',right)]:
        report+='<h2>'+html.escape(title)+'</h2><pre>'+html.escape(value)+'</pre>'
    report+='</html>\n'
    require(len(report.encode())<=MAX_ARTIFACT,'preview byte limit')
    return {'before.txt':before,'after.txt':after,'diff.txt':diff.encode(),'review.html':report.encode()}


def propose(base,candidate,name,author,reason,output):
    before,after=read(base,MAX_SOURCE),read(candidate,MAX_SOURCE)
    require(before!=after,'no change')
    data=artifacts(before,after,name,author,reason)
    manifest=dict(schema='geek-work-manuscript-proposal-1',document=name,author=author,reason=reason,
                  files={n:sha(b) for n,b in data.items()},scientific_verification=False)
    raw=encoded(manifest)
    output.mkdir(parents=True,exist_ok=False)
    for n,b in data.items():
        with (output/n).open('xb') as f:f.write(b)
    with (output/'manifest.json').open('xb') as f:f.write(raw)
    return dict(status='proposal_ready',manifest_sha256=sha(raw),live_document_modified=False)


def verified(bundle,anchor):
    require(type(anchor) is str and bool(re.fullmatch('[0-9a-f]{64}',anchor)),'full manifest SHA required')
    require(bundle.is_dir() and not bundle.is_symlink(),'regular bundle directory')
    require({p.name for p in bundle.iterdir()}==FILES|{'manifest.json'},'bundle file set')
    raw=read(bundle/'manifest.json');require(sha(raw)==anchor,'manifest anchor mismatch');m=load(raw)
    require(type(m) is dict and set(m)=={'schema','document','author','reason','files','scientific_verification'},'manifest fields')
    require(m['schema']=='geek-work-manuscript-proposal-1' and m['scientific_verification'] is False,'manifest scope')
    require(type(m['files']) is dict and set(m['files'])==FILES,'artifact file set')
    data={n:read(bundle/n) for n in FILES}
    require(all(sha(b)==m['files'][n] for n,b in data.items()),'artifact hash mismatch')
    require(data['before.txt']!=data['after.txt'],'no change')
    require(data==artifacts(data['before.txt'],data['after.txt'],m['document'],m['author'],m['reason']),'preview mismatch')
    return m,data


def decide(bundle,anchor,current,decision,reviewer,output):
    require(decision in ('accept','reject'),'decision must be accept or reject')
    require(type(reviewer) is str and bool(reviewer.strip()) and len(reviewer)<=4000,'reviewer required')
    m,data=verified(bundle,anchor)
    observed=read(current,MAX_SOURCE)
    require(observed==data['before.txt'],'STALE_BASE_REJECTED')
    chosen=data['after.txt'] if decision=='accept' else data['before.txt']
    name='result'+document(m['document']).suffix
    receipt=dict(schema='geek-work-manuscript-decision-1',decision=decision,reviewer=reviewer,
                 proposal_sha256=anchor,document=m['document'],observed_base_sha256=sha(observed),
                 result_file=name,result_sha256=sha(chosen),live_document_modified=False,
                 scientific_verification=False,reviewer_identity_verified=False,
                 limits='Point-in-time baseline check; staged output only, not an atomic live-file update.')
    output.mkdir(parents=True,exist_ok=False)
    with (output/name).open('xb') as f:f.write(chosen)
    with (output/'receipt.json').open('xb') as f:f.write(encoded(receipt))
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('propose');q.add_argument('--base',type=Path,required=True);q.add_argument('--candidate',type=Path,required=True)
    q.add_argument('--document',required=True);q.add_argument('--author',required=True);q.add_argument('--reason',required=True);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('decide');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);q.add_argument('--current',type=Path,required=True)
    q.add_argument('--decision',choices=['accept','reject'],required=True);q.add_argument('--reviewer',required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=propose(a.base,a.candidate,a.document,a.author,a.reason,a.output) if a.command=='propose' else decide(a.bundle,a.sha256,a.current,a.decision,a.reviewer,a.output)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
