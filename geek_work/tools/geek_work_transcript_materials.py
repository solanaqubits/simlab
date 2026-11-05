#!/usr/bin/env python3
"""Bind transcript cues to supplied material bytes; no media decoding or alignment claim."""
import argparse
import os
from pathlib import Path
import stat

import geek_work_transcript as t
from knowledge import strict_json

m, k, tree, ops = t.m, t.k, t.tree, t.ops
MAX_MATERIAL = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
SCHEMA = 'geek-work-transcript-materials-1'
FLAGS = dict(media_alignment_verified=False, transcription_accuracy_verified=False,
             page_existence_verified=False, ocr_accuracy_verified=False,
             origin_verified=False, semantic_support_verified=False, publication_authorized=False)


def binary_source(root, name):
    """Bounded descriptor-relative read; refuse symlinks and special files."""
    parts = k.path_name(name).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as stream:
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular material required')
            raw = stream.read(MAX_MATERIAL + 1)
        m.require(0 < len(raw) <= MAX_MATERIAL, 'material byte limit or empty material')
        return raw
    finally:
        os.close(fd)


def integer(value, low, high):
    m.require(type(value) is int and low <= value <= high, 'bounded integer locator required')


def validate(spec, cues, anchor):
    k.obj(spec, 'schema transcript_sha256 materials bindings')
    m.require(spec['schema'] == SCHEMA, 'materials schema')
    k.digest(spec['transcript_sha256'])
    m.require(spec['transcript_sha256'] == anchor, 'transcript manifest mismatch')
    materials, paths = {}, set()
    for row in k.rows(spec['materials'], 16, 1):
        k.obj(row, 'id path sha256 kind'); k.ident(row['id']); k.path_name(row['path']); k.digest(row['sha256'])
        m.require(type(row['kind']) is str and row['kind'] in ('media', 'slides', 'ocr'), 'material kind')
        m.require(row['id'] not in materials and row['path'].casefold() not in paths, 'duplicate material')
        materials[row['id']] = row; paths.add(row['path'].casefold())
    by_cue = {row['id']: row for row in cues}; seen, used, bindings = set(), set(), []
    for row in k.rows(spec['bindings'], 256, 1):
        k.obj(row, 'id cue material locator review_note')
        for field in ('id', 'cue', 'material'): k.ident(row[field])
        k.text(row['review_note'])
        m.require(row['id'] not in seen, 'duplicate binding'); seen.add(row['id'])
        m.require(row['cue'] in by_cue and row['material'] in materials, 'unknown cue or material')
        kind = materials[row['material']]['kind']; loc = row['locator']; used.add(row['material'])
        if kind == 'media':
            k.obj(loc, 'start_ms end_ms')
            integer(loc['start_ms'], 0, t.MAX_TIME); integer(loc['end_ms'], 1, t.MAX_TIME)
            m.require(loc['start_ms'] < loc['end_ms'], 'positive media interval required')
        else:
            k.obj(loc, 'page slides' if kind == 'ocr' else 'page'); integer(loc['page'], 1, 100000)
            if kind == 'ocr':
                k.ident(loc['slides'])
                m.require(loc['slides'] in materials and materials[loc['slides']]['kind'] == 'slides', 'OCR needs pinned slides')
                used.add(loc['slides'])
        bindings.append(dict(**row, cue_evidence=by_cue[row['cue']], locator_status='reported_not_verified'))
    m.require(used == set(materials), 'unreferenced material refused')
    return materials, bindings


def transcript_bytes(bundle, anchor):
    t.verify(bundle, anchor)
    blobs = {name: m.read(Path(bundle)/name, t.MAX_OUTPUT) for name in t.FILES | {'manifest.json'}}
    # Recheck captured bytes through reconstruction, not a separately read cue index.
    expected, _ = t.artifacts(blobs['source.vtt'], strict_json(blobs['map.json']))
    expected['map.json'] = blobs['map.json']
    manifest = m.encoded(dict(schema=t.SCHEMA, files={n:m.sha(b) for n,b in expected.items()}, **FLAGS_TRANSCRIPT))
    m.require(blobs == {**expected, 'manifest.json':manifest} and m.sha(manifest) == anchor, 'transcript changed while reading')
    return blobs, t.cues(blobs['source.vtt'])


