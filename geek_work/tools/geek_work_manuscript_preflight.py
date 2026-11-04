#!/usr/bin/env python3
"""Bounded, offline literal-LaTeX dependency lint over an explicit file selection."""
import argparse
from collections import Counter
import os
from pathlib import Path, PurePosixPath
import re
import stat
import geek_work_manuscript as m

MAX_FILES = 64
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_EVENTS = 10000
KEY = re.compile(r'[A-Za-z0-9_.:+/-]+\Z')
COMMAND = re.compile(r'\\([A-Za-z@]+|[^\n])')
REFS = {'ref', 'eqref', 'pageref', 'autoref'}
CITES = {'cite', 'citep', 'citet', 'parencite', 'textcite', 'nocite'}
PATHS = {'input', 'include', 'bibliography', 'addbibresource', 'includegraphics'}
LITERAL = REFS | CITES | PATHS | {'label'}
DYNAMIC = {'def', 'edef', 'gdef', 'xdef', 'newcommand', 'renewcommand',
           'providecommand', 'newenvironment', 'catcode', 'csname', 'includeonly',
           'graphicspath', 'DeclareGraphicsExtensions', 'endinput', 'directlua'}
OPAQUE = {'verbatim', 'verbatim*', 'lstlisting', 'minted'}
SUFFIXES = {'.tex', '.bib', '.pdf', '.png', '.jpg', '.jpeg', '.svg', '.eps'}


def path_name(name):
    m.require(type(name) is str and 0 < len(name) <= 200, 'path name')
    p = PurePosixPath(name)
    m.require(not p.is_absolute() and p.as_posix() == name and
              all(not part.startswith('.') for part in p.parts) and
              not any(ord(c) < 32 or c in '\\:<>"|?*' for c in name), 'relative literal path required')
    m.require(p.suffix in SUFFIXES, 'unsupported file suffix')
    return p


def config(value):
    m.require(type(value) is dict and set(value) == {'schema', 'entry', 'files'}, 'selection fields')
    m.require(value['schema'] == 'geek-work-manuscript-preflight-selection-1', 'selection schema')
    files = value['files']
    m.require(type(files) is list and 1 <= len(files) <= MAX_FILES, 'selection size')
    for name in files:
        path_name(name)
    m.require(len({n.casefold() for n in files}) == len(files), 'duplicate/case-colliding paths')
    for a in files:
        for b in files:
            m.require(a == b or not b.casefold().startswith(a.casefold() + '/'), 'path collision')
    m.require(value['entry'] in files and path_name(value['entry']).suffix == '.tex', 'selected TeX entry required')
    return value


def read_selected(root, name):
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
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular selected file required')
            raw = stream.read(MAX_FILE + 1)
            m.require(len(raw) <= MAX_FILE, 'file byte limit')
            if PurePosixPath(name).suffix in {'.tex', '.bib'}:
                m.source(raw)
            return raw
    except OSError as error:
        raise ValueError('missing or unsafe selected file: ' + name) from error
    finally:
        if fd is not None:
            os.close(fd)


def comments(text):
    # Mask unescaped percent comments, retaining character offsets and newlines.
    chars = list(text)
    i = 0
    while i < len(text):
        if text[i] == '\\':
            i += 2
        elif text[i] == '%':
            end = text.find('\n', i)
            if end < 0:
                end = len(text)
            chars[i:end] = ' ' * (end - i)
            i = end
        else:
            i += 1
    return ''.join(chars)


def group(text, pos, opening='{', closing='}'):
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != opening:
        return None, pos
    start = pos + 1
    depth = 1
    pos = start
    while pos < len(text):
        if text[pos] == '\\':
            pos += 2
            continue
        if text[pos] == opening:
            depth += 1
        elif text[pos] == closing:
            depth -= 1
            if depth == 0:
                return text[start:pos], pos + 1
        pos += 1
    return None, pos


