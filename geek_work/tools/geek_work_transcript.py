#!/usr/bin/env python3
"""Archive a bounded WebVTT subset and source-bound notes offline; no ASR or media access."""
import argparse
import html
import json
from pathlib import Path
import re

import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops
from knowledge import strict_json

MAX_INPUT = 1024 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
MAX_CUES = 1000
MAX_TIME = 12 * 60 * 60 * 1000
FILES = {'source.vtt', 'map.json', 'cues.json', 'notes.json', 'review.html'}
SCHEMA = 'geek-work-transcript-evidence-1'
TIMESTAMP = r'(?:[0-9]{2}:)?[0-5][0-9]:[0-5][0-9]\.[0-9]{3}'
TIMING = re.compile('(' + TIMESTAMP + r') --> (' + TIMESTAMP + ')')


def millis(value):
    parts = value.split(':')
    seconds, fraction = parts[-1].split('.')
    hours = int(parts[0]) if len(parts) == 3 else 0
    return ((hours * 60 + int(parts[-2])) * 60 + int(seconds)) * 1000 + int(fraction)


def cues(raw):
    m.require(len(raw) <= MAX_INPUT, 'transcript byte limit')
    text = raw.decode('utf-8')
    m.require('\x00' not in text and '\r' not in text.replace('\r\n', ''), 'NUL/bare CR not supported')
    # Offsets always refer to ORIGINAL decoded source, including BOM and CRLF.
    lines, position = [], 0
    for match in re.finditer(r'[^\n]*\n|[^\n]+$', text):
        value = match.group().removesuffix('\n').removesuffix('\r')
        lines.append((position, value)); position += len(match.group())
    m.require(len(lines) >= 2 and lines[0][1] in ('WEBVTT', '\ufeffWEBVTT') and lines[1][1] == '',
              'WEBVTT header and blank separator required; header metadata not supported')
    result, i, previous = [], 2, -1
    while i < len(lines):
        if lines[i][1] == '':
            i += 1
            continue
        first = i
        while i < len(lines) and lines[i][1] != '':
            i += 1
        block = lines[first:i]
        label = None
        if not TIMING.fullmatch(block[0][1]):
            label = block[0][1]
            m.require(not label.startswith(('NOTE', 'STYLE', 'REGION')) and '-->' not in label,
                      'unsupported metadata or timing syntax')
            k.text(label)
            block = block[1:]
        m.require(len(block) >= 2, 'cue needs timing and text')
        timing = TIMING.fullmatch(block[0][1])
        m.require(timing is not None, 'strict timestamp syntax required; cue settings unsupported')
        start, end = map(millis, timing.groups())
        m.require(0 <= start < end <= MAX_TIME and start >= previous, 'invalid or unsorted cue times')
        previous = start
        left, right = block[1][0], block[-1][0] + len(block[-1][1])
        payload = text[left:right]
        k.text(payload)
        m.require('-->' not in payload, 'missing cue separator or unsupported arrow in payload')
        result.append(dict(id=f'cue-{len(result)+1:04d}', label=label, start_ms=start, end_ms=end,
                           source_start=left, source_end=right, text=payload))
        m.require(len(result) <= MAX_CUES, 'cue count limit')
    m.require(bool(result), 'at least one cue required')
    return result


