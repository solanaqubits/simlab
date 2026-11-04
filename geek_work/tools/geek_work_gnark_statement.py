#!/usr/bin/env python3
"""Prepare expected public inputs for the bounded gnark pilot; NOT a proof verifier."""
import argparse
from pathlib import Path
import geek_work_proof_contract as contract

k = contract.k
SPEC = b'GeekWork bounded-convolution-v1: h[3]*q[3]=t[5]; h,q:uint8;t:uint18; Q denominator=1; context:sha256-hi128-lo128; test setup only.\n'
PARAMETERS = b'gnark-v0.16.4;groth16-bn254;local-test-setup;not-post-quantum;not-onchain\n'
FILES = dict(specification='specification.txt', program='circuit.bin', input='input.json',
             public_output='output.json', verifier='verifier.bin', parameters='parameters.txt')


def expected_statement(raw, anchor, artifacts):
    binding = contract.bind(raw, anchor, artifacts)
    request = contract.validate(raw, anchor)
    k.require(request['claim'] == 'bounded-convolution-v1', 'unsupported_claim')
    k.require(request['backend'] == dict(id='gnark', version='v0.16.4',
                                        proof_system='groth16-bn254'), 'unsupported_backend')
    k.require(request['target']['ecosystem'] == 'offline', 'offline_only')
    k.require(artifacts['specification'] == SPEC, 'unsupported_specification')
    k.require(artifacts['parameters'] == PARAMETERS, 'unsupported_parameters')
    h = k.strict_json(artifacts['input']); k.obj(h, {'h'})
    t = k.strict_json(artifacts['public_output']); k.obj(t, {'t'})
    for value, size, bound in ((h['h'], 3, 256), (t['t'], 5, 1 << 18)):
        k.require(type(value) is list and len(value) == size, 'coefficient_count')
        k.require(all(type(x) is int and 0 <= x < bound for x in value), 'coefficient_range')
    return dict(h=h['h'], t=t['t'], context=binding['public_input_limbs_hex'],
                verifier_sha256=request['artifacts']['verifier'],
                program_sha256=request['artifacts']['program'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--expected-request-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        raw = k.bounded(a.bundle / 'request.json')
        artifacts = {name: k.bounded(a.bundle / filename) for name, filename in FILES.items()}
        result = expected_statement(raw, a.expected_request_sha256, artifacts)
        data = k.canonical(result) + b'\n'
        k.write_new(a.output, data)
        print(k.canonical(dict(status='expected_statement_prepared',
                               expected_statement_sha256=k.digest(data),
                               cryptographic_verification=False)).decode())
        return 0
    except (k.Refusal, OSError, ValueError, TypeError, KeyError) as err:
        print(k.canonical(dict(status='refused', reason=str(err))).decode())
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
