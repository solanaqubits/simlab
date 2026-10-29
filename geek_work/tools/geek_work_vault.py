#!/usr/bin/env python3
"""Deterministic, local Markdown view of selected knowledge; never a write-back authority."""
import argparse
import html
import json
from pathlib import Path
import re

import geek_work_memory as memory
import knowledge as k

MAX_TOTAL = 4 * 1024 * 1024


def digest(value): return k.digest(k.canonical(value))


def pins():
    return {Path(p).name:k.digest(Path(p).read_bytes()) for p in (__file__,memory.__file__,k.__file__)}


def escaped(value):
    # Only trusted generated links remain active; source text is not a link/action template.
    s=html.escape(value,quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+!|~])',r'\\\1',s)


def block(value):
    text=json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)
    fence='`' * max(3, 1+max((len(x) for x in re.findall(r'`+',text)),default=0))
    return fence+'json\n'+text+'\n'+fence+'\n'


def target(cid): return 'Cards/card-'+k.digest(cid.encode())


def link(cid): return '[['+target(cid)+'|'+cid+']]'


def build(graph,root,request):
    context=memory.retrieve(graph,root,request)
    k.require(context['graph_sha256']==request['expected_graph_sha256'],'graph_changed')
    k.require(all('revision_changed' not in row['issues'] for row in context['cards']),'revision_changed')
    rows={row['card']['id']:row for row in context['cards']}
    mapping={cid:target(cid)+'.md' for cid in rows}
    k.require(len(set(mapping.values()))==len(mapping),'filename_collision')
    boundary=[e for e in graph['links'] if (e['from'] in rows)!=(e['to'] in rows)]
    data={'context.json':k.canonical(context)+b'\n','request.json':k.canonical(request)+b'\n',
          'catalog.json':k.canonical(dict(schema='geek-work-vault-catalog-1',graph_sha256=context['graph_sha256'],
                    files=mapping,outside_selection=boundary,write_back_enabled=False))+b'\n'}
    index=['# Digital Brain: selected view','','Generated local view; JSON graph remains authoritative.',
           'Edits here are proposals only. No plugins, model calls or automatic write-back.','',
           'Graph SHA-256: '+context['graph_sha256'],'','## Cards','']
    pending=['# Review queue','','This is a projection of recorded review states, not a new scientific audit.','']
    for cid,row in rows.items():
        c=row['card'];index.append('- '+link(cid)+' — '+escaped(c['title']))
        if row['issues']: pending.append('- '+link(cid)+' — '+escaped(', '.join(row['issues'])))
        outgoing=[e for e in context['links'] if e['from']==cid]
        incoming=[e for e in context['links'] if e['to']==cid]
        lines=['---','card_id: '+json.dumps(cid),'revision: '+str(c['revision']),
               'generated_view: true','---','', '# '+escaped(c['title']),'',
               '## Statement','',escaped(c['text']),'', '## Scope','',escaped(c['scope']),'',
               '## Assumptions','']
        lines += ['- '+escaped(x) for x in c['assumptions']] or ['(none recorded)']
        lines += ['', '## Status and provenance','',block(dict(status=c['status'],review=c['review'],
                   effective_review=row['effective_review'],issues=row['issues'],source_checks=row['source_checks'])),
                  '## Detail','',block(c['detail']),'## Evidence','',block(c['evidence']),
                  '## Taxonomy','',block({key:c[key] for key in ['kind','domains','directions','tags','categories','projects']}),
                  '## Relations in this selection','']
        lines += ['- '+e['relation']+' → '+link(e['to'])+' — '+escaped(e['scope']) for e in outgoing] or ['(none)']
        lines += ['', '## Backlinks in this selection','']
        lines += ['- '+link(e['from'])+' → '+e['relation']+' — '+escaped(e['scope']) for e in incoming] or ['(none)']
        lines += ['', 'Other relations outside this selection are listed in [[Boundary]].','']
        data[mapping[cid]]='\n'.join(lines).encode()
    data['Index.md']=('\n'.join(index)+'\n\n[[Review]] · [[Boundary]]\n').encode()
    data['Review.md']=('\n'.join(pending)+'\n').encode()
    data['Boundary.md']=('# Relations outside the selection\n\nTargets exist in the source graph but are not exported notes. No placeholder notes are invented.\n\n'+block(boundary)).encode()
    k.require(sum(map(len,data.values()))<=MAX_TOTAL,'vault_byte_limit')
    return data


def export(graph,root,request,output):
    data=build(graph,root,request)
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in data.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);k.write_new(path,raw)
    seal=dict(schema='geek-work-vault-seal-1',request=request,graph_sha256=digest(graph),
              tool_pins=pins(),files={name:k.digest(raw) for name,raw in data.items()})
    k.write_new(output/'seal.json',k.canonical(seal)+b'\n')
    return dict(seal_sha256=digest(seal),cards=len(json.loads(data['catalog.json'])['files']),files=len(data),source_changed=False)