def artifacts(raw, mapping):
    k.obj(mapping, 'schema source_sha256 title origin notes')
    m.require(mapping['schema'] == 'geek-work-transcript-map-1', 'map schema')
    k.digest(mapping['source_sha256']); k.text(mapping['title'])
    m.require(m.sha(raw) == mapping['source_sha256'], 'transcript anchor mismatch')
    origin = mapping['origin']
    k.obj(origin, 'provider_label media_reference language transcription_method')
    for key in ('provider_label', 'media_reference', 'language'):
        k.text(origin[key])
    m.require(type(origin['transcription_method']) is str and origin['transcription_method'] in
              ('asr_reported', 'human_reported', 'unknown'), 'reported transcription method required')
    rows = cues(raw); by_id = {row['id']: row for row in rows}
    texts = {key: row['text'] for key, row in by_id.items()}
    notes, seen = [], set()
    for note in k.rows(mapping['notes'], 128):
        k.obj(note, 'id text citations'); k.ident(note['id']); k.text(note['text'])
        m.require(note['id'] not in seen, 'duplicate note id'); seen.add(note['id'])
        citations = []
        for citation in k.rows(note['citations'], 16, 1):
            k.span(citation, texts, 'cue')
            cue = by_id[citation['cue']]
            citations.append(dict(**citation, cue_start_ms=cue['start_ms'], cue_end_ms=cue['end_ms'],
                                  source_start=cue['source_start'] + citation['start'],
                                  source_end=cue['source_start'] + citation['end']))
        notes.append(dict(id=note['id'], text=note['text'], citations=citations,
                          semantic_support_verified=False))
    flags = dict(origin_verified=False, media_alignment_verified=False, transcription_accuracy_verified=False,
                 semantic_support_verified=False, publication_authorized=False)
    report = dict(schema=SCHEMA, source_sha256=m.sha(raw), notes=notes, **flags)
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Transcript evidence review</title><style>body{font:16px system-ui;max-width:1050px;margin:2em auto;padding:1em;line-height:1.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1em}article{border-top:1px solid #ccc;margin-top:2em}a{color:#145b87}</style>
<h1>Transcript evidence review</h1><p>Exact text bindings only. Times and origin are reported; audio/video alignment, ASR accuracy and note meaning are not verified. Markup is shown literally. No media is loaded.</p>'''
    esc = html.escape
    page += '<h2>' + esc(mapping['title']) + '</h2><pre>' + esc(m.encoded(origin).decode()) + '</pre>'
    page += '<p><a href="source.vtt">Original transcript bytes</a> · <a href="map.json">Input map</a></p><h2>Derived notes</h2>'
    if not notes:
        page += '<p>No notes supplied.</p>'
    for note in notes:
        page += '<article><h3>' + esc(note['id']) + '</h3><pre>' + esc(note['text']) + '</pre>'
        for c in note['citations']:
            page += ('<p><a href="#' + c['cue'] + '">' + c['cue'] + ' · ' + str(c['cue_start_ms']) +
                     '–' + str(c['cue_end_ms']) + ' ms (whole cue)</a></p><pre>' + esc(c['quote']) + '</pre>')
        page += '</article>'
    page += '<h2>Complete supplied transcript</h2>'
    for row in rows:
        page += ('<article id="' + row['id'] + '"><h3>' + row['id'] + ' · ' + str(row['start_ms']) +
                 '–' + str(row['end_ms']) + ' ms</h3><pre>' + esc(row['text']) + '</pre></article>')
    page += '</html>\n'
    data = {'source.vtt': raw, 'map.json': m.encoded(mapping), 'cues.json': m.encoded(rows),
            'notes.json': m.encoded(report), 'review.html': page.encode()}
    m.require(all(len(value) <= MAX_OUTPUT for value in data.values()), 'artifact byte limit')
    return data, flags


def prepare(source, mapping_path, expected_sha256, output):
    source, mapping_path, output = map(Path, (source, mapping_path, output))
    k.digest(expected_sha256); ops.outside(output, source, mapping_path)
    raw = m.read(source, MAX_INPUT)
    m.require(m.sha(raw) == expected_sha256, 'expected transcript SHA mismatch')
    map_raw = m.read(mapping_path, MAX_INPUT)
    data, flags = artifacts(raw, strict_json(map_raw))
    # Keep the exact original mapping bytes too; replay validates its meaning.
    data['map.json'] = map_raw
    manifest = m.encoded(dict(schema=SCHEMA, files={n: m.sha(b) for n, b in data.items()}, **flags))
    tree.write_tree(output, {**data, 'manifest.json': manifest})
    return dict(status='transcript_evidence_ready', manifest_sha256=m.sha(manifest), **flags)


def verify(bundle, anchor):
    bundle = Path(bundle); k.digest(anchor)
    tree.exact_tree(bundle, FILES | {'manifest.json'})
    encoded = m.read(bundle / 'manifest.json', 16384)
    m.require(m.sha(encoded) == anchor, 'manifest anchor mismatch')
    data = {n: m.read(bundle / n, MAX_INPUT if n in ('source.vtt', 'map.json') else MAX_OUTPUT) for n in FILES}
    expected, flags = artifacts(data['source.vtt'], strict_json(data['map.json']))
    expected['map.json'] = data['map.json']
    m.require(data == expected, 'artifact reproduction mismatch')
    manifest = m.encoded(dict(schema=SCHEMA, files={n: m.sha(b) for n, b in expected.items()}, **flags))
    m.require(encoded == manifest, 'manifest reproduction mismatch')
    return dict(status='transcript_evidence_reproduced', manifest_sha256=anchor, **flags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--source', type=Path, required=True); p.add_argument('--map', type=Path, required=True)
    p.add_argument('--sha256', required=True); p.add_argument('--output', type=Path, required=True)
    v = commands.add_parser('verify')
    v.add_argument('--bundle', type=Path, required=True); v.add_argument('--sha256', required=True)
    args = parser.parse_args()
    try:
        result = (prepare(args.source, args.map, args.sha256, args.output) if args.command == 'prepare'
                  else verify(args.bundle, args.sha256))
        print(json.dumps(result, ensure_ascii=False)); return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps(dict(status='refused', reason=str(error)), ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
