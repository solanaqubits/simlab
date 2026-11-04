#!/usr/bin/env python3
"""Bounded original-page selection using a separately pinned Docker runtime."""
import argparse
import signal
from pathlib import Path
import time
import geek_work_pdf_container as c
import geek_work_raw_pdf_pages as raw

m=c.m;k=c.k;tree=c.tree
SCHEMA='geek-work-raw-pdf-selection-manifest-1'


def derived(pdf,anchor,runtime,descriptors,receipts,files,first,last):
    def failure():
        return dict(schema='geek-work-raw-pdf-selection-failure-report-1',requested_source_pages=list(range(first,last+1)),status='cleanup_failed' if any(not row['container_removed'] for row in receipts) else 'container_render_failed',pdf=dict(sha256=anchor,bytes=len(pdf)),source_kind='original_pdf_bytes',compile_binding_verified=False,operations=receipts,pdf_visual_review=False,renderer_execution_independently_verified=False,scientific_verification=False,publication_authorized=False),{}
    if any(row['status']!='completed' for row in receipts):return failure()
    try:
        m.require(len(descriptors)>=2,'missing info operation')
        def streams(index):
            base=descriptors[index]['folder']+'/'
            errors=b''.join(files[base+phase+'.stderr'] for phase in c.PHASES)
            m.require(len(errors)<=65536,'diagnostic aggregate limit');return files[base+'start.stdout'],errors
        info,errors=streams(1);total=raw.total_pages(info);raw.selection(first,last,total);count=last-first+1
        m.require(len(descriptors)==count+2,'selected container page coverage')
        _,profile_errors=streams(0);errors=profile_errors+errors
        images={};diagnostics={}
        for i in range(1,count+1):
            image,err=streams(i+1);images[f'{i:04}.png']=image;diagnostics[f'{i:04}.stdout']=b'';diagnostics[f'{i:04}.stderr']=err
        report=raw.report(pdf,anchor,runtime,info,errors,images,diagnostics,first,last)
        report['container_operations']=receipts
        views={'pdfinfo.stdout':info,'pdfinfo.stderr':errors,**{'pages/'+n:x for n,x in images.items()},**{'diagnostics/'+n:x for n,x in diagnostics.items()}}
        return report,views
    except ValueError:return failure()


def render(pdf_path,anchor,renderer_anchor,first,last,output):
    raw.selection(first,last,100000)
    c.p.b.release.g.pre.ops.outside(output,pdf_path);m.require(not output.exists() and not output.is_symlink(),'new raw container packet required')
    k.digest(anchor);k.digest(renderer_anchor);pdf=m.read(pdf_path,c.selection_profile()['max_pdf_bytes']);m.require(pdf.startswith(b'%PDF-') and m.sha(pdf)==anchor,'original PDF header/anchor mismatch')
    runtime=c.selection_profile();m.require(m.sha(m.encoded(runtime))==renderer_anchor,'container profile anchor mismatch')
    output.mkdir(parents=True);(output/'original.pdf').write_bytes(pdf);(output/'profile.json').write_bytes(m.encoded(runtime));(output/'operations').mkdir()
    descriptors=[];started=time.monotonic()
    def step(mode,page=None):
        m.require(time.monotonic()-started<c.TOTAL_TIMEOUT,'container page loop deadline')
        folder=f'operations/{len(descriptors):04}';receipt=c.execute(output/folder,mode,pdf if mode!='profile' else b'',page,runtime=runtime)
        descriptors.append(dict(folder=folder,name=receipt['name'],mode=mode,page=page));return receipt['status']=='completed'
    try:
        if step('profile') and step('info'):
            total=raw.total_pages(m.read(output/'operations/0001/start.stdout',65536));raw.selection(first,last,total)
            for page in range(first,last+1):
                if not step('page',page):break
    except ValueError:pass
    if not descriptors:(output/'operations').rmdir()
    receipts,operations=c.operation_files(output,descriptors,anchor,runtime=runtime,source_pages=list(range(first,last+1)))
    report,views=derived(pdf,anchor,runtime,descriptors,receipts,operations,first,last)
    files={'original.pdf':pdf,'profile.json':m.encoded(runtime),'report.json':m.encoded(report),**operations,**views}
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'container report limit')
    for name,data in views.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    (output/'report.json').write_bytes(files['report.json'])
    manifest=m.encoded(dict(schema=SCHEMA,pdf_sha256=anchor,renderer_profile_sha256=renderer_anchor,first_page=first,last_page=last,operations=descriptors,files={n:m.sha(x) for n,x in files.items()}))
    (output/'manifest.json').write_bytes(manifest);return dict(status=report['status'],manifest_sha256=m.sha(manifest))


def verified(bundle,anchor,require_pages=False):
    k.digest(anchor);blob=m.read(bundle/'manifest.json');m.require(m.sha(blob)==anchor,'raw container packet anchor mismatch');spec=m.load(blob)
    k.obj(spec,'schema pdf_sha256 renderer_profile_sha256 first_page last_page operations files');m.require(spec['schema']==SCHEMA,'raw container packet schema');k.digest(spec['pdf_sha256']);first=spec['first_page'];last=spec['last_page'];raw.selection(first,last,100000)
    pdf=m.read(bundle/'original.pdf',c.selection_profile()['max_pdf_bytes']);m.require(pdf.startswith(b'%PDF-') and m.sha(pdf)==spec['pdf_sha256'],'original PDF header/anchor mismatch')
    runtime_raw=m.read(bundle/'profile.json');runtime=m.load(runtime_raw);c.validate_selection_profile(runtime)
    m.require(runtime_raw==m.encoded(runtime) and m.sha(runtime_raw)==spec['renderer_profile_sha256'],'container profile binding')
    receipts,operations=c.operation_files(bundle,spec['operations'],spec['pdf_sha256'],runtime=runtime,source_pages=list(range(first,last+1)));report,views=derived(pdf,spec['pdf_sha256'],runtime,spec['operations'],receipts,operations,first,last)
    files={'original.pdf':pdf,'profile.json':runtime_raw,'report.json':m.encoded(report),**operations,**views}
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'container report limit');tree.exact_tree(bundle,set(files)|{'manifest.json'})
    m.require(spec['files']=={n:m.sha(x) for n,x in files.items()},'raw container packet hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'raw container reproduction mismatch')
    if require_pages:m.require(report['status']==raw.STATUS,'successful raw container pages required')
    return report,{**files,'manifest.json':blob}


def main():
    def interrupted(signum,frame):raise InterruptedError('operator termination')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('render');q.add_argument('--pdf',type=Path,required=True);q.add_argument('--pdf-sha256',required=True);q.add_argument('--renderer-sha256',required=True);q.add_argument('--output',type=Path,required=True);q.add_argument('--first-page',type=int,required=True);q.add_argument('--last-page',type=int,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    if a.action=='render':result=render(a.pdf,a.pdf_sha256,a.renderer_sha256,a.first_page,a.last_page,a.output)
    else:
        report,_=verified(a.bundle,a.sha256);result=dict(status=report['status'],manifest_sha256=a.sha256,integrity_reproduced=True)
    print(m.encoded(result).decode(),end='');raise SystemExit(2 if result['status']==raw.STATUS else 3)


if __name__=='__main__':main()
