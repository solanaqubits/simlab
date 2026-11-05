#!/usr/bin/env python3
"""Bound a small page selection to original PDF bytes, without a compile claim."""
import argparse
from pathlib import Path
import re
import tempfile
import time
import geek_work_pdf_pages as p

m=p.m;k=p.k;tree=p.tree
MAX_PDF=32*1024*1024
SCHEMA='geek-work-raw-pdf-pages-manifest-1'
STATUS='raw_pdf_pages_review_required'


def total_pages(info):
    text=info.decode('utf-8','replace')
    counts=re.findall(r'^Pages:\s*(\d+)\s*$',text,re.M)
    encrypted=re.findall(r'^Encrypted:\s*(\S+)',text,re.M)
    m.require(len(counts)==1 and encrypted==['no'],'unambiguous unencrypted PDF required')
    count=int(counts[0]);m.require(1<=count<=100000,'PDF page count limit');return count


def selection(first,last,total):
    m.require(type(first) is int and type(last) is int and 1<=first<=last<=total and last-first+1<=p.MAX_PAGES,'page selection limit')
    return list(range(first,last+1))


def report(pdf,anchor,runtime,info,errors,images,diagnostics,first,last):
    k.digest(anchor);m.require(m.sha(pdf)==anchor,'original PDF anchor mismatch')
    m.require(len(pdf)<=MAX_PDF and pdf.startswith(b'%PDF-'),'PDF header/size')
    p.validate_profile(runtime)
    count=total_pages(info);numbers=selection(first,last,count)
    m.require(set(images)=={f'{i:04}.png' for i in range(1,len(numbers)+1)},'selected page coverage')
    m.require(set(diagnostics)=={f'{i:04}.{suffix}' for i in range(1,len(numbers)+1) for suffix in ('stdout','stderr')},'selected diagnostic coverage')
    m.require(len(info)<=65536 and len(errors)<=65536 and all(len(x)<=65536 for x in diagnostics.values()),'diagnostic limits')
    m.require(sum(map(len,images.values()))<=p.MAX_IMAGES,'page image total limit')
    result=dict(schema='geek-work-raw-pdf-pages-report-1',status=STATUS,pdf=dict(sha256=anchor,bytes=len(pdf)),
        source_kind='original_pdf_bytes',source_binding_status='raw_pdf_no_compile_binding',compile_binding_verified=False,
        pdf_page_count=count,page_count=len(numbers),source_pdf_pages=numbers,full_document_coverage=numbers==list(range(1,count+1)),
        renderer_profile_sha256=m.sha(m.encoded(runtime)),pages={n:p.png(x) for n,x in sorted(images.items())},
        renderer_diagnostics_present=bool(errors) or any(diagnostics.values()),diagnostics_review_required=True,
        png_container_checks=True,pixels_decoded_by_verifier=False,pdf_visual_review=False,pdf_conformance_verified=False,
        renderer_execution_independently_verified=False,scientific_verification=False,publication_authorized=False,
        limits='Original PDF bytes and selected page images, no manuscript/compile binding. Page ordinals map explicitly to source PDF pages; omitted pages are not processed. Native trusted host, no OS/network sandbox or pinned shared libraries. Offline integrity checks do not prove raster fidelity, OCR quality, completeness, authorship or safety of PDF content. 96 DPI is a review profile, not a qualified OCR preprocessing choice.')

    if runtime['schema'] in ('geek-work-pdf-container-profile-1','geek-work-pdf-container-profile-2'):
        result.update(renderer_backend='docker',container_configuration_recorded=True,container_escape_protection_verified=False,limits='Original PDF and selected images without compile binding. Recorded pinned Docker image, no network or host binds, readonly/non-root/resource limits and cleanup. Docker/host/kernel trusted; no adversarial containment qualification or independent execution authentication. Offline verification checks recorded configuration, original bytes, captures and PNG containers without Docker. No OCR or visual/scientific acceptance.')
    return result


def files_for(pdf,runtime,info,errors,images,diagnostics,result):
    return {'original.pdf':pdf,'profile.json':m.encoded(runtime),'pdfinfo.stdout':info,'pdfinfo.stderr':errors,'report.json':m.encoded(result),**{'pages/'+n:x for n,x in images.items()},**{'diagnostics/'+n:x for n,x in diagnostics.items()}}


