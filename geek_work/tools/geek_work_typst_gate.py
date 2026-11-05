#!/usr/bin/env python3
"""Gate Typst compilation on a clean literal preflight and bind its exact snapshot."""
import argparse
from pathlib import Path
import geek_work_typst_preflight as pre
import geek_work_compile_verify as compiled

m=pre.m;k=pre.k;tree=pre.tree
CLEAN='preflight_bound_typst_compile_consistent'


def accepted_preflight(bundle,anchor):
    report,archive=pre.verified(bundle,anchor)
    m.require(report['status']=='no_dependency_findings_in_supported_subset','PREFLIGHT_REVIEW_REQUIRED')
    return report,archive


def report(preflight_anchor,preflight,pa,compile_anchor,summary,ca):
    expected=compiled.c.request(m.load(pa['request.json']));actual=compiled.c.request(m.load(ca['request.json']))
    m.require(actual['entry']==expected['entry'] and {r['path']:r['sha256'] for r in actual['files']}=={r['path']:r['sha256'] for r in expected['files']},'COMPILE_REQUEST_MISMATCH')
    m.require({n:x for n,x in ca.items() if n.startswith('sources/')}=={n:x for n,x in pa.items() if n.startswith('sources/')},'COMPILE_SOURCE_MISMATCH')
    success=summary['status']=='compiled_bundle_consistent';diagnostics=bool(ca.get('compiler.log',b'').strip());pdf=None
    if success:
        blob=ca['document.pdf'];pdf=dict(sha256=m.sha(blob),bytes=len(blob))
    status='preflight_bound_typst_failure_archive' if not success else 'preflight_bound_typst_compile_needs_review' if diagnostics else CLEAN
    return dict(schema='geek-work-typst-gate-report-1',status=status,preflight_sha256=preflight_anchor,compile_sha256=compile_anchor,
        entry=expected['entry'],files=expected['files'],preflight_status=preflight['status'],source_bytes_match=True,
        prepared_request_sha256=m.sha(pa['request.json']),recorded_request_sha256=m.sha(ca['request.json']),request_bytes_identical=pa['request.json']==ca['request.json'],
        compile_archive_check=summary,compiler_diagnostics_present=diagnostics,pdf=pdf,compilation_replayed=False,pdf_visual_review=False,
        full_typst_syntax_checked=False,reference_semantics_checked=False,scientific_verification=False,publication_authorized=False,
        limits='Clean literal dependency preflight and exact request/source contract bound to recorded Typst archive. Nonempty compiler log requires review; failure integrity is not independent execution qualification. No full Typst parsing, PDF conformance/visual review or publication approval.')


def files_for(pa,ca,result):
    return {'report.json':m.encoded(result),**{'preflight/'+n:x for n,x in pa.items()},**{'compile/'+n:x for n,x in ca.items()}}


def manifest_for(preflight_anchor,compile_anchor,files):
    return m.encoded(dict(schema='geek-work-typst-gate-manifest-1',preflight_sha256=preflight_anchor,compile_sha256=compile_anchor,files={n:m.sha(x) for n,x in files.items()}))


def summary(result,anchor,invoked=False,reproduced=False):
    return dict(status=result['status'],manifest_sha256=anchor,pdf=result['pdf'],compiler_invoked_here=invoked,reproduced=reproduced,source_bytes_match=True,pdf_visual_review=False,publication_authorized=False)


def bind(preflight,preflight_anchor,compile_bundle,compile_anchor,output):
    pre.ops.outside(output,preflight,compile_bundle);pr,pa=accepted_preflight(preflight,preflight_anchor);cr,ca=compiled.verified(compile_bundle,compile_anchor)
    result=report(preflight_anchor,pr,pa,compile_anchor,cr,ca);files=files_for(pa,ca,result);manifest=manifest_for(preflight_anchor,compile_anchor,files)
    tree.write_tree(output,{**files,'manifest.json':manifest});return summary(result,m.sha(manifest))


def run(preflight,anchor,output):
    pre.ops.outside(output,preflight);m.require(not output.exists() and not output.is_symlink(),'new output required')
    _,archive=accepted_preflight(preflight,anchor)
    tree.write_tree(output,{'preflight/'+n:x for n,x in archive.items()})
    result=compiled.c.build(output/'preflight/sources',output/'preflight/request.json',m.sha(archive['request.json']),output/'compile')
    pr,pa=accepted_preflight(output/'preflight',anchor);cr,ca=compiled.verified(output/'compile',result['manifest_sha256'])
    bound=report(anchor,pr,pa,result['manifest_sha256'],cr,ca);files=files_for(pa,ca,bound)
    with (output/'report.json').open('xb') as f:f.write(files['report.json'])
    tree.exact_tree(output,set(files))
    for n,x in files.items():m.require(m.read(output/n,max(len(x),1))==x,'staged archive changed')
    manifest=manifest_for(anchor,result['manifest_sha256'],files)
    with (output/'manifest.json').open('xb') as f:f.write(manifest)
    return summary(bound,m.sha(manifest),invoked=True)


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'gate anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema preflight_sha256 compile_sha256 files');m.require(manifest['schema']=='geek-work-typst-gate-manifest-1','gate schema')
    pr,pa=accepted_preflight(bundle/'preflight',manifest['preflight_sha256']);cr,ca=compiled.verified(bundle/'compile',manifest['compile_sha256'])
    result=report(manifest['preflight_sha256'],pr,pa,manifest['compile_sha256'],cr,ca);files=files_for(pa,ca,result)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'gate artifact hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'gate reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    result,_=verified(bundle,anchor)
    return summary(result,anchor,reproduced=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('run')
    for n in ('preflight','output'):q.add_argument('--'+n,type=Path,required=True)
    q.add_argument('--sha256',required=True)
    q=sub.add_parser('bind')
    for n in ('preflight','compile-bundle','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','compile-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    if a.action=='run':result=run(a.preflight,a.sha256,a.output)
    elif a.action=='bind':result=bind(a.preflight,a.sha256,a.compile_bundle,a.compile_sha256,a.output)
    else:result=verify(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status']!=CLEAN:raise SystemExit(2)


if __name__=='__main__':main()
