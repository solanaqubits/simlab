"""Offline consistency audit of normal compiled ALCC receipts; never executes code.

A consistent archive is not an authenticated execution or a Lean kernel proof.
The caller supplies the trusted PIN and independently expected input hashes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from datetime import datetime

PROTOCOL = 'ALCC-BRIDGE-VERIFY-1'
BASE = '4c7e29b9735892e6979e439e9b4e08ea9a745ddc'
PAIRS = {0: 'VERIFIED_SUCCESS', 2: 'IDENTITY_MISMATCH', 3: 'DECODE_ERROR'}
RUNTIME_ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LEAN_NUM_THREADS': '1',
               'LEAN_ABORT_ON_PANIC': '1', 'LEAN_STACK_SIZE_KB': '65536',
               'MIMALLOC_ARENA_RESERVE': '67108864'}
PROVENANCE = ('kernel_base_commit', 'cli_source_commit', 'bridge_runner_commit', 'lean_toolchain')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hex_value(value, size):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None


def read_file(path, limit):
    """Bounded regular-file input; refuse final symlinks and FIFOs without blocking."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'not a regular file')
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'file byte budget exceeded')
    return data


def hash_file(path, limit=512 * 1024**2):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'not a regular artifact')
        h, size = hashlib.sha256(), 0
        while chunk := stream.read(65536):
            size += len(chunk)
            require(size <= limit, 'artifact byte budget exceeded')
            h.update(chunk)
    return h.hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('nonfinite JSON number: ' + value)

    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def obj(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ': unexpected schema')


