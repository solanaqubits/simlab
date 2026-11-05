#!/usr/bin/env python3
"""Bind selected manuscript excerpts to pinned evidence; no semantic adjudication."""
import argparse
from collections import Counter
import html
import os
from pathlib import Path, PurePosixPath
import re
import stat
import geek_work_manuscript as m

MAX_FILE = 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
KINDS = {'lean_source', 'audit_report', 'measurement_report', 'reference_material'}
STATES = {'formal_reported', 'empirical_reported', 'source_only', 'reference_only', 'hypothesis', 'open'}


def obj(value, keys):
    m.require(type(value) is dict and set(value) == set(keys.split()), 'object fields: ' + keys)


def text(value):
    m.require(type(value) is str and bool(value.strip()) and len(value) <= 4000, 'bounded nonempty text required')


def ident(value):
    m.require(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value), 'identifier')


def digest(value, size=64):
    m.require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}', value), 'full hexadecimal digest')


def path_name(value):
    m.require(type(value) is str and 0 < len(value) <= 240, 'relative path required')
    p = PurePosixPath(value)
    m.require(not p.is_absolute() and p.as_posix() == value and
              all(not part.startswith('.') for part in p.parts) and
              not any(ord(c) < 32 or c in '\\:<>"|?*' for c in value), 'safe relative path required')
    return p


def utf8(raw):
    m.require(len(raw) <= MAX_FILE, 'file byte limit')
    value = raw.decode('utf-8')
    m.require('\x00' not in value, 'NUL in text')
    return value


def read_source(root, name):
    parts = path_name(name).parts
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as stream:
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular source required')
            raw = stream.read(MAX_FILE + 1)
            utf8(raw)
            return raw
    except OSError as error:
        raise ValueError('missing or unsafe source: ' + name) from error
    finally:
        if fd is not None:
            os.close(fd)


def rows(value, maximum, minimum=0):
    m.require(type(value) is list and minimum <= len(value) <= maximum, 'list size')
    return value


def strings(value):
    for item in rows(value, 32):
        text(item)


def catalog(mapping):
    obj(mapping, 'schema documents materials claims')
    m.require(mapping['schema'] == 'geek-work-manuscript-claim-map-1', 'map schema')
    for group, maximum, prefix in [('documents', 16, 'document-'), ('materials', 32, 'material-')]:
        seen, paths = set(), set()
        for row in rows(mapping[group], maximum, 1 if group == 'documents' else 0):
            obj(row, 'id path sha256' if group == 'documents' else 'id path sha256 kind origin')
            ident(row['id']); path_name(row['path']); digest(row['sha256'])
            m.require(row['id'] not in seen and row['path'].casefold() not in paths, 'duplicate source id/path')
            seen.add(row['id']); paths.add(row['path'].casefold())
            if group == 'materials':
                m.require(type(row['kind']) is str and row['kind'] in KINDS, 'material kind')
                obj(row['origin'], 'repository commit')
                text(row['origin']['repository']); digest(row['origin']['commit'], 40)
    return {prefix + row['id'] + '.txt': row for group, prefix in [('documents','document-'),('materials','material-')] for row in mapping[group]}


def span(value, texts, key):
    obj(value, key + ' start end quote')
    m.require(type(value[key]) is str and value[key] in texts, 'unknown span source')
    start, end = value['start'], value['end']
    source = texts[value[key]]
    text(value['quote'])
    m.require(type(start) is int and type(end) is int and 0 <= start < end <= len(source), 'span offsets')
    m.require(source[start:end] == value['quote'], 'quote mismatch')


def derive(mapping, blobs):
    files = catalog(mapping)
    m.require(set(blobs) == set(files), 'snapshot source set')
    m.require(sum(map(len, blobs.values())) <= MAX_TOTAL, 'total source byte limit')
    decoded = {}
    for name, row in files.items():
        m.require(m.sha(blobs[name]) == row['sha256'], 'source SHA mismatch: ' + name)
        decoded[name] = utf8(blobs[name])
    docs = {r['id']: decoded['document-' + r['id'] + '.txt'] for r in mapping['documents']}
    materials = {r['id']: decoded['material-' + r['id'] + '.txt'] for r in mapping['materials']}
    kinds = {r['id']: r['kind'] for r in mapping['materials']}
    seen, intervals, used = set(), set(), set()
    for claim in rows(mapping['claims'], 64, 1):
        obj(claim, 'id statement reported_evidence_state scope assumptions non_claims open_obligations evidence')
        ident(claim['id']); m.require(claim['id'] not in seen, 'duplicate claim id'); seen.add(claim['id'])
        span(claim['statement'], docs, 'document')
        s = claim['statement']; interval = (s['document'], s['start'], s['end'])
        m.require(interval not in intervals, 'duplicate statement span'); intervals.add(interval)
        state = claim['reported_evidence_state']; m.require(type(state) is str and state in STATES, 'reported evidence state')
        text(claim['scope'])
        for key in ('assumptions', 'non_claims', 'open_obligations'):
            strings(claim[key])
        m.require(bool(claim['non_claims']), 'explicit non-claims required')
        present = set()
        for evidence in rows(claim['evidence'], 8):
            obj(evidence, 'citation declaration')
            span(evidence['citation'], materials, 'material')
            mid = evidence['citation']['material']; kind = kinds[mid]
            present.add(kind); used.add(mid)
            if kind == 'lean_source':
                text(evidence['declaration'])
                m.require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.\x27]*', evidence['declaration']), 'declaration identifier')
            else:
                m.require(evidence['declaration'] is None, 'declaration only for Lean source')
        required = {'formal_reported': {'lean_source', 'audit_report'},
                    'source_only': {'lean_source'}, 'empirical_reported': {'measurement_report'},
                    'reference_only': {'reference_material'}}.get(state, set())
        m.require(required <= present, 'missing evidence kinds for reported state')
    report = dict(schema='geek-work-manuscript-claim-report-1', status='byte_bindings_verified',
                  claims=len(seen), reported_states=dict(sorted(Counter(c['reported_evidence_state'] for c in mapping['claims']).items())),
                  unused_materials=sorted(set(materials)-used),
                  semantic_correspondence_verified=False, kernel_replayed=False,
                  origin_commits_verified=False, declaration_resolution_verified=False,
                  all_manuscript_claims_covered=False, publication_authorized=False,
                  limits='Selected excerpts and bytes only. States, origins, declaration names, scope and assumptions are supplied editorial metadata. A matching quotation may be a comment, not a theorem. No Git lookup, Lean execution, evidence interpretation, completeness, authenticity or independent review is established.')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'"><title>Manuscript claim map</title><h1>Selected claim/evidence bindings</h1><p>Byte bindings only; reported states are not new verification or semantic approval.</p>'
    def section(title, value):
        return '<h3>' + html.escape(title) + '</h3><pre>' + html.escape(value) + '</pre>'
    for claim in mapping['claims']:
        page += '<article><h2>' + html.escape(claim['id']) + '</h2>'
        for key in ('statement', 'reported_evidence_state', 'scope', 'assumptions', 'non_claims', 'open_obligations', 'evidence'):
            page += section(key, m.encoded(claim[key]).decode())
        page += '</article>'
    page += section('Source identities and declared origins', m.encoded({'documents': mapping['documents'], 'materials': mapping['materials']}).decode())
    page += section('Verification limits', m.encoded(report).decode()) + '</html>\n'
    return {'report.json': m.encoded(report), 'review.html': page.encode()}


