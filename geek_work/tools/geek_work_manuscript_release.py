#!/usr/bin/env python3
"""Prepare explicitly allowlisted manuscript source packages; never publish them."""
import argparse
from pathlib import Path
import re
import geek_work_operation_git as g

m=g.m;k=g.pre.k;p=g.pre.p;tree=g.pre.tree
MAX_FINDINGS=4096
KEY=re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----')
TEXT_RULES=[('email',re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')),
            ('local_path',re.compile(r'(?:/home/|/Users/|[A-Za-z]:\\Users\\)')),
            ('credential_assignment',re.compile(r'''(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*["']?[A-Za-z0-9_./+\-]{8,}'''))]
PRIVATE_PATH=re.compile(r'(?i)(?:^|[/_.-])(?:private|internal|secret|confidential)(?:[/_.-]|$)')


def selection(raw,git_archive):
    spec=m.load(raw);k.obj(spec,'schema entry files');m.require(spec['schema']=='geek-work-manuscript-release-selection-1','release selection schema')
    m.require(type(spec['files']) is list and 1<=len(spec['files'])<=p.MAX_FILES,'selection size');sources=set();blobs={}
    for row in spec['files']:
        k.obj(row,'source destination sha256');p.path_name(row['source']);p.path_name(row['destination']);k.digest(row['sha256'])
        m.require(row['source'] not in sources and row['destination'] not in blobs,'duplicate selection');sources.add(row['source'])
        name='preflight/sources/'+row['source'];m.require(name in git_archive,'source not in verified final projection');blob=git_archive[name]
        m.require(m.sha(blob)==row['sha256'],'selected source SHA mismatch');blobs[row['destination']]=blob
    config=p.config(dict(schema='geek-work-manuscript-preflight-selection-1',entry=spec['entry'],files=list(blobs)))
    return spec,blobs,p.analyze(config,blobs)


def report(raw,git_anchor,git_archive):
    spec,blobs,lint=selection(raw,git_archive);findings=[]
    def add(code,dest,location,line=None,severity='review'):
        m.require(len(findings)<MAX_FINDINGS,'finding limit')
        findings.append(dict(id=f'f{len(findings)+1:04}',code=code,destination=dest,location=location,line=line,severity=severity))
    for row in spec['files']:
        name=row['destination'];blob=blobs[name]
        for field in ('source','destination'):
            if PRIVATE_PATH.search(row[field]):add('private_path_marker',name,field+'_path')
        if KEY.search(blob):add('private_key_marker',name,'bytes',severity='block')
        if Path(name).suffix not in {'.tex','.bib'}:add('opaque_asset',name,'bytes')
        else:
            text=m.source(blob)
            for number,line in enumerate(text.splitlines(),1):
                for code,pattern in TEXT_RULES:
                    if pattern.search(line):add(code,name,'text',number)
    result=dict(schema='geek-work-manuscript-release-review-1',git_bundle_sha256=git_anchor,selection_sha256=m.sha(raw),entry=spec['entry'],
        files=[dict(**row,bytes=len(blobs[row['destination']])) for row in spec['files']],findings=findings,preflight=lint,
        export_blocked=bool(lint['findings']) or any(x['severity']=='block' for x in findings),privacy_verified=False,
        asset_contents_decoded=False,scientific_verification=False,publication_authorized=False,
        limits='Heuristic markers plus explicit per-file review. No exhaustive secret/PII detection, asset decoding, rights verification, reviewer authentication or publication. Public output contains only selected destination bytes and a minimal hash manifest.')
    return result,blobs


def template(anchor,review):
    return dict(schema='geek-work-manuscript-release-decisions-1',proposal_sha256=anchor,reviewer=None,
        files=[dict(destination=r['destination'],decision=None,reason=None) for r in review['files']],
        findings=[dict(finding_id=r['id'],decision=None,reason=None) for r in review['findings']])


def proposal_files(raw,git_anchor,archive):
    review,blobs=report(raw,git_anchor,archive)
    # The template's proposal pin is supplied only after the manifest exists.
    files={'selection.json':raw,'report.json':m.encoded(review),'decisions.template.json':m.encoded(template(None,review)),
           **{'selected/'+n:x for n,x in blobs.items()},**{'git-bundle/'+n:x for n,x in archive.items()}}
    m.require(len(files['report.json'])<=m.MAX_ARTIFACT,'review report limit');return review,blobs,files


def prepare(bundle,anchor,repo,selection_path,selection_sha,output):
    g.pre.ops.outside(output,bundle,repo);_,archive=g.verified(bundle,anchor,repo)
    k.digest(selection_sha);raw=m.read(selection_path);m.require(m.sha(raw)==selection_sha,'selection anchor mismatch')
    review,_,files=proposal_files(raw,anchor,archive)
    manifest=m.encoded(dict(schema='geek-work-manuscript-release-proposal-1',git_bundle_sha256=anchor,files={n:m.sha(x) for n,x in files.items()}))
    tree.write_tree(output,{**files,'manifest.json':manifest})
    return dict(status='private_review_prepared',manifest_sha256=m.sha(manifest),export_blocked=review['export_blocked'],findings=len(review['findings']),privacy_verified=False)


def verified_proposal(bundle,anchor,repo):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'proposal anchor mismatch');manifest=m.load(raw)
    k.obj(manifest,'schema git_bundle_sha256 files');m.require(manifest['schema']=='geek-work-manuscript-release-proposal-1','proposal schema')
    _,archive=g.verified(bundle/'git-bundle',manifest['git_bundle_sha256'],repo)
    review,blobs,files=proposal_files(m.read(bundle/'selection.json'),manifest['git_bundle_sha256'],archive)
    tree.exact_tree(bundle,set(files)|{'manifest.json'});m.require(manifest['files']=={n:m.sha(x) for n,x in files.items()},'proposal hashes')
    for n,x in files.items():m.require(m.read(bundle/n,max(len(x),1))==x,'proposal reproduction mismatch')
    return review,blobs,{**files,'manifest.json':raw}


