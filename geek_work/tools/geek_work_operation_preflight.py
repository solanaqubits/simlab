#!/usr/bin/env python3
"""Recheck a file-operation baseline and lint its selected final LaTeX projection."""
import argparse
from pathlib import Path, PurePosixPath
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_manuscript_preflight as p
import geek_work_file_operations as ops
import geek_work_batch_hunks as tree

MAX_BASELINE=p.MAX_TOTAL


def selection(raw):
    spec=m.load(raw);k.obj(spec,'schema entry files')
    m.require(spec['schema']=='geek-work-operation-preflight-selection-1','selection schema')
    return p.config(dict(schema='geek-work-manuscript-preflight-selection-1',entry=spec['entry'],files=spec['files']))


def requirements(spec,receipt):
    writes=set(receipt['writes']);removed={r['path'] for r in receipt['removals']}
    m.require(not removed.intersection(spec['files']),'removed paths cannot be selected as final files')
    supported={name for name in writes if PurePosixPath(name).suffix in p.SUFFIXES}
    m.require(supported<=set(spec['files']),'all supported staged files must be selected')
    expected={};kinds={}
    for record in receipt['operations']:
        for name,digest in record['baseline'].items():
            expected[name]=digest;kinds[name]=record['operation']['kind']
    for name in spec['files']:
        if name not in writes and name not in expected:
            expected[name]='*';kinds[name]='text' if PurePosixPath(name).suffix in {'.tex','.bib'} else 'binary'
    return expected,kinds


def analyze(raw,decision_anchor,payload,receipt,baseline):
    spec=selection(raw);expected,_=requirements(spec,receipt)
    m.require(set(baseline)==set(expected),'baseline observation set')
    total=0
    for name,digest in expected.items():
        blob=baseline[name]
        if blob is not None:total+=len(blob);m.require(len(blob)<=ops.MAX_FILE and total<=MAX_BASELINE,'baseline byte limit')
        m.require((blob is None if digest is None else blob is not None and (digest=='*' or m.sha(blob)==digest)),'STALE_BASE_REJECTED: '+name)
    final={name:payload['result/'+name] if name in receipt['writes'] else baseline[name] for name in spec['files']}
    lint=p.analyze(spec,final);removed={r['path'] for r in receipt['removals']};renames={}
    for record in receipt['operations']:
        op=record['operation']
        if op['op']=='rename' and record['decision']['decision']=='accept':renames[op['source']]=op['target']
    old_links=[dict(**edge,rename_target=renames.get(edge['target'])) for edge in lint['dependencies'] if edge['target'] in removed]
    unsupported=sorted(name for name in expected if PurePosixPath(name).suffix not in p.SUFFIXES)
    # A create destination is in baseline observations too, so all operation paths are covered.
    status='review_required' if lint['findings'] or unsupported or old_links else 'no_findings_in_supported_subset'
    report=dict(schema='geek-work-operation-preflight-1',status=status,decision_sha256=decision_anchor,selection_sha256=m.sha(raw),
        baseline={name:None if blob is None else dict(sha256=m.sha(blob),bytes=len(blob)) for name,blob in sorted(baseline.items())},
        additional_selected_baseline_paths=sorted(n for n,d in expected.items() if d=='*'),
        removed_paths=sorted(removed),references_to_removed_paths=old_links,unanalysed_operation_paths=unsupported,preflight=lint,
        live_project_modified=False,compilation_verified=False,scientific_verification=False,full_syntax_coverage=False,binary_content_validated=False,
        limits='Selected final projection of an anchored decision plus captured baseline files. Literal root-relative LaTeX/BibTeX lint only; no live application, automatic reference rewriting, compiler, asset decoding or independent historical filesystem attestation. Observations are per-file, not an atomic project snapshot.')
    return report,final


