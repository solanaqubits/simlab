#!/usr/bin/env python3
"""Bind a proof request to local artifacts. Never verifies or generates ZK proofs."""
import argparse
from pathlib import Path
import re

import knowledge as k

SCHEMA = 'geek-work-proof-request-1'
ARTIFACTS = ('specification', 'program', 'input', 'public_output', 'verifier', 'parameters')
BACKENDS = ('sp1', 'risc0', 'openvm', 'cairo-stwo', 'noir-barretenberg', 'gnark')
SYSTEMS = ('native-stark', 'groth16-bn254', 'plonk-bn254', 'honk-bn254')
HEX = re.compile(r'[0-9a-f]{64}')
DOMAIN = b'GeekWork/ProofRequest/v1\x00'
MAX_REQUEST_BYTES = 32 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def digest_limbs(digest):
    """Lossless high/low u128, big endian; no reduction modulo any field."""
    k.require(type(digest) is str and HEX.fullmatch(digest), 'digest_format')
    return [int(digest[:32], 16), int(digest[32:], 16)]


def limbs_digest(limbs):
    k.require(type(limbs) is list and len(limbs) == 2, 'limb_count')
    k.require(all(type(x) is int and 0 <= x < 2**128 for x in limbs), 'limb_range')
    return ''.join(f'{x:032x}' for x in limbs)


def label(value):
    k.require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}', value),
              'identifier')


def validate(raw, anchor):
    k.require(type(raw) is bytes and len(raw) <= MAX_REQUEST_BYTES, 'request_size')
    k.require(type(anchor) is str and HEX.fullmatch(anchor), 'anchor_format')
    k.require(k.digest(raw) == anchor, 'request_anchor')
    r = k.strict_json(raw)
    k.obj(r, {'schema', 'claim', 'artifacts', 'backend', 'target', 'nonce', 'requirements'})
    k.require(r['schema'] == SCHEMA, 'schema')
    label(r['claim'])
    k.obj(r['artifacts'], set(ARTIFACTS))
    for digest in r['artifacts'].values():
        digest_limbs(digest)
    k.obj(r['backend'], {'id', 'version', 'proof_system'})
    k.require(r['backend']['id'] in BACKENDS, 'backend')
    label(r['backend']['version'])
    k.require(r['backend']['proof_system'] in SYSTEMS, 'proof_system')
    k.obj(r['target'], {'ecosystem', 'network', 'verifier_id', 'application_id'})
    k.require(r['target']['ecosystem'] in ('offline', 'ethereum', 'solana', 'starknet'),
              'ecosystem')
    for name in ('network', 'verifier_id', 'application_id'):
        label(r['target'][name])
    digest_limbs(r['nonce'])
    k.obj(r['requirements'], {'zero_knowledge', 'post_quantum'})
    k.require(all(type(x) is bool for x in r['requirements'].values()), 'requirements')
    # A syntactic pairing profile must not masquerade as a post-quantum one.
    k.require(not (r['requirements']['post_quantum'] and
                   r['backend']['proof_system'] != 'native-stark'), 'pairing_not_post_quantum')
    return r


def bind(raw, anchor, artifacts):
    r = validate(raw, anchor)
    k.require(type(artifacts) is dict and set(artifacts) == set(ARTIFACTS), 'artifacts')
    total = 0
    lengths = {}
    for name in ARTIFACTS:
        content = artifacts[name]
        k.require(type(content) is bytes and 0 < len(content) <= MAX_ARTIFACT_BYTES,
                  'artifact_size:' + name)
        total += len(content)
        k.require(total <= MAX_TOTAL_BYTES, 'total_bytes')
        k.require(k.digest(content) == r['artifacts'][name], 'artifact_hash:' + name)
        lengths[name] = len(content)
    commitment = k.digest(DOMAIN + k.canonical(r))
    return dict(schema='geek-work-proof-binding-1', status='request_bound',
                request_file_sha256=anchor, statement_sha256=commitment,
                public_input_encoding='sha256-hi128-lo128-big-endian-v1',
                public_input_limbs_hex=[f'{x:032x}' for x in digest_limbs(commitment)], artifact_bytes=lengths,
                tool_pins={Path(p).name: k.digest(Path(p).read_bytes())
                           for p in (__file__, k.__file__)},
                proof_generated=False, cryptographic_verification=False,
                zero_knowledge_verified=False, post_quantum_verified=False,
                chain_compatibility_verified=False, deployment_performed=False,
                privacy='Hashes are binding identifiers, not hiding commitments; report is private by default.',
                limits='Only local byte binding and deterministic encoding. No proof backend, '
                       'version attestation, program execution, semantic equivalence or replay registry. '
                       'Requirements are requested properties, not established guarantees.')


def verify(report, report_anchor, raw, anchor, artifacts):
    k.require(type(report_anchor) is str and HEX.fullmatch(report_anchor), 'report_anchor_format')
    k.require(k.digest(k.canonical(report)) == report_anchor, 'report_anchor')
    expected = bind(raw, anchor, artifacts)
    k.require(report == expected, 'binding_changed')
    return dict(schema='geek-work-proof-binding-replay-1', status='binding_reproduced',
                report_sha256=report_anchor, cryptographic_verification=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bind', 'verify'))
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected-request-sha256', required=True)
    for name in ARTIFACTS:
        parser.add_argument('--' + name.replace('_', '-'), dest=name, type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--report-anchor')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    try:
        raw = k.bounded(a.request)
        validate(raw, a.expected_request_sha256)
        artifacts = {}
        total = 0
        for name in ARTIFACTS:
            content = k.bounded(getattr(a, name))
            total += len(content)
            k.require(total <= MAX_TOTAL_BYTES, 'total_bytes')
            artifacts[name] = content
        if a.action == 'bind':
            k.require(a.report is None and a.report_anchor is None, 'unexpected_report')
            result = bind(raw, a.expected_request_sha256, artifacts)
        else:
            k.require(a.report is not None and a.report_anchor is not None, 'report_required')
            result = verify(k.load(a.report), a.report_anchor, raw,
                            a.expected_request_sha256, artifacts)
        k.write_new(a.output, k.canonical(result) + b'\n')
        print(k.canonical(dict(status=result['status'],
                               report_sha256=k.digest(k.canonical(result)),
                               cryptographic_verification=False)).decode())
        return 0
    except (k.Refusal, OSError, ValueError, TypeError, KeyError) as err:
        print(k.canonical(dict(status='refused', reason=str(err))).decode())
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
