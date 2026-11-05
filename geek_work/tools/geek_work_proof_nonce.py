#!/usr/bin/env python3
"""Verify a pinned local gnark proof, then atomically consume its scoped nonce.

Local trusted filesystem/SQLite/toolchain only; not an external action executor,
production setup attestation, rollback detector or blockchain transaction manager.
"""
import argparse
import contextlib
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tempfile
import uuid

import geek_work_gnark_statement as adapter

k = adapter.k
SCHEMA = 'geek-work-proof-nonce-1'
SUCCESS = 'request_bound_proof_verified; test_setup_only; nonce_registry_not_implemented'


def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        k.require(stat.S_ISREG(s.st_mode) and s.st_size <= limit, 'file_size_or_type')
        b = f.read(limit + 1)
        k.require(len(b) <= limit, 'file_size_or_type')
        return b


def initialize(path):
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    registry_id = str(uuid.uuid4())
    # A failed init deliberately leaves a non-usable file, never an auto-reset.
    with contextlib.closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA synchronous=FULL')
        with db:
            db.execute('CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema TEXT NOT NULL, registry_id TEXT NOT NULL)')
            db.execute('CREATE TABLE consumed (scope TEXT NOT NULL, nonce TEXT NOT NULL, statement TEXT NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(scope,nonce))')
            db.execute('INSERT INTO metadata VALUES (1,?,?)', (SCHEMA, registry_id))
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return dict(status='registry_initialized', registry_id=registry_id, schema=SCHEMA)


def connect(path, registry_id):
    path = Path(path)
    k.require(path.is_file() and not path.is_symlink(), 'registry_missing_or_symlink')
    # mode=rw never recreates a lost registry; caller must also pin its ID.
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True,
                         timeout=5, isolation_level=None)
    try:
        db.execute('PRAGMA synchronous=FULL')
        k.require(db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete', 'registry_journal_mode')
        row = db.execute('SELECT schema,registry_id FROM metadata WHERE singleton=1').fetchone()
        k.require(row == (SCHEMA, registry_id), 'registry_identity')
        return db
    except BaseException:
        db.close()
        raise


def scope_for(request):
    # Verifier/key upgrades must NOT create a new nonce namespace.
    scope = {name: request['target'][name] for name in ('ecosystem', 'network', 'application_id')}
    return scope, k.digest(b'GeekWork/NonceScope/v1\x00' + k.canonical(scope))


def _commit_verified(db, registry_id, request, statement, audit, _fault=lambda stage: None):
    """Internal transaction primitive. Tests exercise storage, not cryptography."""
    scope, scope_hash = scope_for(request)
    nonce = request['nonce']
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('SELECT statement,receipt FROM consumed WHERE scope=? AND nonce=?',
                         (scope_hash, nonce)).fetchone()
        if row:
            k.require(row[0] == statement, 'nonce_conflict')
            receipt = k.strict_json(row[1].encode())
            status = 'already_consumed'
        else:
            receipt = dict(schema=SCHEMA, registry_id=registry_id, scope=scope, nonce=nonce,
                           statement_sha256=statement, **audit)
            db.execute('INSERT INTO consumed VALUES (?,?,?,?)',
                       (scope_hash, nonce, statement, k.canonical(receipt).decode()))
            status = 'consumed'
        _fault('before_commit')
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    _fault('after_commit')
    return dict(status=status, receipt=receipt, receipt_sha256=k.digest(k.canonical(receipt)),
                new_consumption=(status == 'consumed'), external_action_performed=False)


def _verify(snapshot, binary, expected_sha, timeout):
    # Executable and artifact bytes have already been copied and pinned. No shell.
    try:
        proc = subprocess.run([str(binary), 'verify-bound', str(snapshot),
                               str(snapshot / 'expected.json'), expected_sha],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as err:
        raise k.Refusal('verification_timeout') from err
    k.require(proc.returncode == 0, 'verification_failed')
    k.require(len(proc.stdout) <= 65536 and len(proc.stderr) <= 65536, 'verification_output_size')
    lines = proc.stdout.decode('utf-8', errors='strict').splitlines()
    k.require(bool(lines) and lines[-1] == SUCCESS, 'verification_result_missing')


def consume(bundle, anchor, registry, registry_id, backend, backend_sha, timeout=60):
    k.require(type(timeout) is int and 1 <= timeout <= 120, 'verification_timeout_range')
    k.require(type(backend_sha) is str and adapter.contract.HEX.fullmatch(backend_sha), 'backend_pin_format')
    # Check store identity before expensive verification, but never consume early.
    with contextlib.closing(connect(registry, registry_id)):
        pass
    bundle = Path(bundle)
    raw = read_regular(bundle / 'request.json', adapter.contract.MAX_REQUEST_BYTES)
    artifacts = {name: read_regular(bundle / f, adapter.contract.MAX_ARTIFACT_BYTES)
                 for name, f in adapter.FILES.items()}
    expected = adapter.expected_statement(raw, anchor, artifacts)
    request = adapter.contract.validate(raw, anchor)
    proof = read_regular(bundle / 'proof.bin', 1 << 20)
    binary_bytes = read_regular(backend, 128 << 20)
    k.require(k.digest(binary_bytes) == backend_sha, 'backend_pin_mismatch')
    expected_bytes = k.canonical(expected) + b'\n'
    with tempfile.TemporaryDirectory(prefix='geek-work-proof-') as d:
        snapshot = Path(d)
        for name, b in artifacts.items():
            (snapshot / adapter.FILES[name]).write_bytes(b)
        (snapshot / 'proof.bin').write_bytes(proof)
        (snapshot / 'expected.json').write_bytes(expected_bytes)
        binary = snapshot / 'verifier-executable'
        binary.write_bytes(binary_bytes)
        binary.chmod(0o500)
        _verify(snapshot, binary, k.digest(expected_bytes), timeout)
    # Receipt and nonce share one SQLite transaction. Lost stdout is retryable.
    audit = dict(first_request_file_sha256=anchor, first_proof_sha256=k.digest(proof),
                 first_backend_sha256=backend_sha, program_sha256=expected['program_sha256'],
                 verifier_sha256=expected['verifier_sha256'], test_setup_only=True)
    with contextlib.closing(connect(registry, registry_id)) as db:
        result = _commit_verified(db, registry_id, request, ''.join(expected['context']), audit)
    result.update(cryptographic_verification=True, current_proof_sha256=k.digest(proof),
                  current_backend_sha256=backend_sha)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init'); init.add_argument('--registry', type=Path, required=True)
    use = sub.add_parser('consume')
    for flag in ('registry', 'registry-id', 'bundle', 'expected-request-sha256',
                 'backend', 'expected-backend-sha256'):
        use.add_argument('--' + flag, required=True)
    use.add_argument('--timeout', type=int, default=60)
    a = p.parse_args()
    try:
        if a.action == 'init':
            result = initialize(a.registry)
        else:
            result = consume(a.bundle, a.expected_request_sha256, a.registry, a.registry_id,
                             a.backend, a.expected_backend_sha256, a.timeout)
        print(k.canonical(result).decode())
        return 0
    except (k.Refusal, OSError, ValueError, TypeError, KeyError, sqlite3.Error) as err:
        # This describes this attempt only; a previous commit may have succeeded.
        print(k.canonical(dict(status='not_accepted', reason=str(err))).decode())
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