def _audit(receipt_path, pin_path, passport_hash, certificate_hash):
    require(hex_value(passport_hash, 64) and hex_value(certificate_hash, 64), 'expected input hashes required')
    pin_bytes = read_file(pin_path, 65536)
    pin = parse(pin_bytes)
    obj(pin, (*PROVENANCE, 'protocol_version', 'evidence_kind', 'artifacts'), 'PIN')
    require(pin['protocol_version'] == PROTOCOL and pin['evidence_kind'] == 'compiled_execution', 'PIN protocol mismatch')
    require(pin['kernel_base_commit'] == BASE, 'unsupported kernel base')
    for key in PROVENANCE[:3]:
        require(hex_value(pin[key], 40), 'invalid source commit')
    require(type(pin['lean_toolchain']) is str and bool(pin['lean_toolchain']), 'missing toolchain')
    obj(pin['artifacts'], ('binary', 'build_log', 'environment', 'runner'), 'artifacts')
    for name, item in pin['artifacts'].items():
        obj(item, ('path', 'sha256'), name)
        require(type(item['path']) is str and Path(item['path']).is_absolute(), 'artifact path must be absolute')
        require(hex_value(item['sha256'], 64), 'invalid artifact digest')
        require(hash_file(item['path']) == item['sha256'], 'artifact hash mismatch: ' + name)
    env_bytes = read_file(pin['artifacts']['environment']['path'], 4 * 1024**2)
    require(sha(env_bytes) == pin['artifacts']['environment']['sha256'], 'environment changed while reading')
    env = parse(env_bytes)
    require(type(env) is dict, 'environment must be an object')
    for key in ('kernel_base_commit', 'cli_source_commit', 'lean_toolchain'):
        require(env.get(key) == pin[key], 'environment provenance mismatch: ' + key)
    if 'bridge_runner_commit' in env:
        require(env['bridge_runner_commit'] == pin['bridge_runner_commit'], 'environment runner mismatch')
    for key, artifact in (('binary_sha256', 'binary'), ('build_log_hash', 'build_log')):
        require(env.get(key) == pin['artifacts'][artifact]['sha256'], 'environment hash mismatch: ' + key)

    raw_receipt = read_file(receipt_path, 4 * 1024**2)
    r = parse(raw_receipt)
    keys = (*PROVENANCE, 'protocol_version', 'evidence_kind', 'started_at', 'finished_at',
            'status', 'exit_code', 'run_directory', 'runtime_environment', 'limits', 'snapshots',
            'errors', 'command', 'pin_sha256', 'binary_sha256', 'build_log_hash',
            'environment_manifest_hash', 'snapshot_integrity_verified', 'artifact_integrity_verified',
            'elapsed_seconds', 'stdout_sha256', 'stderr_sha256', 'raw_stdout_base64', 'raw_stderr_base64')
    obj(r, keys, 'receipt')
    require(r['protocol_version'] == PROTOCOL and r['evidence_kind'] == 'compiled_execution', 'receipt protocol mismatch')
    require(type(r['exit_code']) is int and r['exit_code'] in PAIRS, 'only normal 0/2/3 outcomes supported')
    require(r['status'] == PAIRS[r['exit_code']], 'receipt verdict/exit mismatch')
    require(r['errors'] == [], 'normal receipt contains errors')
    require(r['snapshot_integrity_verified'] is True and r['artifact_integrity_verified'] is True, 'integrity not established')
    require(r['pin_sha256'] == sha(pin_bytes), 'receipt PIN mismatch')
    for key in PROVENANCE:
        require(r[key] == pin[key], 'receipt provenance mismatch: ' + key)
    for key, artifact in (('binary_sha256', 'binary'), ('build_log_hash', 'build_log'), ('environment_manifest_hash', 'environment')):
        require(r[key] == pin['artifacts'][artifact]['sha256'], 'receipt artifact mismatch: ' + key)
    require(type(r['elapsed_seconds']) in (int, float) and math.isfinite(r['elapsed_seconds']) and r['elapsed_seconds'] >= 0, 'invalid elapsed time')
    times = [datetime.fromisoformat(r[key]) for key in ('started_at', 'finished_at')]
    require(all(t.utcoffset() is not None for t in times) and times[1] >= times[0], 'invalid timestamps')
    require(type(r['run_directory']) is str and Path(r['run_directory']).is_absolute(), 'invalid recorded directory')
    limits = r['limits']
    obj(limits, ('wall_seconds', 'address_space_bytes', 'cpu_seconds', 'input_bytes', 'log_bytes_per_stream', 'lean_worker_threads'), 'limits')
    for key in set(limits) - {'wall_seconds'}:
        require(type(limits[key]) is int and limits[key] > 0, 'invalid limit: ' + key)
    require(type(limits['wall_seconds']) in (int, float) and math.isfinite(limits['wall_seconds']) and limits['wall_seconds'] > 0, 'invalid wall limit')
    require(limits['cpu_seconds'] == math.ceil(limits['wall_seconds']) + 1 and limits['lean_worker_threads'] == 1, 'inconsistent CPU/worker limits')
    require(r['runtime_environment'] == RUNTIME_ENV, 'runtime environment differs from supported profile')
    # Recorded paths are checked as metadata, never followed. Local filenames are fixed.
    run = receipt_path.parent
    obj(r['snapshots'], ('passport', 'certificate'), 'snapshots')
    for label, expected in (('passport', passport_hash), ('certificate', certificate_hash)):
        item = r['snapshots'][label]
        obj(item, ('path', 'bytes', 'sha256_before', 'sha256_after'), 'snapshot')
        require(item['path'] == str(Path(r['run_directory']) / f'snapshot_{label}.bin'), 'recorded snapshot path mismatch')
        data = read_file(run / f'snapshot_{label}.bin', min(limits['input_bytes'], 1024**2))
        require(type(item['bytes']) is int and item['bytes'] == len(data), 'snapshot size mismatch')
        require(sha(data) == expected == item['sha256_before'] == item['sha256_after'], 'snapshot/expected hash mismatch: ' + label)
    require(r['command'] == [pin['artifacts']['binary']['path'], '--passport', r['snapshots']['passport']['path'], '--certificate', r['snapshots']['certificate']['path']], 'recorded command mismatch')
    logs = {}
    for label in ('stdout', 'stderr'):
        data = read_file(run / (label + '.bin'), min(limits['log_bytes_per_stream'], 1024**2))
        require(len(data) < limits['log_bytes_per_stream'], 'normal receipt reached output budget')
        require(type(r['raw_' + label + '_base64']) is str, 'invalid encoded log')
        require(base64.b64encode(data).decode('ascii') == r['raw_' + label + '_base64'], 'raw log/Base64 mismatch')
        require(sha(data) == r[label + '_sha256'], 'log hash mismatch')
        logs[label] = data
    require(not logs['stderr'], 'normal verdict has stderr')
    response = parse(logs['stdout'])
    obj(response, ('protocol_version', 'evidence_kind', 'verdict'), 'stdout')
    require(response == dict(protocol_version=PROTOCOL, evidence_kind='compiled_execution', verdict=r['status']), 'stdout verdict mismatch')
    return dict(ok=True, status='ARCHIVE_CONSISTENT', evidence_kind='compiled_execution',
                recorded_verdict=r['status'], receipt_sha256=sha(raw_receipt), pin_sha256=sha(pin_bytes),
                execution_replayed=False, authenticated_execution=False, kernel_proof=False)


def audit(receipt: Path, pin: Path, passport_sha256: str, certificate_sha256: str):
    try:
        return _audit(Path(receipt), Path(pin), passport_sha256, certificate_sha256)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        return dict(ok=False, status='ARCHIVE_REJECTED', error=str(exc), execution_replayed=False,
                    authenticated_execution=False, kernel_proof=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('receipt', 'pin'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('passport-sha256', 'certificate-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    result = audit(args.receipt, args.pin, args.passport_sha256, args.certificate_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
