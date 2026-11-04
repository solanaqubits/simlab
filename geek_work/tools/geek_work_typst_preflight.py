#!/usr/bin/env python3
"""Bounded literal Typst dependency lint; no Typst evaluation or package resolution."""
import argparse
from bisect import bisect_right
from pathlib import Path, PurePosixPath
import re
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_manuscript_preflight as tex
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops
import geek_work_manuscript_compile as compiler

SUFFIXES={'.typ','.bib','.yaml','.yml','.png','.jpg','.jpeg','.svg','.gif','.pdf'}
MAX_FILES=32
MAX_TOTAL=16*1024*1024
MAX_TOKENS=16384
MAX_EVENTS=4096
COMMANDS={'include','import','image','bibliography'}


def config(value):
    k.obj(value,'schema entry files');m.require(value['schema']=='geek-work-typst-preflight-selection-1','selection schema')
    names=value['files'];m.require(type(names) is list and 1<=len(names)<=MAX_FILES,'selection size')
    for name in names:k.path_name(name);m.require(PurePosixPath(name).suffix in SUFFIXES,'unsupported selected suffix')
    m.require(len({n.casefold() for n in names})==len(names),'duplicate/case-colliding paths')
    for a in names:
        for b in names:m.require(a==b or not b.casefold().startswith(a.casefold()+'/'),'path collision')
    m.require(value['entry'] in names and value['entry'].endswith('.typ'),'selected Typst entry required');return value


def lex(text):
    tokens=[];issues=[];breaks=[i for i,c in enumerate(text) if c=='\n'];i=0
    def issue(code,start):
        m.require(len(issues)<MAX_EVENTS,'lexical finding limit');issues.append(dict(code=code,line=bisect_right(breaks,start)+1))
    while i<len(text):
        start=i
        if text[i].isspace():i+=1;continue
        if text[i]=='\\':i+=min(2,len(text)-i);continue
        if text.startswith('//',i):
            end=text.find('\n',i);i=len(text) if end<0 else end;continue
        if text.startswith('/*',i):
            i+=2;depth=1
            while i<len(text) and depth:
                if text.startswith('/*',i):depth+=1;m.require(depth<=64,'comment nesting limit');i+=2
                elif text.startswith('*/',i):depth-=1;i+=2
                else:i+=1
            if depth:issue('unterminated_comment',start)
            continue
        if text[i]=='`':
            width=1
            while i+width<len(text) and text[i+width]=='`':width+=1
            end=text.find('`'*width,i+width);i=len(text) if end<0 else end+width
            issue('raw_region_requires_review',start);continue
        if text.startswith(('https://','http://'),i):
            while i<len(text) and not text[i].isspace():i+=1
            issue('url_region_requires_review',start);continue
        if text[i]=='"':
            i+=1;escaped=False
            while i<len(text):
                if text[i]=='\\':escaped=True;i+=min(2,len(text)-i)
                elif text[i]=='"':i+=1;break
                else:i+=1
            else:issue('unterminated_string',start)
            kind='string';value=text[start+1:i-1] if text[i-1]=='"' and i>start+1 else text[start+1:i]
        elif text[i].isalpha() or text[i]=='_':
            i+=1
            while i<len(text) and (text[i].isalnum() or text[i] in '_-'):i+=1
            kind='id';value=text[start:i];escaped=False
        else:i+=1;kind='punct';value=text[start:i];escaped=False
        m.require(len(tokens)<MAX_TOKENS,'token limit');tokens.append(dict(kind=kind,value=value,start=start,end=i,line=bisect_right(breaks,start)+1,escaped=escaped))
    return tokens,issues


def target(source,value):
    m.require(value and not value.startswith('@') and '://' not in value,'external or empty path')
    parts=[] if value.startswith('/') else list(PurePosixPath(source).parent.parts)
    for part in value.split('/')[1:] if value.startswith('/') else value.split('/'):
        if part=='.':continue
        if part=='..':m.require(bool(parts),'path escapes root');parts.pop()
        else:m.require(bool(part),'empty path segment');parts.append(part)
    name='/'.join(parts);k.path_name(name);return name