def expected(vault,anchor,graph,root):
    k.require(not vault.is_symlink() and vault.is_dir(),'vault_directory')
    seal=k.load(vault/'seal.json');k.require(digest(seal)==anchor,'seal_anchor')
    k.obj(seal,{'schema','request','graph_sha256','tool_pins','files'})
    k.require(seal['schema']=='geek-work-vault-seal-1' and seal['tool_pins']==pins(),'seal_tools')
    k.require(seal['graph_sha256']==digest(graph),'graph_changed')
    data=build(graph,root,seal['request'])
    k.require(seal['files']=={name:k.digest(raw) for name,raw in data.items()},'projection_manifest')
    return data


def read_file(vault,name):
    path=vault/name
    k.require(not any(p.is_symlink() for p in [path,*path.parents] if p!=vault and p.is_relative_to(vault)), 'vault_symlink')
    return k.bounded(path)


def verify(vault,anchor,graph,root):
    data=expected(vault,anchor,graph,root)
    k.require({p.name for p in vault.iterdir()}- {'.obsidian'}=={'Cards','context.json','request.json','catalog.json','Index.md','Review.md','Boundary.md','seal.json'},'vault_file_set')
    k.require(not (vault/'Cards').is_symlink(),'vault_symlink')
    k.require({p.name for p in (vault/'Cards').iterdir()}=={Path(n).name for n in data if n.startswith('Cards/')},'card_file_set')
    for name,raw in data.items():k.require(read_file(vault,name)==raw,'projection_changed:'+name)
    return dict(status='verified_projection',cards=len(json.loads(data['catalog.json'])['files']),
                source_changed=False,scientific_verification=False,
                ui_config_not_audited=(vault/'.obsidian').exists())


def wiki_targets(text):
    # Bounded grammar for our generated notes, not a complete Obsidian parser.
    fence=None; found=[]
    for line in text.splitlines():
        match=re.match(r'^\s*(`{3,}|~{3,})',line)
        if match:
            mark=match.group(1)
            if fence is None:fence=mark
            elif mark[0]==fence[0] and len(mark)>=len(fence):fence=None
            continue
        if fence is None:
            found.extend(m.group(1).split('|',1)[0] for m in re.finditer(r'(?<!\\)\[\[([^\]\n]+)\]\]',line))
    return found


def lint(vault,anchor,graph,root,planned=None):
    data=expected(vault,anchor,graph,root);planned=[] if planned is None else planned
    k.require(type(planned) is list and len(planned)<=32 and all(type(x) is str and re.fullmatch(r'[A-Za-z0-9/_-]{1,100}',x) and not x.startswith('/') for x in planned),'planned_references')
    k.require(len(set(planned))==len(planned),'duplicate_planned_reference')
    notes={name[:-3] for name in data if name.endswith('.md')};issues=[];changed=[];bytes_read=0
    for name,raw in data.items():
        if not name.endswith('.md'):continue
        path=vault/name
        if not path.exists():issues.append(dict(file=name,kind='missing_note',target=None));continue
        current=read_file(vault,name);bytes_read+=len(current);k.require(bytes_read<=MAX_TOTAL,'vault_byte_limit')
        if current!=raw:changed.append(name)
        for ref in wiki_targets(current.decode('utf-8')):
            if ref not in notes or not (vault/(ref+'.md')).is_file():
                issues.append(dict(file=name,target=ref,kind='planned_reference' if ref in planned else 'unresolved_reference'))
    return dict(schema='geek-work-vault-lint-1',status='needs_review' if issues or changed else 'clean_generated_notes',
                changed_notes=changed,issues=issues,write_back_enabled=False,
                scope='Generated Markdown notes only; not arbitrary plugins, extra files, all Markdown syntax, taxonomy semantics or scientific correctness')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['export','verify','lint']);p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--request',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--vault',type=Path);p.add_argument('--anchor');p.add_argument('--planned',type=Path)
    a=p.parse_args()
    try:
        graph=k.load(a.graph)
        if a.action=='export':
            k.require(a.request is not None and a.output is not None,'export_arguments')
            result=export(graph,a.root,k.load(a.request),a.output)
        else:
            k.require(a.vault is not None and a.anchor is not None,'verify_arguments')
            result=verify(a.vault,a.anchor,graph,a.root) if a.action=='verify' else lint(a.vault,a.anchor,graph,a.root,k.load(a.planned) if a.planned else None)
            if a.output:k.write_new(a.output,k.canonical(result)+b'\n')
        print(k.canonical(result).decode())
    except (k.Refusal,OSError,ValueError,TypeError,KeyError) as e:
        print(k.canonical(dict(status='refused',reason=str(e))).decode());return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
