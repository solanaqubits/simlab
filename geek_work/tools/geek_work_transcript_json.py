#!/usr/bin/env python3
"""Convert bounded saved transcript JSON to exact-ms WebVTT offline; retain raw input."""
import argparse
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import geek_work_transcript as t
import geek_work_manuscript as m
import geek_work_manuscript_claims as k
import geek_work_batch_hunks as tree
import geek_work_file_operations as ops
from knowledge import strict_json

SCHEMA = 'geek-work-transcript-json-1'
FORMATS = ('lecture-segments', 'transcriptapi-json')
FILES = {'source.json', 'source.vtt', 'conversion.json'}


def load_numbers(raw):
    """Bound depth/tokens before constructing exact Decimal values; never binary floats."""
    m.require(len(raw) <= t.MAX_INPUT, 'JSON byte limit')
    text = raw.decode('utf-8')
    depth = 0; quoted = False; escape = False
    for char in text:
        if quoted:
            if escape: escape = False
            elif char == '\\': escape = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in '[{':
            depth += 1; m.require(depth <= 32, 'JSON depth limit')
        elif char in ']}': depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            m.require(key not in result, 'duplicate JSON key'); result[key] = value
        return result
    def number(token):
        m.require(len(token) <= 128, 'numeric token limit')
        exponent = token.lower().split('e')
        m.require(len(exponent) == 1 or abs(int(exponent[1])) <= 1000, 'numeric exponent limit')
        value = Decimal(token)
        m.require(value.is_finite() and abs(value.as_tuple().exponent) <= 1000, 'numeric exponent limit')
        return value
    def invalid(token):
        raise ValueError('nonfinite JSON number: ' + token)
    return json.loads(text, object_pairs_hook=pairs, parse_int=number, parse_float=number,
                      parse_constant=invalid)


def seconds(value):
    m.require(type(value) is Decimal, 'time must be a JSON number, not bool/string/null')
    exact = Fraction(value)
    m.require(0 <= exact <= Fraction(t.MAX_TIME, 1000), 'time outside bounded media interval')
    return exact


def milliseconds(exact):
    value = exact * 1000
    m.require(value.denominator == 1, 'sub-millisecond time refused; no implicit rounding')
    return value.numerator


def timestamp(value):
    seconds, ms = divmod(value, 1000)
    minutes, sec = divmod(seconds, 60); hours, minute = divmod(minutes, 60)
    return f'{hours:02d}:{minute:02d}:{sec:02d}.{ms:03d}'


def artifacts(raw, source_format):
    m.require(type(source_format) is str and source_format in FORMATS, 'explicit supported source format required')
    obj = load_numbers(raw)
    if source_format == 'lecture-segments':
        rows, prefix = obj, ''
    else:
        m.require(type(obj) is dict and 'transcript' in obj, 'transcriptapi envelope required')
        rows, prefix = obj['transcript'], '/transcript'
    k.rows(rows, t.MAX_CUES, 1)
    segments, previous = [], -1
    for i, row in enumerate(rows):
        required = {'start', 'end', 'text'} if source_format == 'lecture-segments' else {'start', 'duration', 'text'}
        m.require(type(row) is dict and required <= set(row), 'required segment fields missing')
        start = seconds(row['start'])
        if source_format == 'lecture-segments':
            end = seconds(row['end'])
        else:
            duration = seconds(row['duration'])
            # Require duration itself to be exact milliseconds, not just the sum.
            milliseconds(duration); end = start + duration
        left, right = milliseconds(start), milliseconds(end)
        m.require(previous <= left < right <= t.MAX_TIME, 'unsorted, empty or invalid segment interval')
        previous = left; k.text(row['text'])
        segments.append(dict(cue=f'cue-{i+1:04d}', source_pointer=f'{prefix}/{i}',
                             start_ms=left, end_ms=right, text=row['text'],
                             uninterpreted_keys=sorted(set(row)-required)))
    vtt = ('WEBVTT\n\n' + '\n\n'.join(timestamp(s['start_ms']) + ' --> ' + timestamp(s['end_ms']) +
                                      '\n' + s['text'] for s in segments) + '\n').encode('utf-8')
    # Reuse the existing bounded reader and prove exact payload/time equality.
    # Unsupported text layouts fail rather than being stripped, escaped or split.
    cues = t.cues(vtt)
    m.require(len(cues) == len(segments), 'cue count changed during conversion')
    for cue, segment in zip(cues, segments):
        m.require((cue['id'], cue['start_ms'], cue['end_ms'], cue['text']) ==
                  (segment['cue'], segment['start_ms'], segment['end_ms'], segment['text']),
                  'cue text/timing changed during conversion')
    conversion = dict(schema=SCHEMA, source_format=source_format, source_sha256=m.sha(raw),
        vtt_sha256=m.sha(vtt), numeric_policy='exact_decimal_to_integer_ms_or_refuse',
        segments=segments, raw_metadata_preserved_in='source.json',
        uninterpreted_envelope_keys=sorted(set(obj)-{'transcript'}) if type(obj) is dict else [],
        origin_verified=False, media_alignment_verified=False, transcription_accuracy_verified=False,
        semantic_support_verified=False, publication_authorized=False)
    data = {'source.json': raw, 'source.vtt': vtt, 'conversion.json': m.encoded(conversion)}
    m.require(all(len(value) <= t.MAX_OUTPUT for value in data.values()), 'artifact byte limit')
    return data


