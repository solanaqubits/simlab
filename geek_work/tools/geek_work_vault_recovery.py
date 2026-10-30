#!/usr/bin/env python3
"""Private local recovery snapshot; preserves the full graph and selected source bytes."""
import argparse
from pathlib import Path, PurePosixPath
import knowledge as k
import geek_work_vault as v

MAX_TOTAL=32*1024*1024
MAX_FILES=256


def pins():
    return {Path(p).name:k.digest(Path(p).read_bytes())
            for p in (__file__,v.__file__,v.memory.__file__,k.__file__)}


def source_names(context):
    names=set()
    for row in context['cards']:
        for source in row['source_checks']:
            k.require(source['state']=='matched','selected_source_unavailable')
            names.add(str(PurePosixPath(source['ref'])))
    return names


def snapshot(graph,source_root,vault,vault_anchor,output):
    v.verify(vault,vault_anchor,graph,source_root)
    seal=k.load(vault/'seal.json')
    context=v.memory.retrieve(graph,source_root,seal['request'])
    data={'graph.json':k.canonical(graph)+b'\n'}
    projection=v.expected(vault,vault_anchor,graph,source_root)
    for name in [*projection,'seal.json']:
        data['vault/'+name]=v.read_file(vault,name)
    names=source_names(context)
    k.require(len(data)+len(names)<=MAX_FILES,'snapshot_file_limit')
    for name in sorted(names):
        data['sources/'+name]=k.bounded(source_root/name)
        k.require(sum(map(len,data.values()))<=MAX_TOTAL,'snapshot_byte_limit')
    k.require(sum(map(len,data.values()))<=MAX_TOTAL,'snapshot_byte_limit')
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in data.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);k.write_new(path,raw)
    recovery=dict(schema='geek-work-vault-recovery-1',graph_sha256=v.digest(graph),
                  vault_anchor=vault_anchor,tool_pins=pins(),private_snapshot=True,
                  files={name:k.digest(raw) for name,raw in data.items()})
    # Written last; incomplete snapshots have no recovery seal.
    k.write_new(output/'seal.json',k.canonical(recovery)+b'\n')
    return dict(status='snapshot_created',snapshot_sha256=v.digest(recovery),
                files=len(data),bytes=sum(map(len,data.values())),private_snapshot=True,
                full_graph_included=True,selected_source_files=len(names),ui_configuration_included=False)


def verify(root,anchor):
    v.memory.sha(anchor)
    k.require(root.is_dir() and not root.is_symlink(),'snapshot_directory')
    seal=k.load(root/'seal.json');k.require(v.digest(seal)==anchor,'snapshot_anchor')
    k.obj(seal,{'schema','graph_sha256','vault_anchor','tool_pins','private_snapshot','files'})
    k.require(seal['schema']=='geek-work-vault-recovery-1' and seal['private_snapshot'] is True,'snapshot_schema')
    k.require(seal['tool_pins']==pins(),'snapshot_tools')
    k.require(type(seal['files']) is dict and 0<len(seal['files'])<=MAX_FILES,'snapshot_file_limit')
    for name in seal['files']:
        path=PurePosixPath(name)
        k.require(type(name) is str and not path.is_absolute() and '..' not in path.parts
                  and str(path)==name and name!='seal.json','snapshot_path')
    actual=set();total=0
    for path in root.rglob('*'):
        k.require(not path.is_symlink(),'snapshot_symlink')
        if path.is_file() and path!=root/'seal.json':actual.add(str(path.relative_to(root)))
        k.require(len(actual)<=MAX_FILES,'snapshot_file_limit')
    k.require(actual==set(seal['files']),'snapshot_file_set')
    for name,sha in seal['files'].items():
        raw=v.read_file(root,name);total+=len(raw)
        k.require(total<=MAX_TOTAL,'snapshot_byte_limit')
        k.require(k.digest(raw)==sha,'snapshot_file_changed:'+name)
    graph=k.load(root/'graph.json');k.require(v.digest(graph)==seal['graph_sha256'],'snapshot_graph')
    result=v.verify(root/'vault',seal['vault_anchor'],graph,root/'sources')
    vault_seal=k.load(root/'vault/seal.json')
    context=v.memory.retrieve(graph,root/'sources',vault_seal['request'])
    sources=source_names(context)
    expected={'graph.json','vault/seal.json'} | {'vault/'+n for n in v.expected(root/'vault',seal['vault_anchor'],graph,root/'sources')} | {'sources/'+n for n in sources}
    k.require(actual==expected,'snapshot_scope')
    return dict(status='verified_recovery',snapshot_sha256=anchor,cards=result['cards'],
                full_graph_included=True,selected_source_files=len(sources),
                full_provenance_checked=False,scientific_verification=False,
                ui_configuration_included=False,off_device_backup=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['snapshot','verify']);p.add_argument('--graph',type=Path)
    p.add_argument('--root',type=Path);p.add_argument('--vault',type=Path);p.add_argument('--vault-anchor')
    p.add_argument('--output',type=Path);p.add_argument('--snapshot',type=Path);p.add_argument('--anchor')
    a=p.parse_args()
    try:
        if a.action=='snapshot':
            k.require(all(x is not None for x in [a.graph,a.root,a.vault,a.vault_anchor,a.output]),'snapshot_arguments')
            result=snapshot(k.load(a.graph),a.root,a.vault,a.vault_anchor,a.output)
        else:
            k.require(a.snapshot is not None and a.anchor is not None,'verify_arguments')
            result=verify(a.snapshot,a.anchor)
        print(k.canonical(result).decode())
    except (k.Refusal,OSError,ValueError,TypeError,KeyError) as error:
        print(k.canonical(dict(status='refused',reason=str(error))).decode());return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