FLAGS_TRANSCRIPT = {key:False for key in ('origin_verified','media_alignment_verified','transcription_accuracy_verified','semantic_support_verified','publication_authorized')}


def artifacts(spec_raw, transcript, anchor, cues, read_material):
    spec = strict_json(spec_raw); materials, bindings = validate(spec, cues, anchor)
    blobs = {}; total = 0
    for ident, row in materials.items():
        raw = read_material(row)
        m.require(m.sha(raw) == row['sha256'], 'material hash mismatch: ' + ident)
        total += len(raw); m.require(total <= MAX_TOTAL, 'aggregate material byte limit')
        blobs['materials/' + ident + '.bin'] = raw
    report = dict(schema=SCHEMA, transcript_sha256=anchor, materials=spec['materials'],
                  bindings=bindings, material_bytes=total, **FLAGS)
    blobs.update({'transcript/'+n:b for n,b in transcript.items()})
    blobs.update({'map.json':spec_raw, 'bindings.json':m.encoded(report)})
    manifest = m.encoded(dict(schema=SCHEMA, files={n:m.sha(b) for n,b in blobs.items()}, **FLAGS))
    m.require(len(blobs['bindings.json']) <= t.MAX_OUTPUT, 'binding report byte limit')
    return {**blobs,'manifest.json':manifest}


def prepare(bundle, anchor, mapping, root, output):
    bundle, mapping, root, output = map(Path,(bundle,mapping,root,output))
    ops.outside(output,bundle,mapping,root)
    transcript, cues = transcript_bytes(bundle,anchor)
    raw = m.read(mapping,t.MAX_INPUT)
    blobs = artifacts(raw,transcript,anchor,cues,lambda row:binary_source(root,row['path']))
    tree.write_tree(output,blobs)
    return dict(status='material_bindings_ready',manifest_sha256=m.sha(blobs['manifest.json']),**FLAGS)


def verify(bundle, anchor):
    bundle=Path(bundle);k.digest(anchor)
    manifest=m.read(bundle/'manifest.json',t.MAX_INPUT)
    m.require(m.sha(manifest)==anchor,'manifest anchor mismatch')
    spec_raw=m.read(bundle/'map.json',t.MAX_INPUT); spec=strict_json(spec_raw)
    k.obj(spec,'schema transcript_sha256 materials bindings')
    transcript,cues=transcript_bytes(bundle/'transcript',spec['transcript_sha256'])
    expected=artifacts(spec_raw,transcript,spec['transcript_sha256'],cues,
                       lambda row:binary_source(bundle,'materials/'+row['id']+'.bin'))
    tree.exact_tree(bundle,set(expected))
    m.require(manifest==expected['manifest.json'],'manifest reproduction mismatch')
    m.require(m.read(bundle/'bindings.json',t.MAX_OUTPUT)==expected['bindings.json'],'binding reproduction mismatch')
    return dict(status='material_bindings_reproduced',manifest_sha256=anchor,**FLAGS)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','verify'])
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--map',type=Path);p.add_argument('--root',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        if a.action=='prepare':
            m.require(all(x is not None for x in (a.map,a.root,a.output)),'map/root/output required')
            result=prepare(a.bundle,a.sha256,a.map,a.root,a.output)
        else:
            m.require(all(x is None for x in (a.map,a.root,a.output)),'unexpected prepare arguments')
            result=verify(a.bundle,a.sha256)
        print(m.encoded(result).decode(),end='');return 0
    except (ValueError,OSError,UnicodeError) as error:
        print(m.encoded(dict(status='refused',reason=str(error))).decode(),end='');return 2


if __name__=='__main__':raise SystemExit(main())
