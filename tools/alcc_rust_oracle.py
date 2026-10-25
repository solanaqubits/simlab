"""Pinned, bounded second oracle for normalization; Linux execution adapter.

An unavailable oracle never produces a mathematical rejection. Build hashes
provide traceability, not authentication or a formal proof of native execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'tools/alcc_fraction_oracle'
SOURCES = ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', 'src/main.rs')
PROTOCOL = 'ALCC-FRACTION-ORACLE-1'
TOOLCHAIN = '1.95.0'
MAX_OUTPUT = 2 * 1024**2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: sha(CRATE / name) for name in SOURCES}


def cargo_path():
    path = os.environ.get('CARGO') or shutil.which('cargo')
    if not path:
        path = Path.home() / '.cargo/bin/cargo'
    return str(Path(path).absolute())


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = source_hashes()
    cargo = cargo_path()
    env = dict(os.environ)
    for name in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTC_WRAPPER',
                 'RUSTC_WORKSPACE_WRAPPER', 'RUSTC', 'CARGO_BUILD_TARGET'):
        env.pop(name, None)
    cmd = [cargo, '+' + TOOLCHAIN, 'build', '--offline', '--locked', '--release',
           '--jobs', '1', '--target-dir', str(output / 'target')]
    with (output / 'build.log').open('wb') as log:
        subprocess.run(cmd, cwd=CRATE, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=120)
    if sources != source_hashes():
        raise ValueError('oracle source changed during build')
    binary = output / 'alcc-fraction-oracle'
    shutil.copyfile(output / 'target/release/alcc-fraction-oracle', binary)
    binary.chmod(0o500)
    rustc = str(Path(cargo).with_name('rustc'))
    manifest = dict(schema='ALCC-RUST-ORACLE-BUILD-1', toolchain=TOOLCHAIN,
                    protocol=PROTOCOL, sources=sources, command=cmd,
                    rustc_version=subprocess.check_output(
                        [rustc, '+' + TOOLCHAIN, '-Vv'], env=env, text=True),
                    cargo_version=subprocess.check_output(
                        [cargo, '+' + TOOLCHAIN, '-Vv'], env=env, text=True),
                    binary_sha256=sha(binary), build_log_sha256=sha(output / 'build.log'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return sha(output / 'manifest.json')


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


class OracleNotChecked(RuntimeError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__('second oracle not checked: ' + receipt['status'])


class OracleMismatch(ValueError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__('Rust and Python normalization references disagree')


class RustOracle:
    def __init__(self, directory, expected_manifest_sha256):
        self.directory = Path(directory).resolve()
        self.binary = self.directory / 'alcc-fraction-oracle'
        self.expected_manifest = expected_manifest_sha256
        self._verify_build()

    def _verify_build(self):
        if sha(self.directory / 'manifest.json') != self.expected_manifest:
            raise ValueError('oracle manifest pin mismatch')
        m = json.loads((self.directory / 'manifest.json').read_text(),
                       object_pairs_hook=unique_object)
        if (m['schema'] != 'ALCC-RUST-ORACLE-BUILD-1' or m['protocol'] != PROTOCOL
                or m['toolchain'] != TOOLCHAIN or m['sources'] != source_hashes()
                or m['binary_sha256'] != sha(self.binary)
                or m['build_log_sha256'] != sha(self.directory / 'build.log')):
            raise ValueError('oracle build/source binding mismatch')
        return m

    def check(self, path, expected):
        """Compare two references; preserve refusal independently of mismatch."""
        path = Path(path).resolve()
        m = self._verify_build()
        receipt = dict(protocol=PROTOCOL, evidence_kind='second_oracle_execution',
                       build_manifest_sha256=self.expected_manifest,
                       binary_sha256=m['binary_sha256'], adapter_sha256=sha(__file__),
                       status='EXECUTION_ERROR', checked=False, input_sha256=None,
                       limits=dict(wall_seconds=5, cpu_seconds=2, memory_bytes=256*1024**2,
                                   input_bytes=1024**2, terms=4096, output_bytes=MAX_OUTPUT))
        try:
            if path.stat().st_size > 1024**2:
                receipt['status'] = 'INPUT_LIMIT'
                raise OracleNotChecked(receipt)
            receipt['input_sha256'] = sha(path)
            with tempfile.TemporaryDirectory(prefix='alcc-oracle-') as tmp:
                out, err = Path(tmp) / 'stdout', Path(tmp) / 'stderr'
                with out.open('wb') as stdout, err.open('wb') as stderr:
                    try:
                        p = subprocess.run([str(self.binary), str(path)],
                                           stdout=stdout, stderr=stderr, timeout=5,
                                           preexec_fn=limits)
                        receipt['exit_code'] = p.returncode
                    except subprocess.TimeoutExpired:
                        receipt['status'] = 'TIMEOUT'
                    except OSError as exc:
                        receipt['diagnostic'] = str(exc)
                receipt['stdout'] = out.read_bytes()[:MAX_OUTPUT].decode('utf-8', 'replace')
                receipt['stderr'] = err.read_bytes()[:MAX_OUTPUT].decode('utf-8', 'replace')
                if receipt.get('exit_code') is None:
                    raise OracleNotChecked(receipt)
                if out.stat().st_size >= MAX_OUTPUT or err.stat().st_size >= MAX_OUTPUT:
                    receipt['status'] = 'OUTPUT_LIMIT'
                    raise OracleNotChecked(receipt)
            self._verify_build()
            if sha(path) != receipt['input_sha256']:
                receipt['status'] = 'INPUT_CHANGED'
                raise OracleNotChecked(receipt)
            code = receipt['exit_code']
            if code < 0:
                receipt['status'] = 'EXEC_CRASH'
                raise OracleNotChecked(receipt)
            row = json.loads(receipt['stdout'], object_pairs_hook=unique_object)
            statuses = {0: 'OK', 2: 'INVALID_INPUT', 3: 'RANGE_EXCEEDED',
                        4: 'INPUT_LIMIT', 5: 'IO_ERROR'}
            keys = {'protocol', 'status', 'reference'} if code == 0 else {'protocol', 'status'}
            if (type(row) is not dict or set(row) != keys or row['protocol'] != PROTOCOL
                    or code not in statuses or row['status'] != statuses[code]):
                raise ValueError('oracle protocol/exit mismatch')
            if code:
                receipt['status'] = statuses[code]
                raise OracleNotChecked(receipt)
            actual = row['reference']
            if type(actual) is not list or any(
                type(t) is not list or len(t) != 3 or type(t[0]) is not list
                or len(t[0]) != 3 or any(type(x) is not int or x < 0 for x in t[0])
                or type(t[1]) is not str or type(t[2]) is not str for t in actual
            ):
                raise ValueError('oracle reference schema')
            receipt['reference'] = actual
            if actual != expected:
                receipt['status'] = 'REFERENCE_MISMATCH'
                raise OracleMismatch(receipt)
            receipt.update(status='MATCH', checked=True)
            return receipt
        except (OracleMismatch, OracleNotChecked):
            raise
        except (ValueError, KeyError, TypeError, OSError) as exc:
            receipt['status'] = 'PROTOCOL_OR_IO_ERROR'
            receipt['diagnostic'] = str(exc)
            raise OracleNotChecked(receipt) from exc


def replay(archive, oracle, output):
    from tools.alcc_normalization_bench import corpus, reference, validate_run
    archive, output = Path(archive), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='ALCC-SECOND-ORACLE-REPLAY-1', status='running', cases={},
                  native_lean_executions=0, scope='Fixed-corpus archive comparison, not new timings')
    try:
        for name, terms in corpus().items():
            path = archive / (name + '.txt')
            selected = ''.join(' '.join(map(str, t)) + '\n' for t in terms).encode()
            if path.read_bytes() != selected:
                raise ValueError('archive differs from independently selected corpus: ' + name)
            expected = reference(terms)
            report['cases'][name] = oracle.check(path, expected)
            stdout = archive / (name + '.stdout')
            validate_run(stdout.read_text(), expected)
            report['cases'][name].update(archived_outputs=22, stdout_sha256=sha(stdout))
        report.update(status='passed', archived_outputs=22 * len(report['cases']))
    except (OracleNotChecked, OracleMismatch) as exc:
        report.update(status='not_checked' if isinstance(exc, OracleNotChecked) else 'mismatch',
                      oracle_failure=exc.receipt)
        raise
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='op', required=True)
    b = sub.add_parser('build'); b.add_argument('--output', type=Path, required=True)
    r = sub.add_parser('replay')
    for name in ('archive', 'build', 'output'):
        r.add_argument('--' + name, type=Path, required=True)
    r.add_argument('--manifest-sha256', required=True)
    a = p.parse_args()
    if a.op == 'build':
        print(build(a.output))
    else:
        print(json.dumps(replay(a.archive, RustOracle(a.build, a.manifest_sha256), a.output)))


if __name__ == '__main__':
    main()
