#!/usr/bin/env python3
"""Consistent nonce-registry snapshots and no-overwrite recovery against a pinned checkpoint.

The caller must supply a trusted CURRENT checkpoint SHA. This is not a monotonic
anchor service and cannot detect a coordinated rollback of both DB and anchor.
"""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import geek_work_proof_nonce as nonce

k = nonce.k
SCHEMA = 'geek-work-nonce-checkpoint-1'
MAX_DB = 64 << 20
MAX_ROWS = 100000


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(content); f.flush(); os.fsync(f.fileno())


def state(db, registry_id):
    """Logical state, independent of SQLite page allocation. Caller holds read transaction."""
    k.require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'registry_integrity')
    objects = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    k.require(objects == [('table','consumed'), ('table','metadata')], 'registry_schema')
    columns = db.execute('PRAGMA table_info(consumed)').fetchall()
    k.require(columns == [(0,'scope','TEXT',1,None,1),(1,'nonce','TEXT',1,None,2),
                          (2,'statement','TEXT',1,None,0),(3,'receipt','TEXT',1,None,0)],
              'registry_unique_key_schema')
    k.require(db.execute('PRAGMA table_info(metadata)').fetchall() ==
              [(0,'singleton','INTEGER',0,None,1),(1,'schema','TEXT',1,None,0),
               (2,'registry_id','TEXT',1,None,0)], 'registry_metadata_schema')
    k.require(db.execute('SELECT singleton,schema,registry_id FROM metadata').fetchall() ==
              [(1, nonce.SCHEMA, registry_id)], 'registry_identity')
    h = hashlib.sha256(b'GeekWork/NonceState/v1\x00' +
                       k.canonical(dict(schema=nonce.SCHEMA, registry_id=registry_id)) + b'\n')
    count = 0
    for scope, value, statement, raw in db.execute('SELECT scope,nonce,statement,receipt FROM consumed ORDER BY scope,nonce'):
        count += 1
        k.require(count <= MAX_ROWS and type(raw) is str and len(raw.encode()) <= 8192, 'registry_bounds')
        for digest in (scope, value, statement):
            k.require(type(digest) is str and nonce.adapter.contract.HEX.fullmatch(digest), 'registry_digest')
        receipt = k.strict_json(raw.encode())
        k.require(type(receipt) is dict and k.canonical(receipt).decode() == raw, 'receipt_encoding')
        k.require(receipt.get('schema') == nonce.SCHEMA and receipt.get('registry_id') == registry_id and
                  receipt.get('nonce') == value and receipt.get('statement_sha256') == statement, 'receipt_identity')
        scope_obj = receipt.get('scope')
        k.obj(scope_obj, {'ecosystem','network','application_id'})
        for field in scope_obj.values(): nonce.adapter.contract.label(field)
        k.require(nonce.scope_for(dict(target=scope_obj))[1] == scope, 'receipt_scope')
        h.update(k.canonical([scope,value,statement,receipt]) + b'\n')
    return dict(rows=count, state_sha256=h.hexdigest())


def snapshot(registry, registry_id, destination, _before_backup=lambda: None):
    registry, destination = Path(registry), Path(destination)
    k.require(not registry.is_symlink() and registry.stat().st_size <= MAX_DB, 'registry_bounds')
    destination.mkdir(mode=0o700)  # never merge into an existing directory
    target = destination/'registry.db'
    write_new(target, b'')
    # Let SQLite's backup API manage its own snapshot/locking. Holding an
    # extra source read transaction can stall a concurrent writer's commit.
    with contextlib.closing(nonce.connect(registry, registry_id)) as source:
        _before_backup()
        deadline = time.monotonic() + 30
        page_size = source.execute('PRAGMA page_size').fetchone()[0]
        def progress(status, remaining, total):
            k.require(time.monotonic() <= deadline, 'backup_timeout')
            k.require(total * page_size <= MAX_DB, 'registry_bounds')
        with contextlib.closing(sqlite3.connect(target)) as dest:
            source.backup(dest, pages=128, progress=progress, sleep=0.01)
    copied = nonce.read_regular(target, MAX_DB)
    with contextlib.closing(nonce.connect(target, registry_id)) as check:
        check.execute('BEGIN')
        try: expected = state(check, registry_id)
        finally: check.execute('ROLLBACK')
    # Copy is closed and checked before the completion marker is published.
    with target.open('rb') as f: os.fsync(f.fileno())
    checkpoint = dict(schema=SCHEMA, registry_id=registry_id, **expected,
                      database_sha256=k.digest(copied), database_bytes=len(copied),
                      source_path=str(registry.resolve()), snapshot_path=str(destination.resolve()),
                      external_monotonic_anchor=False)
    raw = k.canonical(checkpoint) + b'\n'
    write_new(destination/'checkpoint.json', raw)
    sync_dir(destination)
    sync_dir(destination.parent)
    return dict(status='snapshot_created', checkpoint_sha256=k.digest(raw),
                checkpoint=checkpoint, off_device_backup_verified=False)


