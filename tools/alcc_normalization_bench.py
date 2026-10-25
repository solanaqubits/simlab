"""Bounded diagnostic for the separately proved Lean normalization candidate.

Original implementation; no upstream benchmark code is copied. This is not a
production ALCC benchmark, formal runtime proof, or statistical significance test.
"""
import argparse
from functools import partial
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import time

if __package__:
    from .alcc_rust_oracle import RustOracle, OracleNotChecked, OracleMismatch
else:
    from alcc_rust_oracle import RustOracle, OracleNotChecked, OracleMismatch

PROTOCOL = 'ALCC-NORMALIZE-PILOT-1'
LEGACY_PROFILE = 'legacy-as-1g'
ISOLATED_PROFILE = 'isolated-as-4g-memory-1g-v2'
PROFILES = {LEGACY_PROFILE: 1024**3, ISOLATED_PROFILE: 4 * 1024**3}


def cgroup_snapshot(root=Path('/sys/fs/cgroup')):
    return {name: (root / name).read_text().strip() for name in
            ('memory.max', 'memory.swap.max', 'memory.current', 'memory.peak',
             'memory.events', 'cpu.max', 'cpu.stat')}


def require_isolation(snapshot):
    """Fail closed if the requested cgroup-v2 limits are not observable."""
    if snapshot['memory.max'] != str(1024**3) or snapshot['memory.swap.max'] != '0':
        raise ValueError('expected 1 GiB cgroup memory and zero swap')
    quota, period = snapshot['cpu.max'].split()
    if quota == 'max' or int(period) <= 0 or not 0 < int(quota) <= int(period):
        raise ValueError('expected CPU quota at most one CPU')


def remaining_timeout(start, now):
    remaining = 180 - (now - start)
    if remaining <= 0:
        raise TimeoutError('total budget exhausted')
    return min(15, remaining)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corpus():
    return {
        'empty': [],
        'zero': [[0, 0, 0, 0, 1]],
        'rational': [[1, 0, 0, 1, 3], [1, 0, 0, 1, 6], [0, 1, 0, -7, 5]],
        'cancel': [[2, 1, 0, 2, 3], [2, 1, 0, -2, 3]],
        'unique32': [[i, 0, 0, i + 1, 7] for i in range(32)],
        'unique128': [[i, 0, 0, i + 1, 7] for i in range(128)],
        'duplicate128': [[i % 8, i % 3, 0, i % 11 - 5, 13] for i in range(128)],
        'cancel128': [[i, 0, 0, sign, 17] for i in range(64) for sign in (1, -1)],
        'large_rationals': [[i % 9, 0, 1, (2**40 + i) * (-1 if i % 2 else 1),
                             2**32 + 15] for i in range(64)],
    }


def reference(terms):
    """Independent exact accumulator; no Lean result is used as the oracle."""
    sums = {}
    for x, y, z, a, b in terms:
        key = (x, y, z)
        sums[key] = sums.get(key, Fraction()) + Fraction(a, b)
    return [[list(key), str(sums[key].numerator), str(sums[key].denominator)]
            for key in sorted(sums, reverse=True) if sums[key]]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def validate_run(stdout, expected):
    rows = [json.loads(line, object_pairs_hook=unique_object) for line in stdout.splitlines()]
    if len(rows) != 22:
        raise ValueError('expected 11 rounds with two variants')
    samples = {'baseline': [], 'cached': []}
    digest = sum(sum(t[0]) + int(t[2]) for t in expected)
    for index, row in enumerate(rows):
        round_no, position = divmod(index, 2)
        order = ['baseline', 'cached'] if round_no % 2 == 0 else ['cached', 'baseline']
        if set(row) != {'protocol', 'variant', 'elapsed_ns', 'force_digest', 'output'}:
            raise ValueError('invalid output schema')
        if row['protocol'] != PROTOCOL or row['variant'] != order[position]:
            raise ValueError('protocol or order mismatch')
        if type(row['elapsed_ns']) is not int or row['elapsed_ns'] < 0:
            raise ValueError('invalid elapsed time')
        if type(row['force_digest']) is not int or row['force_digest'] != digest:
            raise ValueError('invalid forced-result digest')
        if type(row['output']) is not list or any(
            type(t) is not list or len(t) != 3 or type(t[0]) is not list
            or len(t[0]) != 3 or any(type(x) is not int for x in t[0])
            or type(t[1]) is not str or type(t[2]) is not str for t in row['output']
        ):
            raise ValueError('invalid complete result schema')
        if row['output'] != expected:
            raise ValueError('complete result differs from exact reference')
        if round_no >= 3:
            samples[row['variant']].append(row['elapsed_ns'])
    return {name: {'samples_ns': values, 'median_ns': statistics.median(values)}
            for name, values in samples.items()}