def extract(name,raw):
    text=m.source(raw);tokens,findings=lex(text);edges=[];consumed=set()
    def finding(code,tok,command=None):
        m.require(len(findings)<MAX_EVENTS,'finding limit');findings.append(dict(code=code,line=tok['line'],command=command))
    for i,tok in enumerate(tokens):
        if tok['value']=='#':
            if i+1==len(tokens) or tokens[i+1]['kind']!='id' or tokens[i+1]['value'] not in COMMANDS:finding('unanalysed_expression',tok)
        if tok['kind']!='id' or tok['value'] not in COMMANDS:continue
        command=tok['value'];j=i+1
        prefixed=i>0 and tokens[i-1]['value']=='#' and tokens[i-1]['end']==tok['start']
        if not prefixed:
            if text[max(0,tok['start']-2):tok['start']]=='\\#':continue
            if j>=len(tokens) or tokens[j]['value'] not in ('(',) and tokens[j]['kind']!='string':continue
            finding('bare_code_candidate_requires_review',tok,command)
        if command in {'image','bibliography'}:
            if j>=len(tokens) or tokens[j]['value']!='(':finding('dynamic_dependency_requires_review',tok,command);continue
            j+=1
        if j>=len(tokens) or tokens[j]['kind']!='string':finding('dynamic_dependency_requires_review',tok,command);continue
        arg=tokens[j];consumed.add(j)
        if arg['escaped']:finding('escaped_path_requires_review',arg,command);continue
        following=tokens[j+1] if j+1<len(tokens) else None
        if command in {'image','bibliography'}:
            if following is None or following['value'] not in (',',')'):finding('dynamic_dependency_requires_review',tok,command);continue
            if following['value']==',':finding('additional_arguments_require_review',tok,command)
        elif following and following['value'] in ('+','-','*','/','.','?','=','&','|','('):
            finding('dynamic_dependency_requires_review',tok,command);continue
        try:resolved=target(name,arg['value'])
        except ValueError:finding('unsupported_dependency_path',arg,command);continue
        if command in {'include','import'} and not resolved.endswith('.typ'):finding('unsupported_module_suffix',arg,command);continue
        m.require(len(edges)<MAX_EVENTS,'dependency limit');edges.append(dict(file=name,line=tok['line'],command=command,literal=arg['value'],target=resolved))
    for i,tok in enumerate(tokens):
        if tok['kind']=='string' and i not in consumed and '#' in tok['value']:finding('unanalysed_quoted_region',tok)
    return edges,[dict(file=name,**x) for x in findings]


def analyze(spec,blobs):
    spec=config(spec);m.require(set(blobs)==set(spec['files']),'selected byte set');m.require(sum(map(len,blobs.values()))<=MAX_TOTAL,'selected total limit')
    for name,raw in blobs.items():
        m.require(len(raw)<=tex.MAX_FILE,'file byte limit')
        if name.endswith(('.typ','.bib')):m.source(raw)
    edges=[];findings=[];done=set();active=set()
    def add(items):
        findings.extend(items);m.require(len(findings)<=MAX_EVENTS,'total finding limit')
    def visit(name):
        active.add(name);local,issues=extract(name,blobs[name]);add(issues)
        for edge in local:
            edge=dict(**edge,selected=edge['target'] in blobs);edges.append(edge);m.require(len(edges)<=MAX_EVENTS,'total dependency limit')
            dest=edge['target']
            if not edge['selected']:add([dict(code='dependency_not_selected',**edge)])
            elif edge['command'] in {'include','import'}:
                if dest in active:add([dict(code='dependency_cycle',**edge)])
                elif dest not in done:visit(dest)
        active.remove(name);done.add(name)
    visit(spec['entry'])
    return dict(schema='geek-work-typst-preflight-report-1',status='review_required' if findings else 'no_dependency_findings_in_supported_subset',selection=spec,
        files={n:dict(sha256=m.sha(x),bytes=len(x)) for n,x in sorted(blobs.items())},reachable_typst=sorted(done),
        unreached_selected_typst=sorted(n for n in blobs if n.endswith('.typ') and n not in done),dependencies=edges,findings=findings,
        full_syntax_coverage=False,reference_semantics_checked=False,bibliography_contents_checked=False,asset_contents_decoded=False,compilation_performed=False,scientific_verification=False,
        limits='Literal dependency over-approximation in selected reachable Typst files, with file-relative/root-relative paths. No Typst evaluation, package resolution, label/citation validation, asset decoding or compiler claim. Dynamic/bare/unknown code and raw regions require review; not a complete mode-aware parser.')