def approve(raw,anchor,review):
    spec=m.load(raw);k.obj(spec,'schema proposal_sha256 reviewer files findings')
    m.require(spec['schema']=='geek-work-manuscript-release-decisions-1' and spec['proposal_sha256']==anchor,'decision proposal binding');k.text(spec['reviewer'])
    m.require(not review['export_blocked'],'release blocked: repair sources/selection and prepare again')
    for field,key,expected,choice in [('files','destination',{r['destination'] for r in review['files']},'allow'),('findings','finding_id',{r['id'] for r in review['findings']},'acknowledge')]:
        rows=spec[field];m.require(type(rows) is list and len(rows)==len(expected),'complete decisions required');seen=set()
        for row in rows:
            k.obj(row,key+' decision reason');m.require(type(row[key]) is str and row[key] in expected and row[key] not in seen,'decision identity');seen.add(row[key]);k.text(row['reason'])
            m.require(row['decision']==choice,'explicit approval required for every file and finding')
    return spec


def public_files(entry,blobs):
    manifest=m.encoded(dict(schema='geek-work-manuscript-public-package-1',entry=entry,
        files={n:dict(sha256=m.sha(x),bytes=len(x)) for n,x in sorted(blobs.items())}))
    return {**{'files/'+n:x for n,x in blobs.items()},'manifest.json':manifest}


def audit_files(anchor,decisions,archive,public):
    receipt=m.encoded(dict(schema='geek-work-manuscript-release-record-1',proposal_sha256=anchor,decisions_sha256=m.sha(decisions),
        public_manifest_sha256=m.sha(public['manifest.json']),record_kind='local_export_plan',privacy_verified=False,
        reviewer_identity_verified=False,publication_authorized=False,network_publication_performed=False))
    return {'decisions.json':decisions,'receipt.json':receipt,'public-manifest.json':public['manifest.json'],**{'proposal/'+n:x for n,x in archive.items()}}


def export(bundle,anchor,repo,decisions_path,decisions_sha,public_output,audit_output):
    for output,other in ((public_output,audit_output),(audit_output,public_output)):
        g.pre.ops.outside(output,bundle,repo,other,decisions_path)
        m.require(not output.exists() and not output.is_symlink(),'new output required')
    review,blobs,archive=verified_proposal(bundle,anchor,repo);raw=m.read(decisions_path);k.digest(decisions_sha);m.require(m.sha(raw)==decisions_sha,'decision SHA mismatch');approve(raw,anchor,review)
    public=public_files(review['entry'],blobs);audit=audit_files(anchor,raw,archive,public)
    manifest=m.encoded(dict(schema='geek-work-manuscript-release-audit-1',proposal_sha256=anchor,files={n:m.sha(x) for n,x in audit.items()}))
    # Separate directories are not one atomic transaction; audit alone is only a plan.
    tree.write_tree(audit_output,{**audit,'manifest.json':manifest});tree.write_tree(public_output,public)
    return dict(status='local_package_prepared',public_manifest_sha256=m.sha(public['manifest.json']),audit_manifest_sha256=m.sha(manifest),
        public_location=str(public_output.resolve()),private_audit_location=str(audit_output.resolve()),privacy_verified=False,network_publication_performed=False)


