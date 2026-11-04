#!/usr/bin/env python3
"""Build a three-level, source-bound explanation using native offline HTML disclosure controls."""
import argparse
import html
import json
from pathlib import Path

import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as archive
import geek_work_file_operations as ops
import knowledge

LEVELS = ('intuition', 'argument', 'evidence')


def validate(spec):
    k.obj(spec, 'schema id title sources sections non_claims')
    m.require(spec['schema'] == 'geek-work-explainer-1', 'explainer schema')
    k.ident(spec['id']); k.text(spec['title']); k.strings(spec['non_claims'])
    m.require(bool(spec['non_claims']), 'non-claims required')
    refs = {}; paths = set()
    for row in k.rows(spec['sources'], 8, 1):
        k.obj(row, 'id path sha256'); k.ident(row['id']); k.path_name(row['path']); k.digest(row['sha256'])
        m.require(row['id'] not in refs and row['path'].casefold() not in paths, 'duplicate material')
        refs[row['id']] = row; paths.add(row['path'].casefold())
    ids = set()
    for section in k.rows(spec['sections'], 12, 1):
        k.obj(section, 'id title levels'); k.ident(section['id']); k.text(section['title'])
        m.require(section['id'] not in ids, 'duplicate section'); ids.add(section['id'])
        k.obj(section['levels'], ' '.join(LEVELS))
        for level in section['levels'].values():
            k.obj(level, 'text citations'); k.text(level['text']); k.rows(level['citations'], 8, 1)
    return refs


def render(spec, report):
    esc = lambda value: html.escape(str(value), quote=True)
    out = ['''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Source-bound explanation</title>
<style>body{font:17px/1.6 system-ui;max-width:960px;margin:2rem auto;padding:1rem;color:#172c40;background:#fbfcfe;overflow-wrap:anywhere}section{border-top:1px solid #bdcbd8;margin-top:2rem}details{border:1px solid #bdcbd8;border-radius:8px;padding:.7rem 1rem;margin:1rem 0;background:white}summary{cursor:pointer;font-weight:bold}summary:focus-visible,a:focus-visible{outline:3px solid #287abb;outline-offset:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}blockquote{margin:1rem 0;border-left:3px solid #327a89;padding-left:1rem}small{overflow-wrap:anywhere}a{color:#145a91}</style>''',
        '<h1>'+esc(spec['title'])+'</h1>',
        '<p>Редакторское объяснение по закреплённым материалам. Проверены байты и цитаты; смысл объяснения и доказательства заново не проверены.</p>',
        '<nav aria-label="Разделы"><ul>']
    for section in spec['sections']:
        out.append('<li><a href="#section-'+esc(section['id'])+'">'+esc(section['title'])+'</a></li>')
    out.append('</ul></nav>')
    labels = ('1 · Интуиция', '2 · Точный аргумент', '3 · Декларации и свидетельства')
    for section in spec['sections']:
        out.append('<section id="section-'+esc(section['id'])+'"><h2>'+esc(section['title'])+'</h2>')
        for name, label in zip(LEVELS, labels):
            level = section['levels'][name]
            out.append('<details'+(' open' if name == 'intuition' else '')+'><summary>'+label+'</summary><pre>'+esc(level['text'])+'</pre>')
            for c in level['citations']:
                out.append('<blockquote><pre>'+esc(c['quote'])+'</pre><small>'+esc(c['source'])+' · Unicode ['+str(c['start'])+', '+str(c['end'])+')</small></blockquote>')
            out.append('</details>')
        out.append('</section>')
    out.append('<h2>Границы результата</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in spec['non_claims'])+'</ul>')
    out.append('<details><summary>Закреплённые материалы и отчёт проверки</summary><pre>'+esc(json.dumps(dict(materials=spec['sources'],report=report),ensure_ascii=False,indent=2))+'</pre></details></html>\n')
    raw = ''.join(out).replace('<title>Source-bound explanation</title>', '<title>'+esc(spec['title'])+'</title>', 1).encode(); m.require(len(raw) <= k.MAX_FILE, 'HTML size limit'); return raw


def content(raw, blobs):
    spec = knowledge.strict_json(raw); refs = validate(spec)
    m.require(set(blobs) == set(refs) and sum(map(len, blobs.values())) <= 8*1024*1024, 'source set/size')
    texts = {}
    for sid, row in refs.items():
        m.require(m.sha(blobs[sid]) == row['sha256'], 'source hash mismatch'); texts[sid] = k.utf8(blobs[sid])
    used = set(); count = 0
    for section in spec['sections']:
        for level in section['levels'].values():
            for c in level['citations']:
                k.span(c, texts, 'source'); used.add(c['source']); count += 1
    m.require(used == set(refs), 'unused source')
    report = dict(schema='geek-work-explainer-report-1', section_count=len(spec['sections']), citation_count=count,
        source_hashes={sid:row['sha256'] for sid,row in refs.items()}, semantic_correspondence_verified=False,
        pedagogical_quality_verified=False, kernel_replayed=False, scientific_verification=False, publication_authorized=False)
    files = {'spec.json':raw, **{'sources/'+sid+'.txt':b for sid,b in blobs.items()},
             'report.json':m.encoded(report), 'index.html':render(spec, report)}
    m.require(all(len(b) <= k.MAX_FILE for b in files.values()), 'artifact size limit'); return files


def manifest(files):
    return m.encoded(dict(schema='geek-work-explainer-archive-1', files={n:m.sha(b) for n,b in files.items()}))


def build(spec_path, anchor, root, output):
    k.digest(anchor); ops.outside(output, root, spec_path)
    raw = m.read(spec_path); m.require(m.sha(raw) == anchor, 'spec anchor mismatch')
    refs = validate(knowledge.strict_json(raw))
    files = content(raw, {sid:k.read_source(root,row['path']) for sid,row in refs.items()})
    meta = manifest(files); archive.write_tree(output, {**files, 'manifest.json':meta})
    return dict(status='explainer_built', manifest_sha256=m.sha(meta), scientific_verification=False)


def verify(bundle, anchor):
    k.digest(anchor); m.require(bundle.is_dir() and not bundle.is_symlink(), 'regular archive')
    meta = m.read(bundle/'manifest.json'); m.require(m.sha(meta) == anchor, 'archive anchor mismatch')
    raw = m.read(bundle/'spec.json'); refs = validate(knowledge.strict_json(raw))
    files = content(raw, {sid:k.read_source(bundle,'sources/'+sid+'.txt') for sid in refs})
    m.require(meta == manifest(files), 'manifest reproduction mismatch')
    archive.exact_tree(bundle, set(files)|{'manifest.json'})
    for name, data in files.items(): m.require(k.read_source(bundle,name) == data, 'artifact reproduction mismatch')
    return dict(status='explainer_integrity_reproduced', manifest_sha256=anchor, scientific_verification=False)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    b = sub.add_parser('build')
    for flag in ('spec', 'root', 'output'): b.add_argument('--'+flag, type=Path, required=True)
    b.add_argument('--sha256', required=True)
    v = sub.add_parser('verify'); v.add_argument('--bundle', type=Path, required=True); v.add_argument('--sha256', required=True)
    a = p.parse_args()
    try:
        result = build(a.spec,a.sha256,a.root,a.output) if a.action == 'build' else verify(a.bundle,a.sha256)
        print(json.dumps(result)); return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps(dict(status='rejected', reason=str(error)))); return 2


if __name__ == '__main__': raise SystemExit(main())