def check(decision,decision_anchor,root,selection_path,selection_sha256,output):
    ops.outside(output,decision,root);payload,receipt,archive=ops.verified_decision(decision,decision_anchor)
    k.digest(selection_sha256);raw=m.read(selection_path);m.require(m.sha(raw)==selection_sha256,'selection SHA mismatch')
    spec=selection(raw);expected,kinds=requirements(spec,receipt);baseline={};total=0
    for name,digest in expected.items():
        blob=ops.observe(root,name,kinds[name]);baseline[name]=blob
        if blob is not None:total+=len(blob);m.require(total<=MAX_BASELINE,'baseline byte limit')
        m.require((blob is None if digest is None else blob is not None and (digest=='*' or m.sha(blob)==digest)),'STALE_BASE_REJECTED: '+name)
    report,final=analyze(raw,decision_anchor,payload,receipt,baseline);report_raw=m.encoded(report);m.require(len(report_raw)<=p.MAX_TOTAL,'report byte limit')
    files={'selection.json':raw,'report.json':report_raw,**{'baseline/'+n:x for n,x in baseline.items() if x is not None},**{'sources/'+n:x for n,x in final.items()}}
    manifest=m.encoded(dict(schema='geek-work-operation-preflight-bundle-1',decision_sha256=decision_anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,**{'decision/'+n:x for n,x in archive.items()},'manifest.json':manifest})
    return summary(report,m.sha(manifest),False)


def summary(report,anchor,reproduced):
    return dict(status=report['status'],manifest_sha256=anchor,reproduced=reproduced,
        findings=len(report['preflight']['findings']),references_to_removed_paths=len(report['references_to_removed_paths']),
        unanalysed_operation_paths=len(report['unanalysed_operation_paths']),live_project_checked=not reproduced,
        historical_baseline_check_verified=False,compilation_verified=False,scientific_verification=False,full_syntax_coverage=False)


def verified(bundle,anchor):
    k.digest(anchor);m.require(bundle.is_dir() and not bundle.is_symlink(),'regular preflight directory')
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'manifest anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema decision_sha256 files');m.require(manifest['schema']=='geek-work-operation-preflight-bundle-1','manifest schema')
    payload,receipt,archive=ops.verified_decision(bundle/'decision',manifest['decision_sha256'])
    selection_raw=m.read(bundle/'selection.json');spec=selection(selection_raw);expected,kinds=requirements(spec,receipt)
    names={'selection.json','report.json'}|{'baseline/'+n for n,h in expected.items() if h is not None}|{'sources/'+n for n in spec['files']}
    m.require(type(manifest['files']) is dict and set(manifest['files'])==names,'preflight file set')
    tree.exact_tree(bundle,names|{'decision/'+n for n in archive}|{'manifest.json'})
    data={};total=0
    for name in sorted(names):
        limit=p.MAX_TOTAL if name=='report.json' else p.MAX_FILE if name.startswith(('baseline/','sources/')) else m.MAX_ARTIFACT
        blob=m.read(bundle/name,limit);total+=len(blob);m.require(total<=MAX_BASELINE+p.MAX_TOTAL*2+m.MAX_ARTIFACT,'archive payload limit')
        m.require(m.sha(blob)==manifest['files'][name],'preflight artifact hash mismatch');data[name]=blob
    baseline={n:None if digest is None else data['baseline/'+n] for n,digest in expected.items()}
    for name,blob in baseline.items():
        if blob is not None:ops.content(blob,kinds[name])
    report,final=analyze(data['selection.json'],manifest['decision_sha256'],payload,receipt,baseline)
    m.require(data['report.json']==m.encoded(report),'report reproduction mismatch')
    m.require({n:data['sources/'+n] for n in final}==final,'final projection mismatch')
    return report,{**data,**{'decision/'+n:x for n,x in archive.items()},'manifest.json':raw}


def verify(bundle,anchor):
    report,_=verified(bundle,anchor)
    return summary(report,anchor,True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('check')
    for n in ('decision','root','selection','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('decision-sha256','selection-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=parser.parse_args()
    if a.action=='check':result=check(a.decision,a.decision_sha256,a.root,a.selection,a.selection_sha256,a.output)
    else:result=verify(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']!='no_findings_in_supported_subset':raise SystemExit(2)


if __name__=='__main__':main()