def load_checkpoint(path, anchor):
    raw = nonce.read_regular(path, 32768)
    k.require(type(anchor) is str and nonce.adapter.contract.HEX.fullmatch(anchor), 'checkpoint_anchor_format')
    k.require(k.digest(raw) == anchor, 'checkpoint_anchor_mismatch')
    c = k.strict_json(raw)
    k.obj(c, {'schema','registry_id','rows','state_sha256','database_sha256','database_bytes',
              'source_path','snapshot_path','external_monotonic_anchor'})
    k.require(c['schema'] == SCHEMA and c['external_monotonic_anchor'] is False, 'checkpoint_schema')
    k.require(type(c['registry_id']) is str and 0 < len(c['registry_id']) <= 128, 'checkpoint_identity')
    for field in ('state_sha256','database_sha256'):
        k.require(type(c[field]) is str and nonce.adapter.contract.HEX.fullmatch(c[field]), 'checkpoint_digest')
    k.require(type(c['rows']) is int and 0 <= c['rows'] <= MAX_ROWS, 'checkpoint_rows')
    k.require(type(c['database_bytes']) is int and 0 < c['database_bytes'] <= MAX_DB, 'checkpoint_size')
    for field in ('source_path','snapshot_path'):
        k.require(type(c[field]) is str and len(c[field]) <= 4096, 'checkpoint_path')
    return c


def compare(registry, registry_id, checkpoint, anchor):
    c = load_checkpoint(checkpoint, anchor)
    k.require(c['registry_id'] == registry_id, 'checkpoint_identity')
    with contextlib.closing(nonce.connect(registry, registry_id)) as db:
        db.execute('BEGIN')
        try: actual = state(db, registry_id)
        finally: db.execute('ROLLBACK')
    k.require(actual == dict(rows=c['rows'], state_sha256=c['state_sha256']), 'state_mismatch')
    return dict(status='matches_pinned_checkpoint', registry_id=registry_id, **actual,
                continuously_guarded=False, checkpoint_sha256=anchor)


def restore(snapshot_dir, anchor, registry_id, destination, _fault=lambda stage: None):
    root, destination = Path(snapshot_dir), Path(destination)
    c = load_checkpoint(root/'checkpoint.json', anchor)
    k.require(c['registry_id'] == registry_id, 'checkpoint_identity')
    raw = nonce.read_regular(root/'registry.db', MAX_DB)
    k.require(len(raw) == c['database_bytes'] and k.digest(raw) == c['database_sha256'], 'backup_bytes_mismatch')
    # Write an isolated candidate in the destination filesystem, validate it,
    # then atomically publish without replacing any existing file/symlink.
    fd, temp_name = tempfile.mkstemp(prefix='.nonce-restore-', suffix='.db', dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        compare(temp, registry_id, root/'checkpoint.json', anchor)
        _fault('before_publish')
        os.link(temp, destination, follow_symlinks=False)
        sync_dir(destination.parent)
        _fault('after_publish')
    finally:
        temp.unlink(missing_ok=True)
    return dict(status='restored_to_new_path', registry_id=registry_id,
                restored_path=str(destination.resolve()), checkpoint_sha256=anchor,
                state_sha256=c['state_sha256'], rows=c['rows'], active_registry_switched=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('snapshot')
    s.add_argument('--registry',required=True);s.add_argument('--registry-id',required=True)
    s.add_argument('--destination',required=True)
    c=sub.add_parser('compare')
    c.add_argument('--registry',required=True);c.add_argument('--registry-id',required=True)
    c.add_argument('--checkpoint',required=True);c.add_argument('--expected-checkpoint-sha256',required=True)
    r=sub.add_parser('restore')
    r.add_argument('--snapshot',required=True);r.add_argument('--registry-id',required=True)
    r.add_argument('--expected-checkpoint-sha256',required=True);r.add_argument('--destination',required=True)
    a=p.parse_args()
    try:
        if a.action=='snapshot': result=snapshot(a.registry,a.registry_id,a.destination)
        elif a.action=='compare':result=compare(a.registry,a.registry_id,a.checkpoint,a.expected_checkpoint_sha256)
        else:result=restore(a.snapshot,a.expected_checkpoint_sha256,a.registry_id,a.destination)
        print(k.canonical(result).decode());return 0
    except (k.Refusal,OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
        print(k.canonical(dict(status='not_completed',reason=str(e))).decode());return 1


if __name__=='__main__':raise SystemExit(main())