def verified_public(bundle,anchor):
    k.digest(anchor);raw=m.read(bundle/'manifest.json');m.require(m.sha(raw)==anchor,'public anchor mismatch');spec=m.load(raw)
    k.obj(spec,'schema entry files');m.require(spec['schema']=='geek-work-manuscript-public-package-1' and type(spec['files']) is dict,'public schema')
    p.config(dict(schema='geek-work-manuscript-preflight-selection-1',entry=spec['entry'],files=list(spec['files'])))
    tree.exact_tree(bundle,{'manifest.json'}|{'files/'+n for n in spec['files']});total=0
    data={'manifest.json':raw}
    for n,desc in spec['files'].items():
        k.obj(desc,'sha256 bytes');k.digest(desc['sha256']);m.require(type(desc['bytes']) is int and 0<=desc['bytes']<=p.MAX_FILE,'public file size')
        blob=m.read(bundle/'files'/n,p.MAX_FILE);total+=len(blob);m.require(total<=p.MAX_TOTAL,'public total limit')
        m.require(len(blob)==desc['bytes'] and m.sha(blob)==desc['sha256'],'public file mismatch');data['files/'+n]=blob
    return dict(status='public_bytes_consistent',manifest_sha256=anchor,files=len(spec['files']),privacy_verified=False,scientific_verification=False,publication_authorized=False),data


def verify_public(bundle,anchor):
    result,_=verified_public(bundle,anchor)
    return result


def verify_pair(audit,anchor,public,public_anchor,repo):
    k.digest(anchor);raw=m.read(audit/'manifest.json');m.require(m.sha(raw)==anchor,'audit anchor mismatch');spec=m.load(raw)
    k.obj(spec,'schema proposal_sha256 files');m.require(spec['schema']=='geek-work-manuscript-release-audit-1','audit schema')
    review,blobs,archive=verified_proposal(audit/'proposal',spec['proposal_sha256'],repo);decisions=m.read(audit/'decisions.json');approve(decisions,spec['proposal_sha256'],review)
    expected=public_files(review['entry'],blobs);files=audit_files(spec['proposal_sha256'],decisions,archive,expected)
    tree.exact_tree(audit,set(files)|{'manifest.json'});m.require(spec['files']=={n:m.sha(x) for n,x in files.items()},'audit hashes')
    for n,x in files.items():m.require(m.read(audit/n,max(len(x),1))==x,'audit reproduction mismatch')
    m.require(m.sha(expected['manifest.json'])==public_anchor,'public/audit binding');verify_public(public,public_anchor)
    for n,x in expected.items():m.require(m.read(public/n,max(len(x),1))==x,'public projection mismatch')
    return dict(status='local_export_consistent',audit_manifest_sha256=anchor,public_manifest_sha256=public_anchor,privacy_verified=False,reviewer_identity_verified=False,publication_authorized=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare')
    for n in ('bundle','repo','selection','output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','selection-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('export')
    for n in ('bundle','repo','decisions','public-output','audit-output'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','decisions-sha256'):q.add_argument('--'+n,required=True)
    q=sub.add_parser('verify-public');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--sha256',required=True)
    q=sub.add_parser('verify-pair')
    for n in ('audit','public','repo'):q.add_argument('--'+n,type=Path,required=True)
    for n in ('sha256','public-sha256'):q.add_argument('--'+n,required=True)
    a=parser.parse_args()
    if a.action=='prepare':result=prepare(a.bundle,a.sha256,a.repo,a.selection,a.selection_sha256,a.output)
    elif a.action=='export':result=export(a.bundle,a.sha256,a.repo,a.decisions,a.decisions_sha256,a.public_output,a.audit_output)
    elif a.action=='verify-public':result=verify_public(a.bundle,a.sha256)
    else:result=verify_pair(a.audit,a.sha256,a.public,a.public_sha256,a.repo)
    print(m.encoded(result).decode(),end='')


if __name__=='__main__':main()
