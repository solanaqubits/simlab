#!/usr/bin/env python3
"""Bounded literal Typst label/reference inventory over an anchored preflight."""
import argparse
from collections import Counter
from pathlib import Path
import re
import geek_work_typst_preflight as pre

m=pre.m;k=pre.k;tree=pre.tree
CLEAN='no_literal_reference_findings_in_supported_subset'
MAX_OCCURRENCES=4096
NAME=r'[A-Za-z0-9_.:-]+'


def analyze(preflight,archive,anchor):
    labels=[];references=[];findings=[]
    def finding(code,file,line,**extra):
        m.require(len(findings)<pre.MAX_EVENTS,'reference finding limit')
        findings.append(dict(code=code,file=file,line=line,**extra))
    if preflight['findings']:
        finding('preflight_findings_require_review',None,None,count=len(preflight['findings']))
    for name in preflight['reachable_typst']:
        raw=archive['sources/'+name];text=m.source(raw);tokens,_=pre.lex(text)
        covered_until=-1
        for index,token in enumerate(tokens):
            start=token['start'];value=token['value'];line=token['line']
            if start<covered_until:continue
            if token['kind']=='string':
                if '@' in value or '<' in value:finding('quoted_reference_region_requires_review',name,line)
                continue
            if token['kind']=='id' and value in ('label','ref','cite') and index+1<len(tokens) and tokens[index+1]['value']=='(':
                finding('functional_reference_construct_requires_review',name,line,construct=value)
            if value=='$':finding('math_region_requires_review',name,line);continue
            if value not in ('<','@'):continue
            pattern=r'<('+NAME+r')>' if value=='<' else r'@('+NAME+r')'
            match=re.match(pattern,text[start:])
            if not match:
                finding('unsupported_literal_marker_requires_review',name,line,marker=value);continue
            end=start+match.end();key=match.group(1);covered_until=end
            if value=='@' and ((start and (text[start-1].isalnum() or text[start-1] in '_@')) or (end<len(text) and (text[end].isalnum() or text[end]=='_')) or key.endswith(('.',':'))):
                finding('ambiguous_reference_boundary_requires_review',name,line,key=key);continue
            row=dict(file=name,line=line,start=start,end=end,key=key,source_sha256=m.sha(raw))
            (labels if value=='<' else references).append(row)
            m.require(len(labels)+len(references)<=MAX_OCCURRENCES,'reference occurrence limit')
    module_counts=Counter(row['target'] for row in preflight['dependencies'] if row['command'] in ('include','import'))
    for target,count in sorted(module_counts.items()):
        if count>1:finding('repeated_module_dependency_requires_review',None,None,target=target,occurrences=count)
    counts=Counter(row['key'] for row in labels)
    for row in labels:
        if counts[row['key']]>1:finding('repeated_literal_label_candidate',row['file'],row['line'],key=row['key'],occurrences=counts[row['key']])
    bibliography=[row for row in preflight['dependencies'] if row['command']=='bibliography']
    for row in references:
        # Finding a spelling is not proof of element attachment or referenceability.
        row['literal_label_occurrences']=counts[row['key']]
        if not counts[row['key']]:
            finding('reference_not_in_literal_label_inventory',row['file'],row['line'],key=row['key'],bibliography_candidate=bool(bibliography))
    if bibliography:finding('bibliography_contents_require_review',None,None,dependencies=len(bibliography))
    return dict(schema='geek-work-typst-references-report-1',status='review_required' if findings else CLEAN,
        preflight_sha256=anchor,preflight_status=preflight['status'],reachable_typst=preflight['reachable_typst'],
        unreached_selected_typst=preflight['unreached_selected_typst'],labels=labels,references=references,bibliography_dependencies=bibliography,findings=findings,
        full_syntax_coverage=False,reference_semantics_checked=False,bibliography_contents_checked=False,compilation_performed=False,scientific_verification=False,publication_authorized=False,
        limits='Lexical ASCII label/reference candidates in selected reachable files, not Typst evaluation. Occurrences are not runtime definitions. Attachment, scope, numbering, referenceability, imports, bibliography contents and generated labels are not resolved. Repeated includes are scanned once. Offsets are Unicode code points into exact UTF-8-decoded source. Existing preflight/gate schemas are unchanged.')


def summary(report,anchor):
    return dict(status=report['status'],manifest_sha256=anchor,labels=len(report['labels']),references=len(report['references']),findings=len(report['findings']),reference_semantics_checked=False,compilation_performed=False)


def check(bundle,anchor,output):
    pre.ops.outside(output,bundle);m.require(not output.exists() and not output.is_symlink(),'new reference output required')
    report,archive=pre.verified(bundle,anchor);result=analyze(report,archive,anchor);encoded=m.encoded(result)
    m.require(len(encoded)<=m.MAX_ARTIFACT,'reference report limit')
    files={'report.json':encoded,**{'preflight/'+n:x for n,x in archive.items()}}
    manifest=m.encoded(dict(schema='geek-work-typst-references-manifest-1',preflight_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest});return summary(result,m.sha(manifest))


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'reference manifest anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema preflight_sha256 files');m.require(manifest['schema']=='geek-work-typst-references-manifest-1','reference manifest schema')
    report,archive=pre.verified(bundle/'preflight',manifest['preflight_sha256']);result=analyze(report,archive,manifest['preflight_sha256']);encoded=m.encoded(result)
    m.require(len(encoded)<=m.MAX_ARTIFACT,'reference report limit')
    files={'report.json':encoded,**{'preflight/'+n:x for n,x in archive.items()}}
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'reference manifest hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'reference report reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    result,_=verified(bundle,anchor);return summary(result,anchor)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('check','verify'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='check':q.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=check(args.bundle,args.sha256,args.output) if args.action=='check' else verify(args.bundle,args.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']=='review_required':raise SystemExit(2)


if __name__=='__main__':main()
