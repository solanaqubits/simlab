#!/usr/bin/env python3
"""Bind selected execution series to exact study-node plans without combining ledger costs."""
import argparse
import html
import os
from pathlib import Path
import geek_work_execution_series as series
import geek_work_experiment_tree as study
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

SCHEMA='geek-work-study-executions-1'
MAX_TOTAL=128*1024*1024
MAX_FILES=8192


def snapshot(root,anchor,byte_budget=None,entry_budget=None):
    byte_budget=MAX_TOTAL if byte_budget is None else byte_budget
    entry_budget=MAX_FILES if entry_budget is None else entry_budget
    m.require(type(byte_budget) is int and 0<=byte_budget<=MAX_TOTAL,'snapshot byte budget')
    m.require(type(entry_budget) is int and 0<=entry_budget<=MAX_FILES,'snapshot entry budget')
    m.require(root.is_dir() and not root.is_symlink(),'regular bundle root')
    names=[];dirs=[];pending=[root]
    while pending:
        folder=pending.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                m.require(len(names)+len(dirs)<entry_budget,'snapshot entry limit')
                m.require(not entry.is_symlink(),'no symlink')
                path=folder/entry.name;name=path.relative_to(root).as_posix();k.path_name(name)
                if entry.is_dir(follow_symlinks=False):dirs.append(name);pending.append(path)
                else:
                    m.require(entry.is_file(follow_symlinks=False),'regular snapshot file required');names.append(name)
    files={};total=0
    for name in sorted(names):
        raw=m.read(root/name,min(series.runner.MAX_TOTAL,byte_budget-total));total+=len(raw)
        m.require(total<=byte_budget,'snapshot byte limit');files[name]=raw
    m.require('manifest.json' in files,'snapshot manifest missing')
    m.require(m.sha(files['manifest.json'])==anchor,'snapshot anchor changed')
    meta=knowledge.strict_json(files['manifest.json'])
    m.require({n:m.sha(b) for n,b in files.items() if n!='manifest.json'}==meta['files'],'snapshot changed during capture')
    return files,sorted(dirs)


def derive(tree_path,tree_sha,bindings):
    study.verify(tree_path,tree_sha)
    tree_files,tree_dirs=snapshot(tree_path,tree_sha,entry_budget=MAX_FILES-2);nodes=knowledge.strict_json(tree_files['report.json'])['nodes']
    by_id={n['id']:n for n in nodes};seen_nodes=set();seen_attempts=set();rows=[]
    files={'tree/'+n:b for n,b in tree_files.items()};dirs=['tree','series',*['tree/'+d for d in tree_dirs]];selection=[]
    m.require(1<=len(bindings)<=16,'1–16 node bindings')
    for i,(node_id,path,anchor) in enumerate(bindings):
        k.ident(node_id);m.require(node_id in by_id and node_id not in seen_nodes,'missing or duplicate node binding');seen_nodes.add(node_id)
        remaining_bytes=MAX_TOTAL-sum(map(len,files.values()))
        remaining_entries=MAX_FILES-len(files)-len(dirs)-1
        m.require(remaining_bytes>0 and remaining_entries>0,'combined attachment budget exhausted')
        series.verify(path,anchor)
        blobs,folders=snapshot(path,anchor,byte_budget=remaining_bytes,entry_budget=remaining_entries);report=knowledge.strict_json(blobs['report.json']);node=by_id[node_id]
        m.require(all(g['bindings']['plan_sha256']==node['plan_manifest_sha256'] for g in report['groups']),'execution plan does not match node plan')
        for row in report['attempts']:
            m.require(row['attempt_id'] not in seen_attempts,'execution counted at multiple nodes');seen_attempts.add(row['attempt_id'])
        prefix=f'series/{i:04d}'
        files.update({prefix+'/'+n:b for n,b in blobs.items()});dirs.extend([prefix,*[prefix+'/'+d for d in folders]])
        m.require(sum(map(len,files.values()))<=MAX_TOTAL and len(files)+len(dirs)<=MAX_FILES,'combined attachment bound')
        selection.append(dict(node_id=node_id,series_sha256=anchor))
        rows.append(dict(node_id=node_id,plan_manifest_sha256=node['plan_manifest_sha256'],series_manifest_sha256=anchor,
            attempts=report['attempts'],binding_groups=report['groups'],exact_bindings_match=report['exact_bindings_match'],
            ledger_present=bool(node['reported_attempts']),ledger_execution_overlap='not_assessed',
            plan_byte_binding_checked=True,execution_independently_verified=False,scientific_comparability_verified=False))
    report=dict(schema=SCHEMA,tree_manifest_sha256=tree_sha,nodes=rows,
                nodes_without_execution_binding=[n['id'] for n in nodes if n['id'] not in seen_nodes],
                selected_execution_count=len(seen_attempts),ledger_costs_combined=False,
                global_attempt_completeness_verified=False,scientific_verification=False,
                limits='Only exact plan byte bindings checked. Selected receipts are not global history or execution authentication. Ledger costs and execution times remain separate; overlap is not assessed. No automatic acceptance or budget comparison between internal controls and execution attempts.')
    spec=dict(schema=SCHEMA,tree_sha256=tree_sha,bindings=selection)
    files.update({'selection.json':m.encoded(spec),'report.json':m.encoded(report)})
    files['index.html']=('''<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; form-action 'none'"><title>Study execution bindings</title><h1>Selected study execution bindings</h1><p>Exact plan bindings only. No execution authentication or scientific acceptance. Ledger costs are not added.</p><pre>'''+html.escape(m.encoded(report).decode())+'</pre>').encode()
    m.require(all(len(files[n])<=k.MAX_FILE for n in ('selection.json','report.json','index.html')), 'generated artifact byte limit')
    dirs=sorted(set(dirs+['series']))
    m.require(sum(map(len,files.values()))<=MAX_TOTAL and len(files)+len(dirs)<=MAX_FILES,'attachment bound')
    return files,dirs,report