def prepare(map_path, map_sha, document_root, material_root, output):
    digest(map_sha)
    raw = m.read(map_path)
    m.require(m.sha(raw) == map_sha, 'map SHA mismatch')
    mapping = m.load(raw); files = catalog(mapping)
    blobs, total = {}, 0
    for name, row in files.items():
        blob = read_source(document_root if name.startswith('document-') else material_root, row['path'])
        total += len(blob); m.require(total <= MAX_TOTAL, 'total source byte limit')
        blobs[name] = blob
    artifacts = {'map.json': raw, **blobs, **derive(mapping, blobs)}
    m.require(sum(map(len, artifacts.values())) <= MAX_TOTAL, 'bundle byte limit')
    manifest = m.encoded(dict(schema='geek-work-manuscript-claim-bundle-1', files={n:m.sha(b) for n,b in artifacts.items()}))
    output.mkdir(parents=True, exist_ok=False)
    for name, blob in artifacts.items():
        with (output/name).open('xb') as stream:
            stream.write(blob)
    with (output/'manifest.json').open('xb') as stream:
        stream.write(manifest)
    return dict(status='byte_bindings_verified', manifest_sha256=m.sha(manifest), claims=len(mapping['claims']), semantic_correspondence_verified=False)


def verify(bundle, anchor):
    digest(anchor)
    m.require(bundle.is_dir() and not bundle.is_symlink(), 'regular bundle directory required')
    raw = m.read(bundle/'manifest.json')
    m.require(m.sha(raw) == anchor, 'manifest anchor mismatch')
    manifest = m.load(raw); obj(manifest, 'schema files')
    m.require(manifest['schema'] == 'geek-work-manuscript-claim-bundle-1' and type(manifest['files']) is dict, 'manifest schema')
    m.require(3 <= len(manifest['files']) <= 51, 'manifest size')
    for name, value in manifest['files'].items():
        m.require(name in {'map.json','report.json','review.html'} or re.fullmatch(r'(document|material)-[a-z0-9][a-z0-9-]{0,63}\.txt', name), 'manifest filename')
        digest(value)
    m.require({p.name for p in bundle.iterdir()} == set(manifest['files']) | {'manifest.json'}, 'bundle file set')
    artifacts, total = {}, 0
    for name, expected in manifest['files'].items():
        blob = m.read(bundle/name, MAX_TOTAL if name in {'review.html','report.json'} else MAX_FILE if name.endswith('.txt') else m.MAX_ARTIFACT)
        total += len(blob); m.require(total <= MAX_TOTAL, 'bundle byte limit')
        m.require(m.sha(blob) == expected, 'artifact hash mismatch')
        artifacts[name] = blob
    m.require({'map.json','report.json','review.html'} <= set(artifacts), 'required bundle files')
    mapping = m.load(artifacts['map.json']); files = catalog(mapping)
    m.require(set(artifacts) == set(files) | {'map.json','report.json','review.html'}, 'mapped file set')
    generated = derive(mapping, {name:artifacts[name] for name in files})
    m.require(all(artifacts[name] == value for name,value in generated.items()), 'recomputed artifact mismatch')
    return dict(status='reproduced', claims=len(mapping['claims']), semantic_correspondence_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--map', type=Path, required=True); p.add_argument('--map-sha256', required=True)
    p.add_argument('--document-root', type=Path, required=True); p.add_argument('--material-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('verify'); p.add_argument('--bundle', type=Path, required=True); p.add_argument('--sha256', required=True)
    a = parser.parse_args()
    result = prepare(a.map, a.map_sha256, a.document_root, a.material_root, a.output) if a.action == 'prepare' else verify(a.bundle, a.sha256)
    print(m.encoded(result).decode(), end='')


if __name__ == '__main__':
    main()
