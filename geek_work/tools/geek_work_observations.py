#!/usr/bin/env python3
"""Archive bounded observations and read exact anchored ranges offline; no execution."""
import argparse
import base64
import json
from pathlib import Path
import re

import geek_work_manuscript as m
import geek_work_batch_hunks as tree

MAX_SOURCE = 16 * 1024 * 1024
MAX_EXCERPT = 64 * 1024
MAX_METADATA = 16 * 1024
SCHEMA = 'geek-work-observation-1'
EXCERPT_SCHEMA = 'geek-work-observation-excerpt-1'
FILES = {'observation.bin', 'manifest.json'}


def digest(value):
    m.require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'full SHA-256 required')
    return value


def handle_digest(handle):
    m.require(type(handle) is str and handle.startswith('obs1:'), 'obs1 handle required')
    return digest(handle[5:])


def source_info(raw, encoding):
    m.require(len(raw) <= MAX_SOURCE, 'observation byte limit')
    m.require(encoding in ('utf-8', 'binary'), 'explicit supported encoding required')
    text = raw.decode('utf-8') if encoding == 'utf-8' else None
    return dict(sha256=m.sha(raw), bytes=len(raw), encoding=encoding,
                unicode_codepoints=len(text) if text is not None else None,
                lf_lines=raw.count(b'\n') + int(bool(raw) and not raw.endswith(b'\n')))


def manifest(raw, encoding, label, reported_exit_code):
    m.require(type(label) is str and 0 < len(label.strip()) <= 256 and
              all(ord(c) >= 32 for c in label), 'bounded producer label required')
    m.require(reported_exit_code is None or
              type(reported_exit_code) is int and -255 <= reported_exit_code <= 255,
              'reported exit code must be null or bounded integer')
    return dict(schema=SCHEMA, source=source_info(raw, encoding),
                producer_label=label, reported_exit_code=reported_exit_code,
                origin_verified=False, execution_verified=False,
                semantic_completeness_verified=False, publication_authorized=False)


def capture(source, expected_sha256, output, encoding='utf-8', label='unspecified', reported_exit_code=None):
    digest(expected_sha256)
    source, output = Path(source), Path(output)
    m.require(not output.exists() and not output.is_symlink(), 'new archive directory required')
    m.require(not source.resolve().is_relative_to(output.resolve()), 'output overlaps source')
    raw = m.read(source, MAX_SOURCE)
    m.require(m.sha(raw) == expected_sha256, 'source anchor mismatch')
    data = manifest(raw, encoding, label, reported_exit_code)
    encoded = m.encoded(data)
    # Only the completed manifest names an archive. A failed partial directory is
    # retained; callers must use a fresh destination. No durability/atomicity claim.
    tree.write_tree(output, {'observation.bin': raw, 'manifest.json': encoded})
    return dict(status='observation_archived', handle='obs1:' + m.sha(encoded),
                source=data['source'], source_modified=False, origin_verified=False)


def verified(bundle, handle):
    anchor = handle_digest(handle)
    bundle = Path(bundle)
    tree.exact_tree(bundle, FILES)
    encoded = m.read(bundle / 'manifest.json', MAX_METADATA)
    m.require(m.sha(encoded) == anchor, 'manifest anchor mismatch')
    spec = m.load(encoded)
    m.require(type(spec) is dict and type(spec.get('source')) is dict, 'observation manifest object')
    raw = m.read(bundle / 'observation.bin', MAX_SOURCE)
    expected = manifest(raw, spec['source'].get('encoding'), spec.get('producer_label'),
                        spec.get('reported_exit_code'))
    # Canonical replay also rejects missing/extra fields, bool-as-int metadata,
    # false verification promotions and altered source byte/line counts.
    m.require(encoded == m.encoded(expected), 'observation manifest reproduction mismatch')
    return raw, expected


def verify(bundle, handle):
    _, spec = verified(bundle, handle)
    return dict(status='observation_integrity_reproduced', handle=handle, source=spec['source'],
                origin_verified=False, execution_verified=False, semantic_completeness_verified=False)


def bounds(start, end, length):
    m.require(type(start) is int and type(end) is int and 0 <= start <= end <= length,
              'zero-based half-open range required')
    m.require(end - start <= MAX_EXCERPT, 'range width limit; request a smaller page')


