#!/usr/bin/env python3
"""Classify literal reference candidates against selected reachable BibTeX keys."""
import argparse
from collections import Counter
from pathlib import Path
import geek_work_typst_references as refs

pre=refs.pre;m=refs.m;k=refs.k;tree=refs.tree
CLEAN='no_bibliography_key_findings_in_supported_subset'
MAX_KEYS=4096


def analyze(parent,archive,anchor):
    preflight=m.load(archive['preflight/report.json']);keys=[];findings=[];bibliographies=[]
    def finding(code,**extra):
        m.require(len(findings)<pre.MAX_EVENTS,'bibliography finding limit');findings.append(dict(code=code,**extra))
    # These two parent findings describe precisely the previously unclassified layer.
    # Retain the parent's unchanged outcome; only this narrower key layer is derived.
    for row in parent['findings']:
        if row['code'] not in {'reference_not_in_literal_label_inventory','bibliography_contents_require_review'}:
            finding('parent_reference_finding_requires_review',finding=row)
    dependencies=parent['bibliography_dependencies'];active=sorted({row['target'] for row in dependencies})
    if len(dependencies)>1:finding('multiple_bibliography_dependencies_require_review',occurrences=len(dependencies))
    for name in active:
        selected=name in preflight['files'];row=dict(file=name,selected=selected,key_candidates=0,scan='not_scanned')
        bibliographies.append(row)
        if not selected:finding('bibliography_not_selected',file=name);continue
        raw=archive['preflight/sources/'+name];row['sha256']=m.sha(raw)
        if not name.endswith('.bib'):
            finding('unsupported_bibliography_format_requires_review',file=name);continue
        entries,issues=pre.tex.bib_keys(m.source(raw));row.update(scan='literal_bibtex_subset',key_candidates=len(entries))
        for entry in entries:
            m.require(len(keys)<MAX_KEYS,'bibliography key limit');keys.append(dict(file=name,line=entry['line'],key=entry['value'],source_sha256=m.sha(raw)))
        for issue in issues:finding('bibtex_scanner_requires_review',file=name,line=issue['line'],reason=issue['value'])
        if not entries:finding('no_bibtex_key_candidates_requires_review',file=name)
    counts=Counter(row['key'] for row in keys)
    for key,count in sorted(counts.items()):
        if count>1:finding('repeated_bibliography_key_candidate',key=key,occurrences=count)
    classifications=[]
    for row in parent['references']:
        label_count=row['literal_label_occurrences'];bib_count=counts[row['key']]
        if label_count and bib_count:kind='label_bibliography_collision'
        elif label_count:kind='literal_label_candidate'
        elif bib_count:kind='literal_bibliography_key_candidate'
        else:kind='unclassified_reference_candidate'
        classifications.append(dict(**row,bibliography_key_occurrences=bib_count,classification=kind))
        if kind in {'label_bibliography_collision','unclassified_reference_candidate'}:finding(kind,file=row['file'],line=row['line'],key=row['key'])
    return dict(schema='geek-work-typst-bibliography-report-1',status='review_required' if findings else CLEAN,
        reference_inventory_sha256=anchor,parent_reference_status=parent['status'],bibliographies=bibliographies,keys=keys,references=classifications,findings=findings,
        unscanned_selected_bibliographies=sorted(n for n in preflight['files'] if n.endswith(('.bib','.yaml','.yml')) and n not in active),
        parent_report_unchanged=True,full_bibtex_coverage=False,bibliography_contents_verified=False,reference_semantics_checked=False,compilation_performed=False,scientific_verification=False,publication_authorized=False,
        limits='Literal BibTeX header keys using the existing bounded scanner, from selected reachable bibliography dependencies only. Bodies consumed as balanced braces, not metadata validation. Names classify lexical candidates, not runtime reference resolution or citation correctness. Hayagriva/YAML, malformed/parenthesized entries and parent lexical issues need review. Parent inventory outcome is retained; no preflight/gate/status upgrade.')


def summary(report,anchor):
    return dict(status=report['status'],manifest_sha256=anchor,keys=len(report['keys']),references=len(report['references']),findings=len(report['findings']),parent_reference_status=report['parent_reference_status'],bibliography_contents_verified=False,reference_semantics_checked=False)


def check(bundle,anchor,output):
    pre.ops.outside(output,bundle);m.require(not output.exists() and not output.is_symlink(),'new bibliography output required')
    parent,archive=refs.verified(bundle,anchor);result=analyze(parent,archive,anchor);encoded=m.encoded(result);m.require(len(encoded)<=m.MAX_ARTIFACT,'bibliography report limit')
    files={'report.json':encoded,**{'references/'+n:data for n,data in archive.items()}}
    manifest=m.encoded(dict(schema='geek-work-typst-bibliography-manifest-1',reference_inventory_sha256=anchor,files={n:m.sha(data) for n,data in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest});return summary(result,m.sha(manifest))


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'bibliography manifest anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema reference_inventory_sha256 files');m.require(manifest['schema']=='geek-work-typst-bibliography-manifest-1','bibliography manifest schema')
    parent,archive=refs.verified(bundle/'references',manifest['reference_inventory_sha256']);result=analyze(parent,archive,manifest['reference_inventory_sha256']);encoded=m.encoded(result);m.require(len(encoded)<=m.MAX_ARTIFACT,'bibliography report limit')
    files={'report.json':encoded,**{'references/'+n:data for n,data in archive.items()}}
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(data) for n,data in files.items()},'bibliography manifest hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'bibliography reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    report,_=verified(bundle,anchor);return summary(report,anchor)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('check','verify'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
        if action=='check':q.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=check(args.bundle,args.sha256,args.output) if args.action=='check' else verify(args.bundle,args.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']=='review_required':raise SystemExit(2)


if __name__=='__main__':main()
