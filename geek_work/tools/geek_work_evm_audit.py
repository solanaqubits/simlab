#!/usr/bin/env python3
"""Export a source-only EVM audit packet from pinned Git blobs; verify its seal."""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import subprocess

PREFIX = 'digital-brain/experiments/zk-gnark-pilot/'
SOURCE_NAMES = (
    'main.go', 'bound.go', 'evm.go', 'application.go',
    'main_test.go', 'bound_test.go', 'evm_test.go', 'application_test.go',
    'go.mod', 'go.sum', 'run-evm.sh',
    'evm/BoundProofApplication.sol', 'evm/application.mjs', 'evm/check.mjs',
    'evm/package.json', 'evm/package-lock.json', 'evm/APPLICATION.ru.md',
)
REVIEW_PATH = 'digital-brain/research/zk-stack/evm-audit/REVIEW.md'
FILES = {'packet.json', 'REVIEW.md', 'RESPONSE.template.json'}
MAX_BYTES = 4 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_regular(path):
    try:
        fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ValueError("cannot open regular input") from error
    with os.fdopen(fd, 'rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), 'regular file required')
        require(info.st_size <= MAX_BYTES, 'file exceeds byte limit')
        raw=stream.read(MAX_BYTES+1)
        require(len(raw) <= MAX_BYTES, 'file exceeds byte limit')
        return raw


def strict_json(raw):
    def pairs(items):
        obj={}
        for key,value in items:
            require(key not in obj, 'duplicate JSON key')
            obj[key]=value
        return obj
    def constant(value):
        raise ValueError('non-finite JSON number')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def git_blob(repo, commit, path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], timeout=30)
    entry = git('ls-tree', commit, '--', path).decode().strip()
    require(bool(entry), 'missing pinned source: '+path)
    meta, name = entry.split('\t')
    mode, kind, oid = meta.split()
    require(name == path and mode in ('100644', '100755') and kind == 'blob',
            'source must be a regular Git blob: '+path)
    require(int(git('cat-file', '-s', oid)) <= MAX_BYTES, 'source exceeds byte limit')
    return git('cat-file', 'blob', oid)


def export(repo, commit, output):
    require(bool(re.fullmatch('[0-9a-f]{40}', commit)), 'full commit SHA required')
    resolved = subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', '--verify', commit+'^{commit}'], timeout=30).decode().strip()
    require(resolved == commit, 'expected commit object')
    sources = []
    for name in SOURCE_NAMES:
        path = PREFIX+name
        raw = git_blob(repo, commit, path)
        sources.append(dict(path=path, sha256=sha(raw), text=raw.decode('utf-8')))
    review = git_blob(repo, commit, REVIEW_PATH)
    packet = dict(schema='geek-work-evm-audit-source-1', commit=commit,
                  sources=sources, execution_evidence_included=False,
                  dependency_sources_included=False, independent_audit_completed=False,
                  production_ready=False)
    template = dict(schema='geek-work-evm-audit-response-1', packet_sha256=None,
                    reviewer=dict(id=None, prior_exposure=None),
                    integrity_checks=[], findings=[], open_questions=[],
                    overall_assessment=None, independence_verified=False, accepted_as_gold=False)
    artifacts = {'packet.json': encode(packet), 'REVIEW.md': review,
                 'RESPONSE.template.json': encode(template)}
    require(sum(map(len, artifacts.values())) <= MAX_BYTES, 'packet exceeds byte limit')
    manifest = encode(dict(schema='geek-work-evm-audit-manifest-1',
                           files={k:sha(v) for k,v in artifacts.items()}))
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in artifacts.items():
        with (output/name).open('xb') as stream:
            stream.write(raw)
    # Completion marker written last. A partial directory must not verify.
    with (output/'MANIFEST.json').open('xb') as stream:
        stream.write(manifest)
    return dict(manifest_sha256=sha(manifest), packet_sha256=sha(artifacts['packet.json']),
                commit=commit, sources=len(sources), independent_audit_completed=False)


def verified_snapshot(directory, anchor):
    require(bool(re.fullmatch('[0-9a-f]{64}', anchor)), 'external manifest SHA required')
    require(not directory.is_symlink() and directory.is_dir(), 'regular directory required')
    require({p.name for p in directory.iterdir()} == FILES | {'MANIFEST.json'}, 'packet file set mismatch')
    files={name:read_regular(directory/name) for name in FILES | {'MANIFEST.json'}}
    def read(name):return files[name]
    raw=read('MANIFEST.json')
    require(sha(raw)==anchor, 'manifest anchor mismatch')
    manifest=strict_json(raw)
    require(manifest.get('schema')=='geek-work-evm-audit-manifest-1', 'manifest schema')
    require(set(manifest['files'])==FILES, 'manifest file set')
    for name in FILES:
        require(sha(read(name))==manifest['files'][name], 'file hash mismatch: '+name)
    packet=strict_json(read('packet.json'))
    require(packet['schema']=='geek-work-evm-audit-source-1', 'packet schema')
    require(bool(re.fullmatch('[0-9a-f]{40}',packet['commit'])), 'packet commit')
    require([s['path'] for s in packet['sources']]==[PREFIX+n for n in SOURCE_NAMES], 'source allowlist')
    for source in packet['sources']:
        require(sha(source['text'].encode())==source['sha256'], 'source hash mismatch')
    for field in ('execution_evidence_included','dependency_sources_included',
                  'independent_audit_completed','production_ready'):
        require(packet[field] is False, 'unsupported evidence claim')
    return files,packet