def render(pdf_path,anchor,renderer_anchor,first,last,output,trusted_native=False,tool_dir=None):
    m.require(trusted_native is True,'explicit trusted-native acknowledgement required')
    p.b.release.g.pre.ops.outside(output,pdf_path);m.require(not output.exists() and not output.is_symlink(),'new raw PDF packet required')
    k.digest(anchor);k.digest(renderer_anchor);pdf=m.read(pdf_path,MAX_PDF)
    m.require(m.sha(pdf)==anchor and pdf.startswith(b'%PDF-'),'PDF anchor/header mismatch')
    m.require(type(first) is int and type(last) is int and 1<=first<=last and last-first+1<=p.MAX_PAGES,'page selection limit')
    runtime=p.profile(tool_dir);m.require(m.sha(m.encoded(runtime))==renderer_anchor,'renderer profile anchor mismatch')
    images={};diagnostics={};started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='geek-work-raw-pdf-') as tmp:
        tmp=Path(tmp);(tmp/'input.pdf').write_bytes(pdf)
        info,errors=p.run([runtime['tools']['pdfinfo']['path'],'input.pdf'],tmp)
        numbers=selection(first,last,total_pages(info))
        for ordinal,number in enumerate(numbers,1):
            remaining=p.TOTAL_TIMEOUT-(time.monotonic()-started);m.require(remaining>0,'total renderer timeout')
            prefix=f'page-{ordinal:04}'
            out,err=p.run([runtime['tools']['pdftoppm']['path'],'-f',str(number),'-l',str(number),'-r',str(p.DPI),'-png','-singlefile','input.pdf',prefix],tmp,min(p.TIMEOUT,remaining))
            diagnostics[f'{ordinal:04}.stdout']=out;diagnostics[f'{ordinal:04}.stderr']=err
            blob=m.read(tmp/(prefix+'.png'),p.MAX_IMAGE);p.png(blob);images[f'{ordinal:04}.png']=blob
            m.require(sum(map(len,images.values()))<=p.MAX_IMAGES,'page image total limit')
    result=report(pdf,anchor,runtime,info,errors,images,diagnostics,first,last)
    files=files_for(pdf,runtime,info,errors,images,diagnostics,result)
    manifest=m.encoded(dict(schema=SCHEMA,pdf_sha256=anchor,renderer_profile_sha256=renderer_anchor,first_page=first,last_page=last,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=STATUS,manifest_sha256=m.sha(manifest),source_pdf_pages=numbers,full_document_coverage=result['full_document_coverage'])


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'raw PDF packet anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema pdf_sha256 renderer_profile_sha256 first_page last_page files');m.require(manifest['schema']==SCHEMA,'raw PDF packet schema')
    pdf=m.read(bundle/'original.pdf',MAX_PDF);runtime_raw=m.read(bundle/'profile.json');runtime=m.load(runtime_raw)
    m.require(runtime.get('schema')=='geek-work-pdf-renderer-profile-1','native packet requires native profile')
    m.require(runtime_raw==m.encoded(runtime) and m.sha(runtime_raw)==manifest['renderer_profile_sha256'],'renderer profile binding')
    info=m.read(bundle/'pdfinfo.stdout',65536);errors=m.read(bundle/'pdfinfo.stderr',65536)
    numbers=selection(manifest['first_page'],manifest['last_page'],total_pages(info))
    images={f'{i:04}.png':m.read(bundle/'pages'/f'{i:04}.png',p.MAX_IMAGE) for i in range(1,len(numbers)+1)}
    diagnostics={f'{i:04}.{suffix}':m.read(bundle/'diagnostics'/f'{i:04}.{suffix}',65536) for i in range(1,len(numbers)+1) for suffix in ('stdout','stderr')}
    result=report(pdf,manifest['pdf_sha256'],runtime,info,errors,images,diagnostics,manifest['first_page'],manifest['last_page'])
    files=files_for(pdf,runtime,info,errors,images,diagnostics,result)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'raw PDF packet hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'raw PDF packet reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('render');q.add_argument('--pdf',type=Path,required=True);q.add_argument('--pdf-sha256',required=True);q.add_argument('--renderer-sha256',required=True);q.add_argument('--first-page',type=int,required=True);q.add_argument('--last-page',type=int,required=True);q.add_argument('--trusted-native',action='store_true');q.add_argument('--tool-dir',type=Path);q.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    if a.action=='render':result=render(a.pdf,a.pdf_sha256,a.renderer_sha256,a.first_page,a.last_page,a.output,a.trusted_native,a.tool_dir)
    else:
        r,_=verified(a.bundle,a.sha256);result=dict(status=STATUS,manifest_sha256=a.sha256,source_pdf_pages=r['source_pdf_pages'],full_document_coverage=r['full_document_coverage'],integrity_reproduced=True)
    print(m.encoded(result).decode(),end='');raise SystemExit(2)


if __name__=='__main__':main()