def line_boundary(raw, index):
    """LF-delimited lines only; preserve CR and never create a trailing phantom line."""
    pos = 0
    for _ in range(index):
        found = raw.find(b'\n', pos)
        pos = len(raw) if found < 0 else found + 1
    return pos


def excerpt(bundle, handle, unit, start, end):
    raw, spec = verified(bundle, handle)
    m.require(unit in ('bytes', 'codepoints', 'lines'), 'supported range unit required')
    if unit == 'bytes':
        bounds(start, end, len(raw)); left, right = start, end
    elif unit == 'codepoints':
        m.require(spec['source']['encoding'] == 'utf-8', 'codepoints require UTF-8 observation')
        text = raw.decode('utf-8'); bounds(start, end, len(text))
        left, right = len(text[:start].encode('utf-8')), len(text[:end].encode('utf-8'))
    else:
        bounds(start, end, spec['source']['lf_lines'])
        left, right = line_boundary(raw, start), line_boundary(raw, end)
    m.require(right - left <= MAX_EXCERPT, 'excerpt byte limit; request a smaller page')
    selected = raw[left:right]
    try:
        text = selected.decode('utf-8')
    except UnicodeError:
        text = None
    return dict(schema=EXCERPT_SCHEMA, handle=handle, source_sha256=spec['source']['sha256'],
                range=dict(unit=unit, start=start, end=end),
                byte_range=dict(start=left, end=right), excerpt_sha256=m.sha(selected),
                bytes=len(selected), base64=base64.b64encode(selected).decode('ascii'), utf8=text,
                content_is_untrusted=True, semantic_completeness_verified=False)


def write_excerpt(output, result, bundle):
    output, bundle = Path(output), Path(bundle)
    m.require(not output.resolve().is_relative_to(bundle.resolve()), 'excerpt must be outside archive')
    m.require(not output.exists() and not output.is_symlink(), 'new excerpt file required')
    encoded = m.encoded(result)
    with output.open('xb') as stream:
        stream.write(encoded)
    return dict(status='excerpt_saved', excerpt_sha256=m.sha(encoded), handle=result['handle'])


def verify_excerpt(path, anchor, bundle, handle):
    digest(anchor)
    encoded = m.read(Path(path), MAX_EXCERPT * 10 + MAX_METADATA)
    m.require(m.sha(encoded) == anchor, 'excerpt anchor mismatch')
    spec = m.load(encoded)
    m.require(type(spec) is dict and type(spec.get('range')) is dict, 'excerpt object/range')
    selected = spec['range']
    expected = excerpt(bundle, handle, selected.get('unit'), selected.get('start'), selected.get('end'))
    m.require(encoded == m.encoded(expected), 'excerpt reproduction mismatch')
    return dict(status='exact_excerpt_reproduced', handle=handle, excerpt_sha256=anchor,
                semantic_completeness_verified=False)



def execution_logs(execution, anchor):
    # Lazy import keeps ordinary observation operations independent of the runner.
    import geek_work_exact_runner as runner
    runner.verify(execution, anchor)
    meta=m.read(execution/'manifest.json');m.require(m.sha(meta)==anchor,'execution anchor changed')
    entries=m.load(meta)['files'];names=('request.json','receipt.json','stdout.bin','stderr.bin')
    raw={n:m.read(execution/n) for n in names}
    m.require(all(m.sha(b)==entries[n] for n,b in raw.items()),'execution changed during capture')
    request=m.load(raw['request.json']);receipt=m.load(raw['receipt.json']);process=receipt['process']
    code=process['returncode'];reported_code=code if code is not None and -255<=code<=255 else None
    files={};streams=[]
    for name in ('stdout','stderr'):
        data=raw[name+'.bin']
        # Binary is deliberate: logs may contain invalid UTF-8 or partial characters.
        encoded=m.encoded(manifest(data,'binary','execution/'+request['attempt_id']+'/'+name,reported_code))
        files[name+'/observation.bin']=data;files[name+'/manifest.json']=encoded
        streams.append(dict(stream=name,handle='obs1:'+m.sha(encoded),bytes=len(data),sha256=m.sha(data),
                            reported_truncated=process[name+'_truncated']))
    index=dict(schema='geek-work-execution-log-handles-1',execution_manifest_sha256=anchor,
               attempt_id=request['attempt_id'],process_outcome=process['outcome'],returncode=code,
               result_status=receipt['result']['status'],streams=streams,
               complete_process_output_verified=False,execution_independently_verified=False,
               limits='Captured bytes only. Truncation flags report the output cap; timeout/interruption may lose buffered output even when false. Handles alone do not prove origin from a receipt. Parent verification checks byte binding, not execution authenticity.')
    files['index.json']=m.encoded(index)
    return files,index