def manifest(data, source_format):
    return m.encoded(dict(schema=SCHEMA, source_format=source_format,
                          files={name: m.sha(raw) for name, raw in data.items()}))


def prepare(source, expected_sha256, source_format, output):
    source, output = Path(source), Path(output)
    k.digest(expected_sha256); ops.outside(output, source)
    raw = m.read(source, t.MAX_INPUT)
    m.require(m.sha(raw) == expected_sha256, 'source anchor mismatch')
    data = artifacts(raw, source_format); encoded = manifest(data, source_format)
    tree.write_tree(output, {**data, 'manifest.json': encoded})
    return dict(status='transcript_json_converted', manifest_sha256=m.sha(encoded),
                vtt_sha256=m.sha(data['source.vtt']), source_modified=False, origin_verified=False)


def verify(bundle, anchor):
    bundle = Path(bundle); k.digest(anchor)
    tree.exact_tree(bundle, FILES | {'manifest.json'})
    encoded = m.read(bundle/'manifest.json', 16384)
    m.require(m.sha(encoded) == anchor, 'manifest anchor mismatch')
    spec = strict_json(encoded); k.obj(spec, 'schema source_format files')
    m.require(spec['schema'] == SCHEMA, 'manifest schema')
    raw = m.read(bundle/'source.json', t.MAX_INPUT)
    data = artifacts(raw, spec['source_format'])
    for name, expected in data.items():
        m.require(m.read(bundle/name, t.MAX_OUTPUT) == expected, 'conversion reproduction mismatch')
    m.require(encoded == manifest(data, spec['source_format']), 'manifest reproduction mismatch')
    return dict(status='transcript_json_reproduced', manifest_sha256=anchor,
                vtt_sha256=m.sha(data['source.vtt']), origin_verified=False,
                media_alignment_verified=False, transcription_accuracy_verified=False)


def verify_review(bundle, anchor, review, review_anchor):
    converted = verify(bundle, anchor)
    t.verify(review, review_anchor)
    observed = m.read(Path(review)/'source.vtt', t.MAX_INPUT)
    m.require(m.sha(observed) == converted['vtt_sha256'], 'review uses a different converted transcript')
    return dict(status='transcript_json_review_link_reproduced', conversion_sha256=anchor,
                review_sha256=review_anchor, vtt_sha256=converted['vtt_sha256'],
                origin_verified=False, media_alignment_verified=False, semantic_support_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--sha256', required=True); p.add_argument('--format', choices=FORMATS, required=True)
    p.add_argument('--output', type=Path, required=True)
    v = commands.add_parser('verify'); v.add_argument('--bundle', type=Path, required=True)
    v.add_argument('--sha256', required=True)
    linked = commands.add_parser('verify-review')
    linked.add_argument('--bundle', type=Path, required=True); linked.add_argument('--sha256', required=True)
    linked.add_argument('--review', type=Path, required=True); linked.add_argument('--review-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.source, args.sha256, args.format, args.output)
        elif args.command == 'verify-review':
            result = verify_review(args.bundle, args.sha256, args.review, args.review_sha256)
        else:
            result = verify(args.bundle, args.sha256)
        print(json.dumps(result)); return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps(dict(status='refused', reason=str(error)))); return 2


if __name__ == '__main__':
    raise SystemExit(main())
