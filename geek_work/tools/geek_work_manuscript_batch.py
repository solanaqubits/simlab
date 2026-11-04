#!/usr/bin/env python3
"""Stage a single decision for an explicit set of existing manuscript files."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import stat
import geek_work_manuscript as m

MAX_FILES=16
MAX_BUNDLE=16*1024*1024


def selection(names):
    m.require(type(names) is list and 1<=len(names)<=MAX_FILES,'selection size')
    for name in names:
        path=m.document(name)
        m.require(all(not part.startswith('.') for part in path.parts),'hidden path refused')
        m.require(not any(ord(c)<32 or c in ':<>"|?*' for c in name),'portable path required')
    m.require(len({n.casefold() for n in names})==len(names),'duplicate/case-colliding paths')
    for a in names:
        for b in names:
            m.require(a==b or not b.casefold().startswith(a.casefold()+'/'),'file/directory path collision')
    return sorted(names)


def project_file(root,name):
    # Walk every component relative to directory descriptors; no symlink traversal.
    parts=m.document(name).parts
    fd=None
    try:
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(leaf,'rb') as stream:
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),'regular project file required')
            raw=stream.read(m.MAX_SOURCE+1);m.source(raw);return raw
    except OSError as error:
        raise ValueError('missing or unsafe project path: '+name) from error
    finally:
        if fd is not None:os.close(fd)


def index(entries):
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'"><title>Manuscript batch</title><h1>Manuscript batch</h1><p>One decision for all selected files. Unselected files and reference consistency are not checked.</p><ul>'
    for i,row in enumerate(entries):
        page+=f'<li><a href="files/{i:04d}/review.html">'+html.escape(row['document'])+'</a> — '+('changed' if row['changed'] else 'unchanged dependency guard')+'</li>'
    return (page+'</ul></html>\n').encode()


def propose(base,candidate,names,author,reason,output):
    names=selection(names);entries=[];all_data={};total=0
    for i,name in enumerate(names):
        before,after=project_file(base,name),project_file(candidate,name)
        data=m.artifacts(before,after,name,author,reason)
        total+=sum(map(len,data.values()));m.require(total<=MAX_BUNDLE,'bundle byte limit')
        entries.append(dict(document=name,changed=before!=after,files={n:m.sha(b) for n,b in data.items()}))
        all_data[i]=data
    m.require(any(row['changed'] for row in entries),'no changes')
    preview=index(entries)
    manifest=dict(schema='geek-work-manuscript-batch-1',author=author,reason=reason,entries=entries,index_sha256=m.sha(preview),scientific_verification=False)
    output.mkdir(parents=True,exist_ok=False);(output/'files').mkdir()
    for i,data in all_data.items():
        folder=output/'files'/f'{i:04d}';folder.mkdir()
        for name,raw in data.items():
            with (folder/name).open('xb') as f:f.write(raw)
    with (output/'review.html').open('xb') as f:f.write(preview)
    raw=m.encoded(manifest)
    with (output/'manifest.json').open('xb') as f:f.write(raw)
    return dict(status='batch_proposal_ready',files=len(entries),changed=sum(row['changed'] for row in entries),manifest_sha256=m.sha(raw),live_document_modified=False)


def directory(path,expected):
    m.require(path.is_dir() and not path.is_symlink(),'regular bundle directory required')
    remaining=set(expected)
    with os.scandir(path) as entries:
        for entry in entries:
            m.require(entry.name in remaining,'bundle file set')
            remaining.remove(entry.name)
    m.require(not remaining,'bundle file set')


def verified(bundle,anchor):
    m.require(type(anchor) is str and bool(re.fullmatch('[0-9a-f]{64}',anchor)),'full manifest SHA required')
    directory(bundle,{'files','review.html','manifest.json'})
    raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'manifest anchor mismatch');manifest=m.load(raw)
    m.require(type(manifest) is dict and set(manifest)=={'schema','author','reason','entries','index_sha256','scientific_verification'},'manifest fields')
    m.require(manifest['schema']=='geek-work-manuscript-batch-1' and manifest['scientific_verification'] is False,'manifest scope')
    rows=manifest['entries'];m.require(type(rows) is list and 1<=len(rows)<=MAX_FILES,'entries size')
    for row in rows:
        m.require(type(row) is dict and set(row)=={'document','changed','files'} and type(row['changed']) is bool,'entry fields')
        m.require(type(row['files']) is dict and set(row['files'])==m.FILES,'entry file set')
    names=[r['document'] for r in rows];m.require(names==selection(names),'entry ordering')
    directory(bundle/'files',{f'{i:04d}' for i in range(len(rows))})
    data=[];total=0
    for i,row in enumerate(rows):
        folder=bundle/'files'/f'{i:04d}';directory(folder,m.FILES)
        blobs={n:m.read(folder/n) for n in m.FILES};total+=sum(map(len,blobs.values()));m.require(total<=MAX_BUNDLE,'bundle byte limit')
        m.require(all(m.sha(b)==row['files'][n] for n,b in blobs.items()),'artifact hash mismatch')
        m.require(blobs==m.artifacts(blobs['before.txt'],blobs['after.txt'],row['document'],manifest['author'],manifest['reason']),'preview mismatch')
        m.require(row['changed']==(blobs['before.txt']!=blobs['after.txt']),'change flag mismatch');data.append(blobs)
    m.require(any(r['changed'] for r in rows),'no changes')
    preview=m.read(bundle/'review.html');m.require(m.sha(preview)==manifest['index_sha256'] and preview==index(rows),'index mismatch')
    return manifest,data


def decide(bundle,anchor,current,decision,reviewer,output):
    m.require(decision in ('accept','reject'),'batch decision')
    m.require(type(reviewer) is str and bool(reviewer.strip()) and len(reviewer)<=4000,'reviewer required')
    manifest,data=verified(bundle,anchor);rows=manifest['entries']
    # All selected baselines (including unchanged dependencies) checked before any output.
    for row,blobs in zip(rows,data):
        m.require(project_file(current,row['document'])==blobs['before.txt'],'STALE_BASE_REJECTED: '+row['document'])
    results={row['document']:blobs['after.txt' if decision=='accept' else 'before.txt'] for row,blobs in zip(rows,data)}
    receipt=dict(schema='geek-work-manuscript-batch-decision-1',decision=decision,reviewer=reviewer,proposal_sha256=anchor,
                 files={name:m.sha(raw) for name,raw in results.items()},selected_files=len(rows),
                 live_document_modified=False,scientific_verification=False,reference_consistency_checked=False,reviewer_identity_verified=False,
                 limits='Per-file point-in-time checks; explicit selected subset only; no atomic live-project snapshot or write-back.')
    output.mkdir(parents=True,exist_ok=False);(output/'result').mkdir()
    for name,raw in results.items():
        path=output/'result'/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(raw)
    with (output/'receipt.json').open('xb') as f:f.write(m.encoded(receipt))
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('propose');q.add_argument('--base-root',type=Path,required=True);q.add_argument('--candidate-root',type=Path,required=True)
    q.add_argument('--selection',type=Path,required=True);q.add_argument('--author',required=True);q.add_argument('--reason',required=True);q.add_argument('--output',type=Path,required=True)
    q=s.add_parser('decide');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True);q.add_argument('--current-root',type=Path,required=True)
    q.add_argument('--decision',choices=['accept','reject'],required=True);q.add_argument('--reviewer',required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=propose(a.base_root,a.candidate_root,m.load(m.read(a.selection)),a.author,a.reason,a.output) if a.action=='propose' else decide(a.bundle,a.sha256,a.current_root,a.decision,a.reviewer,a.output)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