def capture_execution(execution,anchor,output):
    import geek_work_file_operations as ops
    ops.outside(output,execution);files,index=execution_logs(execution,anchor)
    tree.write_tree(output,files)
    return dict(status='execution_logs_archived',index_sha256=m.sha(files['index.json']),
                streams=index['streams'],parent_binding_checked_here=True,source_modified=False)


def verify_execution(bundle,index_sha,execution,execution_sha):
    digest(index_sha);raw=m.read(bundle/'index.json',MAX_METADATA)
    m.require(m.sha(raw)==index_sha,'log index anchor mismatch')
    files,index=execution_logs(execution,execution_sha)
    m.require(raw==files['index.json'],'execution log binding mismatch')
    tree.exact_tree(bundle,set(files))
    for stream in index['streams']:
        name=stream['stream'];verified(bundle/name,stream['handle'])
    for name,expected in files.items():m.require(m.read(bundle/name)==expected,'execution log bytes mismatch')
    return dict(status='execution_log_binding_reproduced',parent_binding_checked_here=True,
                subprocess_rerun=False,execution_independently_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('--input', type=Path, required=True)
    cap.add_argument('--sha256', required=True, help='Expected SHA-256 of the original bytes')
    cap.add_argument('--output', type=Path, required=True)
    cap.add_argument('--encoding', choices=['utf-8', 'binary'], default='utf-8')
    cap.add_argument('--label', required=True)
    cap.add_argument('--reported-exit-code', type=int)
    for name in ('verify', 'read', 'verify-excerpt'):
        item = sub.add_parser(name)
        item.add_argument('--bundle', type=Path, required=True)
        item.add_argument('--handle', required=True)
        if name == 'read':
            item.add_argument('--unit', choices=['bytes', 'codepoints', 'lines'], required=True)
            item.add_argument('--start', type=int, required=True)
            item.add_argument('--end', type=int, required=True)
            item.add_argument('--output', type=Path, help='Optional NEW excerpt file outside archive')
        elif name == 'verify-excerpt':
            item.add_argument('--excerpt', type=Path, required=True)
            item.add_argument('--sha256', required=True, help='Expected SHA-256 of excerpt JSON')
    cap = sub.add_parser('capture-execution')
    cap.add_argument('--bundle', type=Path, required=True)
    cap.add_argument('--sha256', required=True)
    cap.add_argument('--output', type=Path, required=True)
    ver = sub.add_parser('verify-execution')
    ver.add_argument('--bundle', type=Path, required=True)
    ver.add_argument('--sha256', required=True, help='Expected SHA-256 of index.json')
    ver.add_argument('--execution', type=Path, required=True)
    ver.add_argument('--execution-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture-execution':
            result = capture_execution(args.bundle,args.sha256,args.output)
        elif args.command == 'verify-execution':
            result = verify_execution(args.bundle,args.sha256,args.execution,args.execution_sha256)
        elif args.command == 'capture':
            result = capture(args.input, args.sha256, args.output, args.encoding, args.label, args.reported_exit_code)
        elif args.command == 'verify':
            result = verify(args.bundle, args.handle)
        elif args.command == 'read':
            result = excerpt(args.bundle, args.handle, args.unit, args.start, args.end)
            if args.output is not None:
                result = write_excerpt(args.output, result, args.bundle)
        else:
            result = verify_excerpt(args.excerpt, args.sha256, args.bundle, args.handle)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        print(json.dumps(dict(status='rejected', reason=str(error)), ensure_ascii=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
