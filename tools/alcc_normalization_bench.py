"""Bounded diagnostic for the separately proved Lean normalization candidate.

Original implementation; no upstream benchmark code is copied. This is not a
production ALCC benchmark, formal runtime proof, or statistical significance test.
"""
import argparse
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

PROTOCOL = 'ALCC-NORMALIZE-PILOT-1'


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


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))


def run(binary, output, lean_commit, build_log):
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
              'limits': {'address_space_bytes': 1024**3, 'cpu_seconds_per_case': 10,
                         'wall_seconds_per_case': 15, 'total_wall_seconds': 180},
              'scope': 'Normalization plus forcing fold only; no production speedup claim.',
              'status': 'running'}
    start = time.monotonic()
    try:
        for name, terms in corpus().items():
            if time.monotonic() - start > 180:
                raise TimeoutError('total budget exhausted')
            path = output / (name + '.txt')
            path.write_text(''.join(' '.join(map(str, term)) + '\n' for term in terms))
            input_hash = sha(path)
            environment = dict(os.environ, LEAN_NUM_THREADS='0', LEAN_STACK_SIZE_KB='8192')
            process = subprocess.run([str(binary), str(path)], capture_output=True,
                                     timeout=15, preexec_fn=limits, env=environment)
            (output / (name + '.stdout')).write_bytes(process.stdout)
            (output / (name + '.stderr')).write_bytes(process.stderr)
            if process.returncode != 0:
                raise RuntimeError(f'{name}: execution failure {process.returncode}')
            summary = validate_run(process.stdout.decode('utf-8'), reference(terms))
            if sha(path) != input_hash:
                raise ValueError('input changed during execution')
            report['cases'][name] = {'input_sha256': input_hash, 'terms': len(terms),
                                     'command': [str(binary), str(path)],
                                     'exit_code': process.returncode, 'timings': summary}
        if sha(binary) != before:
            raise ValueError('binary changed during execution')
        report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - start
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lean-commit', required=True)
    parser.add_argument('--build-log', type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.output, args.lean_commit, args.build_log)
