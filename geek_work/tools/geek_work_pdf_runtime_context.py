#!/usr/bin/env python3
"""Prepare/verify an offline pinned Poppler container build context; no execution."""
import argparse
from pathlib import Path
import re
import geek_work_typst_preflight as pre

m=pre.m;k=pre.k;tree=pre.tree
RUNTIME=Path(__file__).resolve().parents[1]/'runtime/pdf-renderer'
LOCK_SHA='7f5d863799ed395487437713dc421e958ce7a8b8020cf0cfe8f4bf268c2347b6'
BOOTSTRAP_SHA='9496f94a8b78c536573c93d946ec9bba74bd9ff79ee55aaa4b546e30db8f511b'
BASE='python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337'
MAX_PACKAGE=128*1024*1024
MAX_TOTAL=512*1024*1024


def inputs(cache,bootstrap):
    lock=m.read(RUNTIME/'poppler-25.12.0-linux-64.lock.json');m.require(m.sha(lock)==LOCK_SHA,'distribution lock changed')
    spec=m.load(lock);m.require(spec['platform']=='linux-64' and spec['selected_version']=='25.12.0','runtime lock profile')
    binary=m.read(bootstrap,32*1024*1024);m.require(m.sha(binary)==BOOTSTRAP_SHA,'micromamba SHA mismatch')
    files={'micromamba':binary,'package-lock.json':lock};total=len(binary)+len(lock);names=set()
    for row in spec['packages']:
        name=row['url'].rsplit('/',1)[-1];m.require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+\.(conda|tar\.bz2)',name)) and name not in names,'package archive name');names.add(name)
        raw=m.read(cache/name,MAX_PACKAGE);m.require(m.sha(raw)==row['sha256'],'package SHA mismatch: '+name)
        total+=len(raw);m.require(total<=MAX_TOTAL,'runtime context byte limit');files['packages/'+name]=raw
    for name in ('Dockerfile','worker.py'):files[name]=m.read(RUNTIME/'container'/name)
    report=dict(schema='geek-work-pdf-runtime-context-report-1',status='offline_runtime_context_prepared',base_image=BASE,platform='linux/amd64',packages=len(names),distribution_lock_sha256=LOCK_SHA,micromamba_sha256=BOOTSTRAP_SHA,
                image_built=False,pdf_processed=False,build_attestation=False,parser_isolation_qualified=False,publication_authorized=False,
                limits='Exact local distribution archives and bootstrap only. No downloads, extraction, Docker calls or build. Archive SHA pins are not upstream build attestation. Docker/host/kernel trust and actual build/run isolation are separate obligations.')
    files['report.json']=m.encoded(report);return report,files


def prepare(cache,bootstrap,output):
    pre.ops.outside(output,cache,bootstrap);m.require(not output.exists() and not output.is_symlink(),'new runtime context required')
    report,files=inputs(cache,bootstrap)
    manifest=m.encoded(dict(schema='geek-work-pdf-runtime-context-manifest-1',files={n:m.sha(raw) for n,raw in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest});return dict(status=report['status'],manifest_sha256=m.sha(manifest),packages=report['packages'],image_built=False)


def verify(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'runtime context anchor mismatch');spec=m.load(raw)
    k.obj(spec,'schema files');m.require(spec['schema']=='geek-work-pdf-runtime-context-manifest-1','runtime context schema')
    report,files=inputs(bundle/'packages',bundle/'micromamba');tree.exact_tree(bundle,set(files)|{'manifest.json'})
    m.require(spec['files']=={n:m.sha(data) for n,data in files.items()},'runtime context hashes')
    for name,data in files.items():m.require(m.read(bundle/name,max(len(data),1))==data,'runtime context reproduction mismatch')
    return dict(status='offline_runtime_context_consistent',manifest_sha256=anchor,packages=report['packages'],image_built=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--cache',type=Path,required=True);p.add_argument('--bootstrap',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('verify');p.add_argument('--bundle',type=Path,required=True);p.add_argument('--sha256',required=True)
    args=parser.parse_args();result=prepare(args.cache,args.bootstrap,args.output) if args.action=='prepare' else verify(args.bundle,args.sha256)
    print(m.encoded(result).decode(),end='')


if __name__=='__main__':main()
