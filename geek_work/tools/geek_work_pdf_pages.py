#!/usr/bin/env python3
"""Render a source-bound PDF into a private, bounded page-review packet."""
import argparse
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
import geek_work_release_compile as b
import geek_work_pdf_binding as pdf_input

m=b.m;k=b.k;tree=b.tree
MAX_PAGES=16
MAX_IMAGE=8*1024*1024
MAX_IMAGES=64*1024*1024
MAX_PIXELS=16_000_000
DPI=96
TIMEOUT=15
TOTAL_TIMEOUT=60


def run(argv,cwd=None,timeout=TIMEOUT):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(TIMEOUT,TIMEOUT))
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_IMAGE,MAX_IMAGE))
        resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
        result=subprocess.run(argv,cwd=cwd,stdout=stdout,stderr=stderr,timeout=timeout,preexec_fn=limits,env={'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':str(cwd) if cwd else '/nonexistent'})
        stdout.seek(0);out=stdout.read(65537);stderr.seek(0);err=stderr.read(65537)
    m.require(len(out)<=65536 and len(err)<=65536,'renderer capture limit')
    m.require(result.returncode==0,'renderer process failed: '+err[:2000].decode('utf-8','replace'));return out,err


def profile(tool_dir=None):
    # Explicit selection must never fall back to another executable on PATH.
    selected={}
    if tool_dir is not None:
        tool_dir=Path(tool_dir).resolve();m.require(tool_dir.is_dir(),'renderer tool directory missing')
        for name in ('pdfinfo','pdftoppm'):
            path=(tool_dir/name).resolve()
            m.require(path.is_file() and os.access(path,os.X_OK),'renderer executable missing: '+name)
            selected[name]=path
    tools={}
    for name in ('pdfinfo','pdftoppm'):
        executable=selected.get(name) if tool_dir is not None else shutil.which(name);m.require(executable is not None,'renderer tool missing: '+name)
        path=Path(executable).resolve();raw=m.read(path,32*1024*1024);out,err=run([str(path),'-v']);version=(out+err).decode('utf-8').strip();k.text(version)
        tools[name]=dict(path=str(path),sha256=m.sha(raw),version=version)
    return dict(schema='geek-work-pdf-renderer-profile-1',tools=tools,dpi=DPI,max_pages=MAX_PAGES,max_pixels=MAX_PIXELS,
        memory_bytes=512*1024*1024,process_timeout_seconds=TIMEOUT,total_timeout_seconds=TOTAL_TIMEOUT,shared_libraries_pinned=False,os_sandboxed=False)


def validate_profile(spec):
    if spec.get('schema')=='geek-work-pdf-container-profile-2':
        import geek_work_pdf_container as container
        container.validate_selection_profile(spec);return
    if spec.get('schema')=='geek-work-pdf-container-profile-1':
        import geek_work_pdf_container as container
        container.validate_profile(spec);return
    k.obj(spec,'schema tools dpi max_pages max_pixels memory_bytes process_timeout_seconds total_timeout_seconds shared_libraries_pinned os_sandboxed')
    m.require(spec['schema']=='geek-work-pdf-renderer-profile-1' and set(spec['tools'])=={'pdfinfo','pdftoppm'},'renderer profile schema')
    for name,row in spec['tools'].items():
        k.obj(row,'path sha256 version');k.digest(row['sha256']);k.text(row['version'])
        m.require(type(row['path']) is str and Path(row['path']).is_absolute(),'absolute renderer path')
    m.require(spec['shared_libraries_pinned'] is False and spec['os_sandboxed'] is False,'unsupported renderer guarantees')
    expected=dict(dpi=DPI,max_pages=MAX_PAGES,max_pixels=MAX_PIXELS,memory_bytes=512*1024*1024,process_timeout_seconds=TIMEOUT,total_timeout_seconds=TOTAL_TIMEOUT,shared_libraries_pinned=False,os_sandboxed=False)
    m.require({n:spec[n] for n in expected}==expected,'renderer limits/profile mismatch')


def page_count(info):
    text=info.decode('utf-8','replace');pages=re.findall(r'^Pages:\s*(\d+)\s*$',text,re.M)
    encrypted=re.findall(r'^Encrypted:\s*(\S+)',text,re.M)
    m.require(len(pages)==1 and encrypted==['no'],'unambiguous unencrypted PDF required')
    count=int(pages[0]);m.require(1<=count<=MAX_PAGES,'page limit');return count