def compile_request(spec,blobs):
    value=dict(schema='geek-work-manuscript-compile-request-1',entry=spec['entry'],files=[dict(path=n,sha256=m.sha(x)) for n,x in sorted(blobs.items())])
    compiler.validate_request(value,'geek-work-manuscript-compile-request-1','.typ');return m.encoded(value)


def read_selected(root,name):
    blob=ops.observe(root,name,'binary');m.require(blob is not None,'missing selected file: '+name)
    if name.endswith(('.typ','.bib')):m.source(blob)
    return blob


def check(root,selection,selection_anchor,output):
    ops.outside(output,root,selection);k.digest(selection_anchor);raw=m.read(selection);m.require(m.sha(raw)==selection_anchor,'selection SHA mismatch');spec=config(m.load(raw));blobs={};total=0
    for n in spec['files']:
        blob=read_selected(root,n);total+=len(blob);m.require(total<=MAX_TOTAL,'selected total limit');blobs[n]=blob
    report=analyze(spec,blobs);encoded=m.encoded(report);m.require(len(encoded)<=m.MAX_ARTIFACT,'report limit')
    files={'selection.json':raw,'report.json':encoded,'request.json':compile_request(spec,blobs),**{'sources/'+n:x for n,x in blobs.items()}}
    manifest=m.encoded(dict(schema='geek-work-typst-preflight-manifest-1',files={n:m.sha(x) for n,x in files.items()}));tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=report['status'],manifest_sha256=m.sha(manifest),findings=len(report['findings']),compile_request_sha256=m.sha(files['request.json']),compilation_performed=False)


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'manifest anchor mismatch');spec=m.load(raw);k.obj(spec,'schema files');m.require(spec['schema']=='geek-work-typst-preflight-manifest-1','manifest schema')
    selected=m.read(bundle/'selection.json');selection=config(m.load(selected));blobs={};total=0
    for n in selection['files']:
        blob=read_selected(bundle/'sources',n);total+=len(blob);m.require(total<=MAX_TOTAL,'selected total limit');blobs[n]=blob
    report=analyze(selection,blobs);m.require(len(m.encoded(report))<=m.MAX_ARTIFACT,'report limit')
    files={'selection.json':selected,'report.json':m.encoded(report),'request.json':compile_request(selection,blobs),**{'sources/'+n:x for n,x in blobs.items()}}
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(spec['files']=={n:m.sha(x) for n,x in files.items()},'preflight hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'preflight reproduction mismatch')
    return report,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    report,files=verified(bundle,anchor)
    return dict(status=report['status'],manifest_sha256=anchor,findings=len(report['findings']),compile_request_sha256=m.sha(files['request.json']),reproduced=True,compilation_performed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True);q=sub.add_parser('check')
    for n in ('root','selection','output'):q.add_argument('--'+n,type=Path,required=True)
    q.add_argument('--selection-sha256',required=True);q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    result=check(a.root,a.selection,a.selection_sha256,a.output) if a.action=='check' else verify(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']=='review_required':raise SystemExit(2)


if __name__=='__main__':main()