def tex_events(text):
    text = comments(text)
    events, unknown = [], Counter()
    pos = 0
    def emit(kind, value, start):
        m.require(len(events) < MAX_EVENTS, 'event limit')
        events.append(dict(kind=kind, value=value, line=text.count('\n', 0, start) + 1))
    while match := COMMAND.search(text, pos):
        command = match[1]
        start, pos = match.start(), match.end()
        if command == 'verb':
            if pos < len(text) and text[pos] == '*':
                pos += 1
            end = text.find(text[pos], pos + 1) if pos < len(text) else -1
            emit('manual_review', 'inline verbatim omitted', start)
            pos = len(text) if end < 0 else end + 1
            continue
        if command == 'begin':
            env, end = group(text, pos)
            if env in OPAQUE:
                close = text.find('\\end{' + env + '}', end)
                emit('manual_review', 'opaque environment: ' + env, start)
                pos = len(text) if close < 0 else close + len('\\end{' + env + '}')
            continue
        if command in DYNAMIC or command.startswith('if') or command in {'else', 'fi'}:
            emit('manual_review', 'dynamic/control command: ' + command, start)
        if command not in LITERAL:
            if command.isalpha():
                unknown[command] += 1
            continue
        if pos < len(text) and text[pos] == '*':
            pos += 1
        for _ in range(2):
            option, end = group(text, pos, '[', ']')
            if option is not None:
                pos = end
        value, end = group(text, pos)
        if value is None:
            emit('manual_review', 'unsupported argument for ' + command, start)
            continue
        pos = end
        values = value.split(',') if command in CITES | {'bibliography'} else [value]
        for item in values:
            item = item.strip()
            if command == 'nocite' and item == '*':
                emit('manual_review', 'nocite wildcard not expanded', start)
            elif not KEY.fullmatch(item):
                emit('manual_review', 'nonliteral argument for ' + command, start)
            else:
                emit(command, item, start)
    return events, dict(sorted(unknown.items()))


def bib_keys(text):
    # Entry bodies consumed as balanced groups so @ inside a title is not a new entry.
    text = comments(text)
    keys, issues = [], []
    pos = 0
    while match := re.search(r'@([A-Za-z]+)\s*([{(])', text[pos:]):
        start = pos + match.start()
        opening = pos + match.end() - 1
        line = text.count('\n', 0, start) + 1
        if text[opening] != '{':
            issues.append(dict(kind='manual_review', value='parenthesized bibliography syntax; remaining entries not scanned', line=line))
            break
        body, end = group(text, opening)
        if body is None:
            issues.append(dict(kind='manual_review', value='unbalanced bibliography entry', line=line))
            break
        pos = end
        if match[1].lower() in {'comment', 'string', 'preamble'}:
            continue
        key, sep, _ = body.partition(',')
        key = key.strip()
        if sep and KEY.fullmatch(key):
            keys.append(dict(kind='bib_key', value=key, line=line))
        else:
            issues.append(dict(kind='manual_review', value='unsupported bibliography header', line=line))
    return keys, issues


def analyze(selection, blobs):
    selection = config(selection)
    m.require(set(blobs) == set(selection['files']), 'selected byte set')
    m.require(sum(map(len, blobs.values())) <= MAX_TOTAL, 'total byte limit')
    parsed, unknown = {}, {}
    for name, raw in sorted(blobs.items()):
        m.require(len(raw) <= MAX_FILE, 'file byte limit')
        if name.endswith('.tex'):
            parsed[name], unknown[name] = tex_events(m.source(raw))
        elif name.endswith('.bib'):
            keys, issues = bib_keys(m.source(raw))
            parsed[name] = keys + issues
    findings, deps, reachable, active_bibs = [], [], set(), set()
    def finding(code, name, event, **more):
        m.require(len(findings) < MAX_EVENTS, 'finding limit')
        findings.append(dict(code=code, file=name, line=event['line'], value=event['value'], **more))
    pending = [selection['entry']]
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for event in parsed[name]:
            command, target = event['kind'], event['value']
            if command == 'manual_review':
                finding('manual_review', name, event)
            if command not in PATHS:
                continue
            suffix = '.tex' if command in {'input', 'include'} else '.bib' if command in {'bibliography', 'addbibresource'} else None
            if suffix and not PurePosixPath(target).suffix:
                target += suffix
            try:
                path_name(target)
                m.require(suffix is None or target.endswith(suffix), 'dependency type')
                m.require(command != 'includegraphics' or PurePosixPath(target).suffix not in {'.tex', '.bib'}, 'asset type')
            except ValueError:
                finding('manual_review', name, event, detail='unsupported dependency path or implicit image extension')
                continue
            deps.append(dict(file=name, line=event['line'], command=command, target=target, selected=target in blobs))
            if target not in blobs:
                finding('dependency_not_selected', name, event, target=target)
            elif suffix == '.tex':
                pending.append(target)
            elif suffix == '.bib':
                active_bibs.add(target)
    # Detect include cycles without expanding TeX or repeatedly counting input files.
    edges = {name: [] for name in reachable}
    for dep in deps:
        if dep['command'] in {'input', 'include'} and dep['target'] in reachable:
            edges[dep['file']].append(dep)
    done, visiting = set(), set()
    def visit(name):
        visiting.add(name)
        for dep in edges[name]:
            target = dep['target']
            if target in visiting:
                finding('include_cycle', name, dict(line=dep['line'], value=target))
            elif target not in done:
                visit(target)
        visiting.remove(name)
        done.add(name)
    visit(selection['entry'])
    labels, keys = {}, {}
    for name in sorted(reachable | active_bibs):
        for event in parsed[name]:
            kind = event['kind']
            table = labels if kind == 'label' else keys if kind == 'bib_key' else None
            if name in active_bibs and kind == 'manual_review':
                finding('manual_review', name, event)
            if table is not None:
                if event['value'] in table:
                    finding('duplicate_label' if kind == 'label' else 'duplicate_bib_key', name, event, first=table[event['value']])
                else:
                    table[event['value']] = dict(file=name, line=event['line'])
    for name in sorted(reachable):
        for event in parsed[name]:
            if event['kind'] in REFS and event['value'] not in labels:
                finding('unresolved_reference', name, event)
            elif event['kind'] in CITES and event['value'] not in keys:
                finding('unresolved_citation', name, event)
    return dict(schema='geek-work-manuscript-preflight-1',
                status='findings' if findings else 'no_findings_in_supported_subset',
                files={name: dict(sha256=m.sha(raw), bytes=len(raw)) for name, raw in sorted(blobs.items())},
                selection=selection, reachable_tex=sorted(reachable), active_bibliographies=sorted(active_bibs),
                dependencies=deps, findings=findings, unanalysed_commands=unknown,
                compilation_verified=False, scientific_verification=False, full_syntax_coverage=False,
                limits='Literal LaTeX/BibTeX subset; project-root-relative paths; selected files only. No macro expansion, branch evaluation, bibliography field validation, asset decoding, network access or compilation. Unresolved means absent from extracted reachable declarations, not proof of a compiler error. Reads are per-file observations, not an atomic project snapshot.')