def png(blob):
    m.require(len(blob)<=MAX_IMAGE and blob.startswith(b'\x89PNG\r\n\x1a\n'),'PNG signature/size')
    at=8;chunks=[];width=height=None
    while at<len(blob):
        m.require(at+12<=len(blob),'truncated PNG chunk');size=struct.unpack('>I',blob[at:at+4])[0];end=at+12+size;m.require(end<=len(blob),'PNG chunk bounds')
        kind=blob[at+4:at+8];data=blob[at+8:at+8+size];crc=struct.unpack('>I',blob[at+8+size:end])[0]
        m.require(zlib.crc32(kind+data)&0xffffffff==crc,'PNG CRC')
        if not chunks:
            m.require(kind==b'IHDR' and size==13,'PNG IHDR');width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            m.require(1<=width<=8192 and 1<=height<=8192 and width*height<=MAX_PIXELS,'PNG pixel limit')
            m.require(depth==8 and color in (2,6) and (compression,filtering,interlace)==(0,0,0),'supported PNG format')
        else:m.require(kind!=b'IHDR','duplicate PNG IHDR')
        chunks.append(kind);at=end
        if kind==b'IEND':m.require(size==0 and at==len(blob),'PNG end/trailing bytes');break
    m.require(chunks and chunks[-1]==b'IEND' and b'IDAT' in chunks,'PNG image/end chunks')
    return dict(width=width,height=height,bytes=len(blob),sha256=m.sha(blob))


def report(binding,anchor,runtime,info,images,diagnostics,info_errors):
    validate_profile(runtime);count=page_count(info)
    m.require(binding['pdf'] is not None and binding['status'] in {b.CLEAN,'source_bound_compile_needs_review',pdf_input.typst.CLEAN,'preflight_bound_typst_compile_needs_review'},'compiled PDF required')
    m.require(set(images)=={f'{i:04}.png' for i in range(1,count+1)},'page image coverage')
    m.require(sum(map(len,images.values()))<=MAX_IMAGES,'page image total limit')
    m.require(set(diagnostics)=={f'{i:04}.{suffix}' for i in range(1,count+1) for suffix in ('stdout','stderr')},'page diagnostic coverage')
    m.require(len(info_errors)<=65536 and all(len(x)<=65536 for x in diagnostics.values()),'diagnostic limits')
    result=dict(schema='geek-work-pdf-pages-report-1',status='pages_ready_for_review',binding_sha256=anchor,pdf=binding['pdf'],
        renderer_profile_sha256=m.sha(m.encoded(runtime)),source_binding_status=binding['status'],diagnostics_review_required=binding['diagnostics_review_required'],
        page_count=count,pages={n:png(x) for n,x in sorted(images.items())},renderer_diagnostics_present=bool(info_errors) or any(diagnostics.values()),png_container_checks=True,pixels_decoded_by_verifier=False,
        pdf_visual_review=False,pdf_conformance_verified=False,renderer_execution_independently_verified=False,scientific_verification=False,publication_authorized=False,
        limits='Private page images for review, not visual acceptance. Native Poppler/host trusted; bounded resources but no OS/network sandbox or pinned shared libraries. Offline verifier checks source binding, PNG containers, hashes and coverage without rendering or decompressing pixels.')

    if runtime.get('schema')=='geek-work-pdf-container-profile-1':
        result.update(renderer_backend='docker',container_configuration_recorded=True,container_escape_protection_verified=False,limits='Recorded pinned Docker image, no network or host binds, readonly/non-root/resource limits and cleanup. Docker/host/kernel trusted; not independent execution or adversarial containment qualification. Offline verification checks recorded configuration, source binding, captures and page containers without Docker or rendering.')
    if binding.get('binding_kind')=='typst_gate':result['binding_kind']='typst_gate'
    return result