def manifest(files,dirs):
    raw=m.encoded(dict(schema=SCHEMA,files={n:m.sha(b) for n,b in files.items()},directories=dirs))
    m.require(len(raw)<=m.MAX_ARTIFACT,'manifest byte limit');return raw


def build(tree_path,tree_sha,bindings,output):
    ops.outside(output,tree_path,*[p for _,p,_ in bindings]);files,dirs,report=derive(tree_path,tree_sha,bindings)
    meta=manifest(files,dirs);archive.write_tree(output,{**files,'manifest.json':meta})
    for d in dirs:(output/d).mkdir(parents=True,exist_ok=True)
    return dict(status='bindings_recorded',manifest_sha256=m.sha(meta),selected_execution_count=report['selected_execution_count'])


def verify(bundle,anchor):
    k.digest(anchor);meta=m.read(bundle/'manifest.json');m.require(m.sha(meta)==anchor,'attachment anchor mismatch')
    spec=knowledge.strict_json(k.read_source(bundle,'selection.json'));k.obj(spec,'schema tree_sha256 bindings')
    m.require(spec['schema']==SCHEMA,'attachment schema');k.digest(spec['tree_sha256']);k.rows(spec['bindings'],16,1)
    bindings=[]
    for i,row in enumerate(spec['bindings']):
        k.obj(row,'node_id series_sha256');k.ident(row['node_id']);k.digest(row['series_sha256'])
        bindings.append((row['node_id'],bundle/f'series/{i:04d}',row['series_sha256']))
    files,dirs,report=derive(bundle/'tree',spec['tree_sha256'],bindings)
    m.require(meta==manifest(files,dirs),'attachment reproduction mismatch')
    expected={'.':set(),**{d:set() for d in dirs}}
    for name in [*files,'manifest.json',*dirs]:expected[Path(name).parent.as_posix()].add(Path(name).name)
    for d,children in expected.items():archive.b.directory(bundle/d,children)
    for name in ('selection.json','report.json','index.html'):m.require(k.read_source(bundle,name)==files[name],'attachment artifact mismatch')
    return dict(status='bindings_reproduced',selected_execution_count=report['selected_execution_count'],subprocess_rerun=False,scientific_verification=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('build');q.add_argument('--tree',type=Path,required=True);q.add_argument('--tree-sha256',required=True)
    q.add_argument('--node',action='append',required=True);q.add_argument('--series',type=Path,action='append',required=True);q.add_argument('--series-sha256',action='append',required=True);q.add_argument('--output',type=Path,required=True)
    q=s.add_parser('verify');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    try:
        if a.action=='build':
            m.require(len(a.node)==len(a.series)==len(a.series_sha256),'one node and SHA per series')
            result=build(a.tree,a.tree_sha256,list(zip(a.node,a.series,a.series_sha256)),a.output)
        else:result=verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        print(m.encoded(dict(status='rejected',reason=str(exc))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