def verify(directory, anchor):
    _,packet=verified_snapshot(directory,anchor)
    return dict(status='integrity_verified', commit=packet['commit'],
                sources=len(packet['sources']), source_repository_checked=False,
                independent_audit_completed=False)


def fields(obj, names, context):
    require(type(obj) is dict and set(obj)==set(names.split()), context+' fields')


def text(value, context):
    require(type(value) is str and bool(value.strip()) and len(value)<=100_000,
            context+' must be nonempty text')


def validate_response(packet, packet_hash, response):
    fields(response,'schema packet_sha256 reviewer integrity_checks findings open_questions overall_assessment independence_verified accepted_as_gold','response')
    require(response['schema']=='geek-work-evm-audit-response-1','response schema')
    require(response['packet_sha256']==packet_hash,'response packet mismatch')
    require(response['independence_verified'] is False and response['accepted_as_gold'] is False,
            'review cannot promote itself')
    fields(response['reviewer'],'id prior_exposure','reviewer')
    for key in ('id','prior_exposure'):text(response['reviewer'][key],key)
    for key in ('integrity_checks','findings','open_questions'):
        require(type(response[key]) is list and len(response[key])<=256,key+' list limit')
    for check in response['integrity_checks']:
        fields(check,'name status details','integrity check')
        text(check['name'],'check name');text(check['details'],'check details')
        require(check['status'] in ('passed','failed','not_checked'),'check status')
    for question in response['open_questions']:text(question,'open question')
    if response['overall_assessment'] is not None:text(response['overall_assessment'],'assessment')
    sources={s['path']:s['text'] for s in packet['sources']}
    ids=set();citations=0
    for finding in response['findings']:
        fields(finding,'id kind severity summary rationale citations','finding')
        require(type(finding['id']) is str and bool(re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',finding['id'])),'finding id')
        require(finding['id'] not in ids,'duplicate finding id');ids.add(finding['id'])
        require(finding['kind'] in ('defect','question','deployment_requirement'),'finding kind')
        require(finding['severity'] in ('info','low','medium','high','critical'),'finding severity')
        text(finding['summary'],'summary');text(finding['rationale'],'rationale')
        refs=finding['citations']
        require(type(refs) is list and 1<=len(refs)<=32,'finding citation count')
        for ref in refs:
            fields(ref,'path line_start line_end quote','citation')
            require(type(ref['path']) is str and ref['path'] in sources,'citation source')
            start,end=ref['line_start'],ref['line_end']
            lines=sources[ref['path']].split('\n')
            require(type(start) is int and type(end) is int and 1<=start<=end<=len(lines),'citation line range')
            text(ref['quote'],'quote')
            require(ref['quote']=='\n'.join(lines[start-1:end]),'citation quote mismatch')
            citations+=1
            require(citations<=1024,'total citation limit')
    return dict(findings=len(ids),citations=citations,
                reported_failed_checks=sum(c['status']=='failed' for c in response['integrity_checks']),
                reported_unchecked_checks=sum(c['status']=='not_checked' for c in response['integrity_checks']),
                assessment_present=response['overall_assessment'] is not None)


def receive(directory, anchor, response_path, response_anchor, output):
    files,packet=verified_snapshot(directory,anchor)
    require(bool(re.fullmatch('[0-9a-f]{64}',response_anchor)),'external response SHA required')
    raw=read_regular(response_path)
    require(sha(raw)==response_anchor,'response anchor mismatch')
    response=strict_json(raw)
    counts=validate_response(packet,sha(files['packet.json']),response)
    receipt=dict(schema='geek-work-evm-audit-intake-1',status='structure_and_citations_valid',
                 manifest_sha256=anchor,packet_sha256=sha(files['packet.json']),
                 response_sha256=sha(raw),commit=packet['commit'],**counts,
                 findings_verified=False,reviewer_identity_verified=False,
                 independence_verified=False,accepted_as_gold=False,production_ready=False,
                 independent_audit_completed=False,
                 limits='Source references checked; reviewer claims and severity are not adjudicated.')
    output.mkdir(parents=True,exist_ok=False)
    with (output/'response.json').open('xb') as stream:stream.write(raw)
    # Receipt is the completion marker; preserve the exact reviewed bytes.
    with (output/'receipt.json').open('xb') as stream:stream.write(encode(receipt))
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command', required=True)
    p=sub.add_parser('export');p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--commit',required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('verify');p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True)
    p=sub.add_parser('receive');p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--response',type=Path,required=True)
    p.add_argument('--response-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='export':result=export(a.repo,a.commit,a.output)
    elif a.command=='verify':result=verify(a.packet,a.manifest_sha256)
    else:result=receive(a.packet,a.manifest_sha256,a.response,a.response_sha256,a.output)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