def check(root, selection, output):
    selection = config(selection)
    blobs = {}
    total = 0
    for name in sorted(selection['files']):
        raw = read_selected(root, name)
        total += len(raw)
        m.require(total <= MAX_TOTAL, 'total byte limit')
        blobs[name] = raw
    report = analyze(selection, blobs)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'sources').mkdir()
    for name, raw in blobs.items():
        dest = output / 'sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(raw)
    raw = m.encoded(report)
    m.require(len(raw) <= MAX_TOTAL, 'report byte limit')
    with (output / 'report.json').open('xb') as stream:
        stream.write(raw)
    manifest = m.encoded(dict(schema='geek-work-manuscript-preflight-bundle-1', report_sha256=m.sha(raw)))
    with (output / 'manifest.json').open('xb') as stream:
        stream.write(manifest)
    return dict(status=report['status'], findings=len(report['findings']), manifest_sha256=m.sha(manifest))


def verify(bundle, anchor):
    m.require(type(anchor) is str and re.fullmatch('[0-9a-f]{64}', anchor), 'full manifest SHA required')
    m.require(not bundle.is_symlink() and bundle.is_dir(), 'regular bundle directory required')
    m.require({p.name for p in bundle.iterdir()} == {'sources', 'report.json', 'manifest.json'}, 'bundle file set')
    manifest_raw = m.read(bundle / 'manifest.json')
    m.require(m.sha(manifest_raw) == anchor, 'manifest anchor mismatch')
    manifest = m.load(manifest_raw)
    m.require(type(manifest) is dict and set(manifest) == {'schema', 'report_sha256'} and manifest['schema'] == 'geek-work-manuscript-preflight-bundle-1', 'manifest schema')
    raw = m.read(bundle / 'report.json', MAX_TOTAL)
    m.require(m.sha(raw) == manifest['report_sha256'], 'report hash mismatch')
    report = m.load(raw)
    selection = config(report['selection'])
    expected = set(selection['files'])
    expected_dirs = {'.'} | {str(parent) for name in expected for parent in PurePosixPath(name).parents}
    root = bundle / 'sources'
    m.require(not root.is_symlink() and root.is_dir(), 'regular sources directory required')
    actual, dirs = set(), {'.'}
    for folder, subdirs, files in os.walk(root, followlinks=False):
        for child in subdirs + files:
            p = Path(folder) / child
            m.require(not p.is_symlink(), 'symlink in snapshot')
        dirs.update(str((Path(folder) / d).relative_to(root)) for d in subdirs)
        actual.update(str((Path(folder) / f).relative_to(root)) for f in files)
        m.require(len(actual) <= MAX_FILES and len(dirs) <= MAX_FILES * 100, 'snapshot entry limit')
    m.require(actual == expected and dirs == expected_dirs, 'snapshot file set')
    blobs, total = {}, 0
    for name in sorted(expected):
        blob = read_selected(root, name)
        total += len(blob)
        m.require(total <= MAX_TOTAL, 'total byte limit')
        blobs[name] = blob
    m.require(analyze(selection, blobs) == report, 'recomputed report mismatch')
    return dict(status='reproduced', preflight_status=report['status'], full_syntax_coverage=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('check')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    result = check(args.root, m.load(m.read(args.selection)), args.output) if args.action == 'check' else verify(args.bundle, args.sha256)
    print(m.encoded(result).decode(), end='')


if __name__ == '__main__':
    main()
