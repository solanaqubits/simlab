"""Opt-in local runner. No NumPy import, services, network calls or proof claims."""
import datetime
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .protocol import (SCHEMA, LIMITS, STATUSES, sha, read_json, write_json,
                       implementation_manifest, implementation_hash)


def execute(command, directory, environment, timeout):
    """Kill the worker process group on wall timeout; preserve capped file logs."""
    with (directory/'stdout.log').open('wb') as out, (directory/'stderr.log').open('wb') as err:
        proc = subprocess.Popen(command, cwd=directory, env=environment,
                                stdout=out, stderr=err, start_new_session=True)
        try:
            return proc.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
            return proc.returncode, True


def run_request(input_path, output_dir, python=sys.executable):
    root = Path(output_dir).resolve()
    # Deliberately refuse reused directories; never overwrite prior evidence.
    root.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    manifest = implementation_manifest()
    receipt = {'schema': SCHEMA, 'evidence_kind': 'numerical_simulation',
               'status': 'EXEC_ERROR', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'limits': LIMITS, 'implementation_files': manifest,
               'implementation_sha256': implementation_hash(),
               'source_origin': read_json((Path(__file__).parent/'UPSTREAM.json').read_bytes()),
               'python_executable': str(Path(python).resolve()), 'exit_code': None,
               'request_sha256': None, 'input_integrity': False,
               'implementation_integrity': False, 'artifacts': {}}
    try:
        with Path(input_path).open('rb') as f:
            data = f.read(LIMITS['max_input_bytes']+1)
        if len(data) > LIMITS['max_input_bytes']:
            receipt.update(status='INVALID_INPUT', detail='Input exceeds 1 MiB; no truncated snapshot recorded')
        else:
            (root/'request.json').write_bytes(data)
            (root/'request.json').chmod(0o400)
            receipt['request_sha256'] = sha(data)
            # -I ignores PYTHONPATH, user-site and current directory. Only our
            # explicitly selected implementation tree is added to worker imports.
            project = str(Path(__file__).resolve().parent.parent)
            code = 'import sys; sys.path.insert(0, '+repr(project)+'); from simlab_quantum.worker import main; sys.exit(main(sys.argv[1]))'
            command = [str(python), '-I', '-B', '-c', code, str(root)]
            env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT')}
            env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       NUMEXPR_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', HOME=str(root), TMPDIR=str(root))
            receipt['command'] = command
            rc, timed_out = execute(command, root, env, LIMITS['wall_seconds'])
            receipt['exit_code'] = rc
            if timed_out:
                receipt.update(status='EXEC_TIMEOUT', detail='Host wall deadline; worker group killed')
            elif rc < 0:
                # SIGKILL alone does not establish OOM.
                receipt.update(status='EXEC_ERROR', detail=f'Worker terminated by signal {-rc}; no OOM inference')
            else:
                try:
                    response = read_json((root/'stdout.log').read_bytes())
                    if (not isinstance(response, dict) or set(response) != {'schema', 'status', 'detail'}
                        or response['schema'] != SCHEMA or response['status'] not in STATUSES
                        or not isinstance(response['detail'], str)
                        or rc != (0 if response['status'] == 'COMPLETED' else 2)):
                        raise ValueError('Worker protocol/exit disagreement')
                    receipt.update(status=response['status'], detail=response['detail'])
                    if receipt['status'] == 'COMPLETED':
                        result = read_json((root/'result.json').read_bytes())
                        if result['schema'] != SCHEMA or result['evidence_kind'] != 'numerical_simulation' or not (root/'state.npy').is_file():
                            raise ValueError('Missing numerical output')
                except (ValueError, KeyError, TypeError, OSError) as e:
                    receipt.update(status='EXEC_ERROR', detail='Worker protocol failure: '+str(e))
    except OSError as e:
        receipt.update(status='IO_ERROR', detail=str(e))
    finally:
        snap = root/'request.json'
        if snap.exists():
            receipt['input_integrity'] = sha(snap.read_bytes()) == receipt['request_sha256']
        receipt['implementation_integrity'] = implementation_manifest() == manifest
        if not receipt['implementation_integrity'] or (receipt['request_sha256'] and not receipt['input_integrity']):
            receipt.update(status='INTEGRITY_ERROR', detail='Input or implementation changed during execution')
        receipt['elapsed_seconds'] = time.monotonic()-start
        receipt['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt['artifacts'] = {name: sha((root/name).read_bytes()) for name in
                                ['request.json','stdout.log','stderr.log','result.json','state.npy']
                                if (root/name).is_file()}
        write_json(root/'receipt.json', receipt)
    return receipt


def audit_archive(directory, expected_request_sha256, expected_implementation_sha256):
    """Offline consistency only; pins supplied independently by the caller."""
    root = Path(directory)
    r = read_json((root/'receipt.json').read_bytes())
    if (r['schema'] != SCHEMA or r['evidence_kind'] != 'numerical_simulation'
        or r['status'] != 'COMPLETED' or r['exit_code'] != 0
        or not r['input_integrity'] or not r['implementation_integrity']):
        raise ValueError('Only complete, internally consistent numerical runs are eligible')
    if r['request_sha256'] != expected_request_sha256 or r['implementation_sha256'] != expected_implementation_sha256:
        raise ValueError('Expected input/implementation pin mismatch')
    if sha(__import__('json').dumps(r['implementation_files'], sort_keys=True).encode()) != expected_implementation_sha256:
        raise ValueError('Implementation manifest mismatch')
    if set(r['artifacts']) != {'request.json','stdout.log','stderr.log','result.json','state.npy'}:
        raise ValueError('Unexpected artifact set')
    for name, digest in r['artifacts'].items():
        p = root/name
        if p.is_symlink() or sha(p.read_bytes()) != digest:
            raise ValueError('Artifact integrity failure: '+name)
    if r['artifacts']['request.json'] != expected_request_sha256:
        raise ValueError('Snapshot pin mismatch')
    response = read_json((root/'stdout.log').read_bytes())
    if response != {'schema': SCHEMA, 'status': 'COMPLETED', 'detail': ''}:
        raise ValueError('Worker response mismatch')
    request = read_json((root/'request.json').read_bytes())
    result = read_json((root/'result.json').read_bytes())
    from .protocol import validate_request
    validate_request(request)
    if (result['schema'] != SCHEMA or result['evidence_kind'] != 'numerical_simulation'
        or result['state_artifact'] != 'state.npy' or result['dtype'] != 'complex128'
        or result['bit_order'] != 'q0_most_significant'):
        raise ValueError('Numerical result metadata disagreement')
    def contains(actual, expected):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and contains(actual[k],v) for k,v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual)==len(expected) and all(contains(a,b) for a,b in zip(actual,expected))
        return actual == expected
    if not contains(result['result']['circuit'],request['circuit']) or not contains(result['result']['config'],request['config']):
        raise ValueError('Request and recorded result disagree')
    n = request['circuit']['n_qubits']
    shape = [2**n] * (2 if request['config']['mode']=='density_matrix' else 1)
    counts = result['result']['counts']
    if (result['shape'] != shape or not isinstance(counts,dict)
        or any(len(k)!=n or set(k)-{'0','1'} or type(v) is not int or v<0 for k,v in counts.items())
        or sum(counts.values()) != request['config']['shots']):
        raise ValueError('Recorded shape/count disagreement')
    return {'status': 'ARCHIVE_CONSISTENT', 'evidence_kind': 'numerical_simulation',
            'claim': 'Byte integrity and receipt consistency only; no independent numerical recomputation or execution authentication'}
