#!/usr/bin/env python3
"""Bind an archived pdfLaTeX result to exact allowlisted manuscript package bytes."""
import argparse
from pathlib import Path
import geek_work_manuscript_release as release
import geek_work_latex_verify as latex

m=release.m;k=release.k;tree=release.tree
CLEAN='source_bound_compile_consistent'


def request_files(source_anchor,source):
    spec=m.load(source['manifest.json'])
    request=dict(schema='geek-work-latex-compile-request-1',entry=spec['entry'],files=[dict(path=n,sha256=spec['files'][n]['sha256']) for n in sorted(spec['files'])])
    latex.c.request(request);total=0
    for row in request['files']:
        blob=source['files/'+row['path']];total+=len(blob)
        m.require(len(blob)<=latex.c.common.MAX_FILE and total<=latex.c.common.MAX_TOTAL,'compile source byte limit')
        if Path(row['path']).suffix in {'.tex','.bib','.sty','.cls'}:m.source(blob)
    raw=m.encoded(request)
    binding=m.encoded(dict(schema='geek-work-release-compile-request-binding-1',source_package_sha256=source_anchor,request_sha256=m.sha(raw),compilation_performed=False,privacy_verified=False,publication_authorized=False))
    return request,{'request.json':raw,'binding.json':binding,**{'source-package/'+n:x for n,x in source.items()}}


def prepare(source,anchor,output):
    release.g.pre.ops.outside(output,source);_,data=release.verified_public(source,anchor)
    request,files=request_files(anchor,data)
    manifest=m.encoded(dict(schema='geek-work-release-compile-request-manifest-1',source_package_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status='compile_request_prepared',manifest_sha256=m.sha(manifest),request_sha256=m.sha(files['request.json']),source_package_sha256=anchor,entry=request['entry'],compilation_performed=False)


def verified_request(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'request bundle anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema source_package_sha256 files');m.require(manifest['schema']=='geek-work-release-compile-request-manifest-1','request bundle schema')
    _,source=release.verified_public(bundle/'source-package',manifest['source_package_sha256'])
    request,files=request_files(manifest['source_package_sha256'],source)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'request bundle hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'request reproduction mismatch')
    return request,{**files,'manifest.json':raw},manifest['source_package_sha256']


def verify_request(bundle,anchor):
    request,files,source_anchor=verified_request(bundle,anchor)
    return dict(status='compile_request_consistent',manifest_sha256=anchor,request_sha256=m.sha(files['request.json']),source_package_sha256=source_anchor,entry=request['entry'],compilation_performed=False)


def binding(request_anchor,request,request_archive,source_anchor,compile_anchor,summary,compiled):
    recorded=latex.c.request(m.load(compiled['request.json']))
    m.require(recorded['entry']==request['entry'] and {r['path']:r['sha256'] for r in recorded['files']}=={r['path']:r['sha256'] for r in request['files']},'compile request contract differs from selected release')
    expected={'sources/'+r['path']:request_archive['source-package/files/'+r['path']] for r in request['files']}
    m.require({n:x for n,x in compiled.items() if n.startswith('sources/')}==expected,'compile source bytes differ from selected release')
    status={'compiled_bundle_consistent':CLEAN,'warning_bundle_consistent':'source_bound_compile_needs_review','failure_archive_intact':'source_bound_failure_archive'}[summary['status']]
    pdf=None
    if summary['compiled_profile_checked']:
        blob=compiled['artifacts/document.pdf'];pdf=dict(sha256=m.sha(blob),bytes=len(blob))
    return dict(schema='geek-work-release-compile-binding-1',status=status,source_package_sha256=source_anchor,
        request_bundle_sha256=request_anchor,compile_bundle_sha256=compile_anchor,entry=request['entry'],files=request['files'],source_bytes_match=True,
        request_contract_matches=True,prepared_request_sha256=m.sha(request_archive['request.json']),recorded_request_sha256=m.sha(compiled['request.json']),request_bytes_identical=compiled['request.json']==request_archive['request.json'],
        pdf=pdf,compile_archive_check=summary,diagnostics_review_required=status!=CLEAN,compilation_replayed=False,
        pdf_visual_review=False,pdf_conformance_verified=False,privacy_verified=False,scientific_verification=False,publication_authorized=False,
        limits='Exact source bytes and entry/path/hash contract bound to a consistent recorded LaTeX archive; request encodings have separate SHA values. No compiler replay, independent execution attestation, PDF rendering/conformance/safety, privacy or publication approval. Warning and failure states are retained.')


def bind(request_bundle,request_anchor,compile_bundle,compile_anchor,output):
    release.g.pre.ops.outside(output,request_bundle,compile_bundle)
    request,rfiles,source_anchor=verified_request(request_bundle,request_anchor);summary,cfiles=latex.verified(compile_bundle,compile_anchor)
    report=binding(request_anchor,request,rfiles,source_anchor,compile_anchor,summary,cfiles)
    files={'report.json':m.encoded(report),**{'request/'+n:x for n,x in rfiles.items()},**{'compile/'+n:x for n,x in cfiles.items()}}
    manifest=m.encoded(dict(schema='geek-work-release-compile-binding-manifest-1',request_bundle_sha256=request_anchor,compile_bundle_sha256=compile_anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=report['status'],manifest_sha256=m.sha(manifest),source_package_sha256=source_anchor,pdf=report['pdf'],source_bytes_match=True,compilation_replayed=False,pdf_visual_review=False,publication_authorized=False)


def verified_binding(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'binding anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema request_bundle_sha256 compile_bundle_sha256 files');m.require(manifest['schema']=='geek-work-release-compile-binding-manifest-1','binding schema')
    request,rfiles,source_anchor=verified_request(bundle/'request',manifest['request_bundle_sha256']);summary,cfiles=latex.verified(bundle/'compile',manifest['compile_bundle_sha256'])
    report=binding(manifest['request_bundle_sha256'],request,rfiles,source_anchor,manifest['compile_bundle_sha256'],summary,cfiles)
    files={'report.json':m.encoded(report),**{'request/'+n:x for n,x in rfiles.items()},**{'compile/'+n:x for n,x in cfiles.items()}}
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'binding file hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'binding reproduction mismatch')
    return report,{**files,'manifest.json':raw}


def verify_binding(bundle,anchor):
    report,_=verified_binding(bundle,anchor)
    return dict(status=report['status'],manifest_sha256=anchor,source_package_sha256=report['source_package_sha256'],pdf=report['pdf'],reproduced=True,source_bytes_match=True,compilation_replayed=False,pdf_visual_review=False,publication_authorized=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare')
    for n in ('source','output'):q.add_argument('--'+n,type=Path,required=True)
    q.add_argument('--sha256',required=True)
    q=sub.add_parser('bind')
    for n in ('request-bundle','compile-bundle','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('request-sha256','compile-sha256'):q.add_argument('--'+n,required=True)
    for action in ('verify-request','verify-binding'):
        q=sub.add_parser(action);q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=parser.parse_args()
    if a.action=='prepare':result=prepare(a.source,a.sha256,a.output)
    elif a.action=='bind':result=bind(a.request_bundle,a.request_sha256,a.compile_bundle,a.compile_sha256,a.output)
    elif a.action=='verify-request':result=verify_request(a.bundle,a.sha256)
    else:result=verify_binding(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')
    if result['status'] in {'source_bound_compile_needs_review','source_bound_failure_archive'}:raise SystemExit(2)


if __name__=='__main__':main()