def render(bundle,anchor,renderer_anchor,output,tool_dir=None):
    b.release.g.pre.ops.outside(output,bundle);m.require(not output.exists() and not output.is_symlink(),'new page output required');binding,archive,pdf=pdf_input.verified(bundle,anchor)
    m.require(binding['pdf'] is not None,'compiled PDF required');runtime=profile() if tool_dir is None else profile(tool_dir);k.digest(renderer_anchor);m.require(m.sha(m.encoded(runtime))==renderer_anchor,'renderer profile anchor mismatch')
    images={};diagnostics={};started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='geek-work-pdf-pages-') as tmp:
        tmp=Path(tmp);(tmp/'input.pdf').write_bytes(pdf)
        info,errors=run([runtime['tools']['pdfinfo']['path'],'input.pdf'],tmp);count=page_count(info)
        for i in range(1,count+1):
            remaining=TOTAL_TIMEOUT-(time.monotonic()-started);m.require(remaining>0,'total renderer timeout')
            prefix=f'page-{i:04}'
            out,err=run([runtime['tools']['pdftoppm']['path'],'-f',str(i),'-l',str(i),'-r',str(DPI),'-png','-singlefile','input.pdf',prefix],tmp,min(TIMEOUT,remaining))
            diagnostics[f'{i:04}.stdout']=out;diagnostics[f'{i:04}.stderr']=err
            blob=m.read(tmp/(prefix+'.png'),MAX_IMAGE);png(blob);images[f'{i:04}.png']=blob
            m.require(sum(map(len,images.values()))<=MAX_IMAGES,'page image total limit')
    result=report(binding,anchor,runtime,info,images,diagnostics,errors)
    files={'profile.json':m.encoded(runtime),'pdfinfo.stdout':info,'pdfinfo.stderr':errors,'report.json':m.encoded(result),**{'pages/'+n:x for n,x in images.items()},**{'diagnostics/'+n:x for n,x in diagnostics.items()},**{'binding/'+n:x for n,x in archive.items()}}
    manifest=m.encoded(dict(schema='geek-work-pdf-pages-manifest-1',binding_sha256=anchor,renderer_profile_sha256=renderer_anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status=result['status'],manifest_sha256=m.sha(manifest),page_count=count,source_binding_status=binding['status'],pdf_visual_review=False)


def verified(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'page packet anchor mismatch');manifest=m.load(raw)
    if manifest.get('schema')=='geek-work-pdf-container-pages-manifest-1':
        import geek_work_pdf_container as container
        return container.verified(bundle,anchor,require_pages=True)
    k.obj(manifest,'schema binding_sha256 renderer_profile_sha256 files');m.require(manifest['schema']=='geek-work-pdf-pages-manifest-1','page packet schema')
    binding,archive,_=pdf_input.verified(bundle/'binding',manifest['binding_sha256']);runtime_raw=m.read(bundle/'profile.json');runtime=m.load(runtime_raw);validate_profile(runtime)
    m.require(m.sha(runtime_raw)==manifest['renderer_profile_sha256'] and runtime_raw==m.encoded(runtime),'renderer profile binding')
    info=m.read(bundle/'pdfinfo.stdout',65536);errors=m.read(bundle/'pdfinfo.stderr',65536);count=page_count(info)
    images={f'{i:04}.png':m.read(bundle/'pages'/f'{i:04}.png',MAX_IMAGE) for i in range(1,count+1)}
    diagnostics={f'{i:04}.{suffix}':m.read(bundle/'diagnostics'/f'{i:04}.{suffix}',65536) for i in range(1,count+1) for suffix in ('stdout','stderr')}
    result=report(binding,manifest['binding_sha256'],runtime,info,images,diagnostics,errors)
    files={'profile.json':runtime_raw,'pdfinfo.stdout':info,'pdfinfo.stderr':errors,'report.json':m.encoded(result),**{'pages/'+n:x for n,x in images.items()},**{'diagnostics/'+n:x for n,x in diagnostics.items()},**{'binding/'+n:x for n,x in archive.items()}}
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'page packet hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'page packet reproduction mismatch')
    return result,{**files,'manifest.json':raw}


def verify(bundle,anchor):
    result,_=verified(bundle,anchor)
    return dict(status='page_packet_consistent',manifest_sha256=anchor,page_count=result['page_count'],source_binding_status=result['source_binding_status'],pdf_visual_review=False,renderer_execution_independently_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True);q=sub.add_parser('profile');q.add_argument('--tool-dir',type=Path)
    q=sub.add_parser('render');q.add_argument('--tool-dir',type=Path)
    for n in ('bundle','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','renderer-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);a=parser.parse_args()
    if a.action=='profile':
        value=profile(a.tool_dir);result=dict(profile=value,profile_sha256=m.sha(m.encoded(value)))
    elif a.action=='render':result=render(a.bundle,a.sha256,a.renderer_sha256,a.output,a.tool_dir)
    else:result=verify(a.bundle,a.sha256)
    print(m.encoded(result).decode(),end='')


if __name__=='__main__':main()