def limits(address_space_bytes):
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))


def run(binary, output, lean_commit, build_log, resource_profile=LEGACY_PROFILE, oracle=None):
    address_space_bytes = PROFILES[resource_profile]
    binary = binary.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = sha(binary)
    report = {'protocol': PROTOCOL, 'evidence_kind': 'compiled_diagnostic',
              'lean_commit': lean_commit, 'runner_sha256': sha(__file__),
              'binary_sha256': before, 'build_log_sha256': sha(build_log),
              'platform': platform.platform(), 'cpu': platform.processor(),
              'lean_num_threads': 0,
              'lean_stack_size_kb': 8192,
              'cpuinfo_sha256': sha('/proc/cpuinfo'), 'cases': {},
              'resource_profile': resource_profile,
              'limits': {'address_space_bytes': address_space_bytes, 'cpu_seconds_per_case': 10,
                         'wall_seconds_per_case': 15, 'total_wall_seconds': 180},
              'scope': 'Normalization plus forcing fold only; no production speedup claim.',
              'status': 'running'}
    report['second_oracle_requested'] = oracle is not None
    start = time.monotonic()
    try:
        if resource_profile == ISOLATED_PROFILE:
            report['cgroup_before'] = cgroup_snapshot()
            require_isolation(report['cgroup_before'])
        for name, terms in corpus().items():
            path = output / (name + '.txt')
            path.write_text(''.join(' '.join(map(str, term)) + '\n' for term in terms))
            input_hash = sha(path)
            expected = reference(terms) if oracle is not None else None
            # Outside the Lean timing interval; refusal aborts qualification.
            oracle_receipt = oracle.check(path, expected) if oracle is not None else None
            environment = dict(os.environ, LEAN_NUM_THREADS='0', LEAN_STACK_SIZE_KB='8192')
            timeout = remaining_timeout(start, time.monotonic())
            try:
                process = subprocess.run([str(binary), str(path)], capture_output=True,
                                         timeout=timeout,
                                         preexec_fn=partial(limits, address_space_bytes),
                                         env=environment)
            except subprocess.TimeoutExpired as exc:
                (output / (name + '.stdout')).write_bytes(exc.stdout or b'')
                (output / (name + '.stderr')).write_bytes(exc.stderr or b'')
                raise
            (output / (name + '.stdout')).write_bytes(process.stdout)
            (output / (name + '.stderr')).write_bytes(process.stderr)
            if process.returncode != 0:
                raise RuntimeError(f'{name}: execution failure {process.returncode}')
            summary = validate_run(process.stdout.decode('utf-8'),
                                   expected if oracle is not None else reference(terms))
            if sha(path) != input_hash:
                raise ValueError('input changed during execution')
            report['cases'][name] = {'input_sha256': input_hash, 'terms': len(terms),
                                     'command': [str(binary), str(path)],
                                     'exit_code': process.returncode, 'timings': summary}
            if oracle_receipt is not None:
                report['cases'][name]['second_oracle'] = oracle_receipt
        if sha(binary) != before:
            raise ValueError('binary changed during execution')
        remaining_timeout(start, time.monotonic())
        if resource_profile == ISOLATED_PROFILE:
            report['cgroup_after'] = cgroup_snapshot()
            require_isolation(report['cgroup_after'])
        report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'failed'
        if isinstance(exc, (OracleNotChecked, OracleMismatch)):
            report['status'] = ('not_checked' if isinstance(exc, OracleNotChecked)
                                else 'oracle_mismatch')
            report['oracle_failure'] = exc.receipt
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if resource_profile == ISOLATED_PROFILE and 'cgroup_after' not in report:
            try:
                report['cgroup_after_failure'] = cgroup_snapshot()
            except OSError as exc:
                report['cgroup_read_error'] = str(exc)
        report['elapsed_seconds'] = time.monotonic() - start
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lean-commit', required=True)
    parser.add_argument('--build-log', type=Path, required=True)
    parser.add_argument('--resource-profile', choices=PROFILES, default=LEGACY_PROFILE)
    parser.add_argument('--rust-oracle-build', type=Path)
    parser.add_argument('--rust-oracle-manifest-sha256')
    args = parser.parse_args()
    if bool(args.rust_oracle_build) != bool(args.rust_oracle_manifest_sha256):
        parser.error('both Rust oracle build directory and manifest pin are required')
    oracle = (RustOracle(args.rust_oracle_build, args.rust_oracle_manifest_sha256)
              if args.rust_oracle_build else None)
    run(args.binary, args.output, args.lean_commit, args.build_log, args.resource_profile, oracle)
