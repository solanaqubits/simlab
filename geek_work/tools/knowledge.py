#!/usr/bin/env python3
"""Private knowledge cards, read-only pinned export, and reviewable dossiers."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

VERSION = '1.0.0'
SCHEMA = 'digital-brain-knowledge-2.0.0'
MAX_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 2000
MAX_DEPTH = 32
KINDS = {'source','claim','theorem','formula','computation','counterexample','question',
         'idea','project','decision','term','application','correction','critique',
         'design','software','structure','evidence'}
STATUSES = {'unreviewed','hypothesis','needs_definition','unsupported','checked_in_model',
            'conditional_statement','counterexample_in_model','open_obligation','superseded'}
CATEGORIES = {'science','directions','tags','questions','formulas','computations','structure',
              'ideas','projects','critique','refresh','open_questions','corrections',
              'knowledge_graph','software_development','design'}
RELATIONS = {'depends_on','supports','contradicts','corrects','explains','part_of',
             'applies_to','answers','defines','derived_from','related_to'}
FIELDS = {'id','revision','kind','title','text','domains','directions','tags','categories',
          'projects','status','scope','assumptions','provenance','evidence','detail','review'}
DETAIL = {
 'theorem': {'declaration','source_ref','hypotheses','conclusion','proof_outline','not_proved','novelty'},
 'formula': {'expression','symbols','units','domain'},
 'computation': {'inputs','semantics','method','result','reproduction','limits'},
 'decision': {'problem','chosen','alternatives','rationale'},
 'term': {'definition','aliases','units','ambiguities'},
 'application': {'target','required_conditions','mapping','unverified_bridge'},
 'question': {'state','missing','resolution'},
 'correction': {'original','replacement','reason'},
 'critique': {'target_statement','objection','basis'},
 'software': {'requirements','interfaces','implementation_state','tests','limitations'},
 'design': {'components','interfaces','alternatives','constraints'},
 'counterexample': {'inputs','failed_conclusion','remaining_conditions','reproduction'},
}
class Refusal(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Refusal(reason)

def bounded(path):
    require(not path.is_symlink() and path.is_file(), 'invalid_input:file')
    with path.open('rb') as f:
        raw = f.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'resource_limit:bytes')
    return raw

def strict_json(raw):
    require(len(raw) <= MAX_BYTES, 'resource_limit:bytes')
    text = raw.decode('utf-8')
    # Bound nesting before json constructs objects. This is not a formal JSON parser proof.
    depth = 0; quoted = False; escape = False
    for c in text:
        if quoted:
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == '"': quoted = False
        elif c == '"': quoted = True
        elif c in '[{':
            depth += 1
            require(depth <= MAX_DEPTH, 'resource_limit:depth')
        elif c in ']}': depth -= 1
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'invalid_input:duplicate_key')
            result[k] = v
        return result
    def integer(s):
        require(len(s) <= 128, 'resource_limit:integer_token')
        return int(s)
    def reject(s):
        raise Refusal('invalid_input:non_integer_number')
    return json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                      parse_float=reject, parse_constant=reject)

def load(path):
    return strict_json(bounded(path))

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def strings(value, nonempty=False):
    return (type(value) is list and (bool(value) or not nonempty)
            and all(type(x) is str and bool(x.strip()) for x in value)
            and len(value) == len(set(value)))

def obj(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'invalid_input:fields')

def textual(value):
    # Structured editorial details contain strings, lists, dictionaries; no implicit bool/int.
    if type(value) is str: return bool(value.strip())
    if type(value) is list: return all(textual(x) for x in value)
    if type(value) is dict: return all(type(k) is str and k and textual(v) for k,v in value.items())
    return False

def card(n):
    obj(n,FIELDS)
    require(type(n['id']) is str and re.fullmatch(r'[a-z][a-z0-9:_-]{1,127}',n['id']), 'invalid_input:id')
    require(type(n['revision']) is int and 1 <= n['revision'] <= 1000000, 'invalid_input:revision')
    require(type(n['kind']) is str and n['kind'] in KINDS, 'invalid_input:kind')
    require(type(n['status']) is str and n['status'] in STATUSES, 'invalid_input:status')
    for k in ('title','text','scope'):
        require(type(n[k]) is str and n[k].strip(), 'invalid_input:text')
    for k in ('domains','directions','tags','categories','projects','assumptions'):
        require(strings(n[k]), 'invalid_input:list')
    require(set(n['categories']) <= CATEGORIES, 'invalid_input:category')
    require(type(n['provenance']) is list and n['provenance'], 'invalid_input:provenance')
    for p in n['provenance']:
        obj(p,{'ref','locator','sha256'})
        require(all(type(v) is str and v for v in p.values()), 'invalid_input:provenance_types')
        require(re.fullmatch(r'[0-9a-f]{64}',p['sha256']), 'invalid_input:sha256')
    obj(n['evidence'],{'formal','computational','empirical'})
    for e in n['evidence'].values():
        obj(e,{'state','refs','limits'})
        require(e['state'] in ('none','reported','checked_here') and type(e['state']) is str, 'invalid_input:evidence')
        require(strings(e['refs']) and type(e['limits']) is str and e['limits'], 'invalid_input:evidence')
        require(e['state']=='none' or bool(e['refs']), 'invalid_input:evidence_reference')
    require(type(n['detail']) is dict and textual(n['detail']), 'invalid_input:detail')
    if n['kind'] in DETAIL:
        obj(n['detail'], DETAIL[n['kind']])
    if n['kind']=='theorem':
        require(n['detail']['novelty']=='not-assessed', 'invalid_input:novelty_requires_separate_review')
    if n['kind']=='question':
        require(n['detail']['state'] in ('open','partial','blocked','resolved'), 'invalid_input:question_state')
        require(n['detail']['state'] != 'resolved' or bool(n['detail']['resolution']), 'invalid_input:resolution')
    obj(n['review'],{'state','as_of','applicability','dependencies'})
    r=n['review']
    require(r['state'] in ('pending','reviewed','needs_review'), 'invalid_input:review_state')
    require(type(r['as_of']) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',r['as_of']), 'invalid_input:review_date')
    try: datetime.date.fromisoformat(r['as_of'])
    except ValueError as exc: raise Refusal('invalid_input:review_date') from exc
    require(type(r['applicability']) is str and r['applicability'], 'invalid_input:applicability')
    require(type(r['dependencies']) is dict and all(type(k) is str and type(v) is int and v>0 for k,v in r['dependencies'].items()), 'invalid_input:dependency_revision')

def validate(g):
    obj(g,{'schema','cards','links','events'})
    require(g['schema']==SCHEMA, 'invalid_input:schema')
    for k in ('cards','links','events'):
        require(type(g[k]) is list, 'invalid_input:lists')
        require(len(g[k]) <= MAX_ITEMS, 'resource_limit:items')
    nodes={}
    for n in g['cards']:
        card(n);require(n['id'] not in nodes,'invalid_input:duplicate_id');nodes[n['id']]=n
    links=set();deps={k:set() for k in nodes}
    for e in g['links']:
        obj(e,{'from','relation','to','scope'})
        require(all(type(x) is str and x for x in e.values()),'invalid_input:link_types')
        require(e['from'] in nodes and e['to'] in nodes and e['relation'] in RELATIONS,'invalid_input:link_reference')
        key=(e['from'],e['relation'],e['to']);require(key not in links,'invalid_input:duplicate_link');links.add(key)
        if e['relation']=='depends_on': deps[e['from']].add(e['to'])
    for i,n in nodes.items():
        require(set(n['review']['dependencies'])==deps[i],'invalid_input:dependency_coverage')
        require(all(v<=nodes[k]['revision'] for k,v in n['review']['dependencies'].items()),'invalid_input:future_revision')
    last={};seen=set()
    for e in g['events']:
        obj(e,{'id','date','reason','before','after'})
        require(type(e['id']) is str and e['id'] and e['id'] not in seen,'invalid_input:event_id');seen.add(e['id'])
        require(type(e['date']) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',e['date']) and type(e['reason']) is str and e['reason'].strip(),'invalid_input:event')
        try: datetime.date.fromisoformat(e['date'])
        except ValueError as exc: raise Refusal('invalid_input:event_date') from exc
        card(e['before']);card(e['after']);a=e['before'];b=e['after'];i=a['id']
        require(i==b['id'] and i in nodes and b['revision']==a['revision']+1,'invalid_input:event_revision')
        require((i not in last and a['revision']==1) or (i in last and last[i]==a),'invalid_input:event_chain');last[i]=b
    for i,n in nodes.items():
        require((i in last and last[i]==n) or (i not in last and n['revision']==1), 'invalid_input:history_missing')
    return {'status':'accepted','cards':len(nodes),'links':len(links),'events':len(g['events']),
            'scope':'structure and declared history; not truth or kernel verification'}

def impact(g, changed):
    validate(g);ids={n['id'] for n in g['cards']}
    require(set(changed)<=ids,'invalid_input:unknown_id')
    reached=set(changed)
    while True:
        nxt=reached|{e['from'] for e in g['links'] if e['relation']=='depends_on' and e['to'] in reached}
        if nxt==reached: break
        reached=nxt
    return sorted(reached-set(changed))

def review(g):
    validate(g);nodes={n['id']:n for n in g['cards']}
    stale={i for i,n in nodes.items() if n['review']['state']=='needs_review' or
           any(nodes[k]['revision']!=r for k,r in n['review']['dependencies'].items())}
    affected=stale|set(impact(g,stale))
    return [{'id':i,'effective_state':'needs_review' if i in affected else n['review']['state'],
             'recorded_state':n['review']['state']} for i,n in sorted(nodes.items())]

def search(g,query='',category=None,tag=None,kind=None):
    validate(g)
    return [n['id'] for n in g['cards'] if (not query or query.casefold() in canonical(n).decode().casefold())
            and (not category or category in n['categories']) and (not tag or tag in n['tags'])
            and (not kind or kind==n['kind'])]

def revise(g,replacement,reason,date):
    validate(g);card(replacement);result=copy.deepcopy(g)
    hits=[i for i,n in enumerate(result['cards']) if n['id']==replacement['id']]
    require(len(hits)==1,'invalid_input:unknown_id');i=hits[0];old=result['cards'][i]
    result['events'].append({'id':'revision:'+replacement['id']+':'+str(replacement['revision']),
        'date':date,'reason':reason,'before':copy.deepcopy(old),'after':copy.deepcopy(replacement)})
    result['cards'][i]=copy.deepcopy(replacement);validate(result);return result

def export_jsonld(g):
    validate(g)
    return {'@context':{'@vocab':'urn:simlab:knowledge:'},'@graph':
        [{'@id':'urn:simlab:knowledge:'+n['id'],**n} for n in g['cards']]+
        [{'@id':'urn:simlab:knowledge:edge:'+str(i),'from':{'@id':'urn:simlab:knowledge:'+e['from']},
          'to':{'@id':'urn:simlab:knowledge:'+e['to']},'relation':e['relation'],'scope':e['scope']} for i,e in enumerate(g['links'])]}

def dossier(g,project):
    validate(g);cards=[n for n in g['cards'] if project in n['projects']]
    require(bool(cards),'invalid_input:unknown_project')
    states={r['id']:r['effective_state'] for r in review(g)}
    lines=['# Private research dossier: '+project,'','Draft only. Novelty, literature review, licensing and publication approval remain separate.',
           'This generated collection is not a paper, a fresh proof audit or a public export.','']
    for n in cards:
        lines += ['## '+n['title'], '',f"ID: {n['id']} / revision {n['revision']} / {n['status']} / review: {states[n['id']]}",
                  '',n['text'],'','Scope: '+n['scope'],'','Assumptions: '+('; '.join(n['assumptions']) or 'See explicit scope.'),'',
                  '```json',json.dumps({'detail':n['detail'],'evidence':n['evidence'],'provenance':n['provenance']},ensure_ascii=False,indent=2),'```','']
    return '\n'.join(lines)

def write_new(path,raw):
    require(len(raw)<=MAX_BYTES,'resource_limit:output_bytes')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f: f.write(raw)

def git_bytes(repo,commit,path):
    require(re.fullmatch(r'[0-9a-f]{40}',commit) is not None,'invalid_input:pinned_commit')
    p=PurePosixPath(path)
    require(not p.is_absolute() and '..' not in p.parts and path==p.as_posix() and not path.startswith('-'), 'invalid_input:source_path')
    require((path.startswith('Verification/') and path.endswith('.lean')) or
            (path.startswith('knowledge/') and path.endswith(('.md','.json'))) or path in ('lean-toolchain','lake-manifest.json'), 'invalid_input:allowlist')
    def git(*args):
        r=subprocess.run(['git','-C',str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
        require(r.returncode==0,'invalid_input:git_object');return r.stdout
    spec=commit+':'+path
    mode=git('ls-tree',commit,'--',path).split()
    require(len(mode)>=3 and mode[0] in (b'100644',b'100755') and mode[1]==b'blob','invalid_input:source_mode')
    size=int(git('cat-file','-s',spec));require(size<=MAX_BYTES,'resource_limit:source_bytes')
    raw=git('cat-file','blob',spec);require(len(raw)==size,'invalid_input:source_size');return raw

def import_lean(repo,commit,paths,output,repository_label='local-git-unverified-origin'):
    require(type(paths) is list and 0<len(paths)<=32 and len(set(paths))==len(paths),'invalid_input:source_list')
    # Read all bounded Git blobs first; never execute Lean, hooks or imported instructions.
    entries=[];payload=[];total=0
    for path in paths:
        raw=git_bytes(repo,commit,path);total+=len(raw)
        require(total<=MAX_BYTES,'resource_limit:bundle_bytes')
        h=digest(raw);local='files/'+h+Path(path).suffix
        entries.append({'repository_label':repository_label,'commit':commit,'path':path,'sha256':h,'bytes':len(raw),'local':local})
        payload.append((local,raw))
    require(not output.exists(),'invalid_input:output_exists');output.mkdir(parents=True)
    for local,raw in payload:
        dest=output/local
        if not dest.exists(): write_new(dest,raw)
    manifest={'schema':'digital-brain-pinned-source-1.0.0','trust':'byte snapshot only; repository label is caller supplied, not authenticated; no proof certification', 'files':entries}
    write_new(output/'manifest.json',canonical(manifest)+b'\n');return manifest

def check_sources(g,root):
    validate(g);root=root.resolve();seen=set()
    for n in g['cards']:
        for p in n['provenance']:
            rel=PurePosixPath(p['ref'])
            require(not rel.is_absolute() and '..' not in rel.parts, 'invalid_input:provenance_path')
            path=root.joinpath(*rel.parts)
            require(path.resolve().is_relative_to(root), 'invalid_input:provenance_escape')
            require(not any(x.is_symlink() for x in [path,*path.parents] if x!=root and x.is_relative_to(root)), 'invalid_input:provenance_symlink')
            require(digest(bounded(path))==p['sha256'],'invalid_witness:source_hash')
            seen.add(p['ref'])
    return {'status':'accepted','source_files':len(seen),'scope':'snapshot bytes, not authorship or truth'}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    for command in ('validate','check-sources','search','review','impact','export-jsonld','dossier','revise'):
        q=s.add_parser(command);q.add_argument('graph',type=Path)
        if command=='check-sources': q.add_argument('--root',type=Path,required=True)
        if command=='search':
            q.add_argument('--query',default='');q.add_argument('--category',choices=sorted(CATEGORIES));q.add_argument('--tag');q.add_argument('--kind',choices=sorted(KINDS))
        if command=='impact': q.add_argument('--changed',action='append',required=True)
        if command in ('export-jsonld','dossier','revise'): q.add_argument('--output',type=Path,required=True)
        if command=='dossier': q.add_argument('--project',required=True)
        if command=='revise':
            q.add_argument('--replacement',type=Path,required=True);q.add_argument('--reason',required=True);q.add_argument('--date',required=True)
    q=s.add_parser('import-lean');q.add_argument('--repository-label',default='local-git-unverified-origin');q.add_argument('--repo',type=Path,required=True);q.add_argument('--commit',required=True);q.add_argument('--path',action='append',required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.command=='import-lean': result=import_lean(a.repo,a.commit,a.path,a.output,a.repository_label)
        else:
            g=load(a.graph);result=validate(g)
            if a.command=='check-sources': result=check_sources(g,a.root)
            elif a.command=='search': result=search(g,a.query,a.category,a.tag,a.kind)
            elif a.command=='review': result=review(g)
            elif a.command=='impact': result={'changed':a.changed,'requires_review':impact(g,a.changed),'truth_statuses_changed':False}
            elif a.command=='dossier': write_new(a.output,dossier(g,a.project).encode())
            elif a.command=='export-jsonld': write_new(a.output,canonical(export_jsonld(g))+b'\n')
            elif a.command=='revise':
                revised=revise(g,load(a.replacement),a.reason,a.date)
                result=validate(revised)
                write_new(a.output,canonical(revised)+b'\n')
        print(json.dumps(result,ensure_ascii=False));return 0
    except (Refusal,UnicodeError,json.JSONDecodeError,OSError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'resource_limit' if str(exc).startswith('resource_limit:') or isinstance(exc,subprocess.TimeoutExpired) else 'rejected','reason':str(exc)},ensure_ascii=False));return 2

if __name__=='__main__': raise SystemExit(main())
