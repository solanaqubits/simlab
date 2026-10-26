"""Bounded, host-side supervision of a newly owned local Docker container.

Execution evidence only: no certificate verdict or operator authentication.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

SCHEMA = 'simlab-container-watchdog-1'
LABEL = 'org.simlab.watchdog.run'
STATUSES = {'EXEC_COMPLETED', 'EXEC_NONZERO_EXIT', 'EXEC_TIMEOUT', 'EXEC_OOM',
            'EXEC_CRASH', 'EXEC_DOCKER_ERROR', 'EXEC_CLEANUP_ERROR', 'EXEC_CANCELLED'}


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def strict_json(text):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('Duplicate JSON key: ' + k)
            out[k] = v
        return out
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def validate_spec(spec, *, check_bind_sources=True):
    fields = {'image', 'command', 'timeout_seconds', 'memory_bytes', 'cpus',
              'pids', 'tmpfs_bytes', 'binds'}
    if not isinstance(spec, dict) or set(spec) != fields:
        raise ValueError('Spec must contain exactly: ' + ', '.join(sorted(fields)))
    if not isinstance(spec['image'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', spec['image']):
        raise ValueError('A local immutable image ID is required')
    cmd = spec['command']
    if (not isinstance(cmd, list) or not 1 <= len(cmd) <= 128 or
        not all(isinstance(x, str) and x and '\0' not in x and len(x) <= 8192 for x in cmd)):
        raise ValueError('Invalid argv')
    for key, low, high in [('timeout_seconds', .1, 3600), ('cpus', .1, 4)]:
        v = spec[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('Invalid ' + key)
    for key, low, high in [('memory_bytes', 16 << 20, 12 << 30), ('pids', 1, 512),
                           ('tmpfs_bytes', 1 << 20, 256 << 20)]:
        if type(spec[key]) is not int or not low <= spec[key] <= high:
            raise ValueError('Invalid ' + key)
    if spec['tmpfs_bytes'] > spec['memory_bytes']:
        raise ValueError('tmpfs must fit the total memory cap')
    if not isinstance(spec['binds'], list) or len(spec['binds']) > 16:
        raise ValueError('Invalid binds')
    targets = set()
    for b in spec['binds']:
        if not isinstance(b, dict) or set(b) != {'source', 'target', 'read_only'} or type(b['read_only']) is not bool:
            raise ValueError('Invalid bind')
        for k in ('source', 'target'):
            if not isinstance(b[k], str) or not b[k].startswith('/') or any(c in b[k] for c in ',\n\0') or '..' in Path(b[k]).parts:
                raise ValueError('Bind paths must be absolute and unambiguous')
        if not b['target'].startswith(('/work/', '/inputs/', '/outputs/')) or b['target'] in targets:
            raise ValueError('Bind targets must be unique under /work, /inputs or /outputs')
        source = Path(b['source'])
        if check_bind_sources and (not source.exists() or str(source.resolve()) != str(source) or not (source.is_file() or source.is_dir())):
            raise ValueError('Bind source must be an existing resolved file or directory')
        targets.add(b['target'])
    return spec


class DockerError(RuntimeError):
    pass


class Docker:
    def __init__(self):
        self.calls = []

    def call(self, args, timeout=5):
        command = ['docker', '--host', 'unix:///var/run/docker.sock', *args]
        start = time.monotonic()
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL)
            row = {'argv': command, 'returncode': p.returncode, 'stdout': p.stdout,
                   'stderr': p.stderr, 'timed_out': False}
        except subprocess.TimeoutExpired:
            row = {'argv': command, 'returncode': None, 'stdout': '',
                   'stderr': 'Docker client deadline exceeded', 'timed_out': True}
        except OSError as e:
            row = {'argv': command, 'returncode': None, 'stdout': '',
                   'stderr': str(e), 'timed_out': False}
        row['elapsed_seconds'] = time.monotonic() - start
        self.calls.append(row)
        return row

    def require(self, args, timeout=5):
        r = self.call(args, timeout)
        if r['returncode'] != 0:
            raise DockerError(r['stderr'])
        return r['stdout'].strip()

    def inspect(self, name, token):
        raw = self.require(['inspect', name])
        rows = strict_json(raw)
        if not isinstance(rows, list) or len(rows) != 1:
            raise DockerError('Invalid inspect response')
        row = rows[0]
        if row.get('Config', {}).get('Labels', {}).get(LABEL) != token:
            raise DockerError('Container ownership label mismatch')
        if not re.fullmatch(r'[0-9a-f]{64}', row.get('Id', '')):
            raise DockerError('Invalid container ID')
        return row


def create_args(spec, name, token):
    args = ['create', '--pull=never', '--name', name, '--label', LABEL + '=' + token,
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--user=65534:65534',
            '--restart=no', '--log-driver=none', '--memory=' + str(spec['memory_bytes']),
            '--memory-swap=' + str(spec['memory_bytes']), '--cpus=' + str(spec['cpus']),
            '--pids-limit=' + str(spec['pids']),
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=' + str(spec['tmpfs_bytes'])]
    for b in spec['binds']:
        args += ['--mount', 'type=bind,src=' + b['source'] + ',dst=' + b['target'] +
                 (',readonly' if b['read_only'] else '')]
    # Override any inherited image entrypoint: command is the complete argv.
    return [*args, '--entrypoint', spec['command'][0], spec['image'], *spec['command'][1:]]


def stopped(state):
    return (state.get('Running') is False and state.get('Pid') == 0 and
            state.get('Status') in ('exited', 'created') and state.get('Restarting') is False)


def supervise(spec, output, *, docker=None):
    """Own lifecycle; timeout is emitted only after independently inspecting stop.

    The execution deadline starts before Docker start, including start latency.
    Docker control/cleanup calls have separate bounded deadlines (5 seconds each).
    """
    validate_spec(spec)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    payload = canonical(spec)
    (output / 'spec.json').write_bytes(payload)
    d = docker or Docker()
    token = uuid.uuid4().hex
    name = 'simlab-watchdog-' + token
    receipt = {'schema': SCHEMA, 'evidence_kind': 'container_execution',
               'run_id': token, 'container_name': name, 'container_id': None,
               'spec_sha256': hashlib.sha256(payload).hexdigest(), 'image_id': spec['image'],
               'started_utc': datetime.now(timezone.utc).isoformat(),
               'status': 'EXEC_DOCKER_ERROR', 'deadline_exceeded': False,
               'termination_confirmed': False, 'removed': False, 'exit_code': None,
               'final_state': None, 'diagnostic': None, 'control_call_timeout_seconds': 5}
    start = time.monotonic()
    attempted_create = False
    owned = None
    try:
        image = d.require(['image', 'inspect', spec['image'], '--format', '{{.Id}}'])
        if image != spec['image']:
            raise DockerError('Image ID mismatch')
        attempted_create = True
        cid = d.require(create_args(spec, name, token))
        owned = d.inspect(name, token)
        if cid != owned['Id']:
            raise DockerError('Create/inspect identity mismatch')
        receipt['container_id'] = cid
        (output / 'container.json').write_bytes(canonical({'id': cid, 'name': name, 'run_id': token}))
        deadline = time.monotonic() + spec['timeout_seconds']
        d.require(['start', cid], timeout=min(5, spec['timeout_seconds']))
        while True:
            owned = d.inspect(cid, token)
            state = owned['State']
            if stopped(state):
                if state['Status'] != 'exited':
                    raise DockerError('Container has not executed')
                # A completed process remains completed even if the final inspect
                # crossed the deadline; a running container at deadline is killed.
                if state.get('OOMKilled') is True:
                    receipt['status'] = 'EXEC_OOM'
                elif state.get('ExitCode') == 0:
                    receipt['status'] = 'EXEC_COMPLETED'
                elif state.get('ExitCode') == 137:
                    receipt['status'] = 'EXEC_CRASH'
                else:
                    receipt['status'] = 'EXEC_NONZERO_EXIT'
                break
            if time.monotonic() >= deadline:
                receipt['deadline_exceeded'] = True
                receipt['status'] = 'EXEC_TIMEOUT'
                break
            time.sleep(min(.1, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        receipt['status'] = 'EXEC_CANCELLED'
        receipt['diagnostic'] = 'Host interrupted; bounded cleanup attempted'
    except (DockerError, OSError, ValueError, KeyError, TypeError) as e:
        receipt['diagnostic'] = str(e)
    finally:
        # Even an ambiguous create/start failure may have created a container.
        # Re-discover only our random name and demand its ownership label.
        if attempted_create:
            try:
                owned = d.inspect(name, token)
                receipt['container_id'] = owned['Id']
                if not stopped(owned['State']):
                    d.call(['kill', '--signal=KILL', owned['Id']])
                    # A racing normal exit can make kill fail. Inspect, never
                    # infer termination from either the client or its return code.
                    owned = d.inspect(owned['Id'], token)
                receipt['final_state'] = owned['State']
                receipt['exit_code'] = owned['State'].get('ExitCode')
                receipt['termination_confirmed'] = stopped(owned['State'])
                (output / 'final-inspect.json').write_bytes(canonical(owned))
                if not receipt['termination_confirmed']:
                    raise DockerError('Container termination is unconfirmed')
                d.require(['rm', owned['Id']])
                receipt['removed'] = True
            except (DockerError, OSError, ValueError, KeyError, TypeError) as e:
                receipt['status'] = 'EXEC_CLEANUP_ERROR'
                receipt['diagnostic'] = str(e)
        receipt['elapsed_seconds'] = time.monotonic() - start
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (output / 'docker-calls.json').write_bytes(canonical(d.calls))
        receipt['calls_sha256'] = hashlib.sha256((output / 'docker-calls.json').read_bytes()).hexdigest()
        receipt['final_inspect_sha256'] = (hashlib.sha256((output / 'final-inspect.json').read_bytes()).hexdigest()
                                         if (output / 'final-inspect.json').exists() else None)
        (output / 'receipt.json').write_bytes(canonical(receipt))
    return receipt


def audit(output):
    """Archive consistency only; not proof that the host logs are authentic."""
    output = Path(output)
    r = strict_json((output / 'receipt.json').read_text())
    if r['schema'] != SCHEMA or r['evidence_kind'] != 'container_execution' or r['status'] not in STATUSES:
        raise ValueError('Invalid receipt type/status')
    spec_bytes = (output / 'spec.json').read_bytes()
    spec = validate_spec(strict_json(spec_bytes), check_bind_sources=False)
    if hashlib.sha256(spec_bytes).hexdigest() != r['spec_sha256'] or spec['image'] != r['image_id']:
        raise ValueError('Spec hash/image mismatch')
    calls_bytes = (output / 'docker-calls.json').read_bytes()
    if hashlib.sha256(calls_bytes).hexdigest() != r['calls_sha256']:
        raise ValueError('Control log hash mismatch')
    calls = strict_json(calls_bytes)
    if not isinstance(calls, list) or not all(isinstance(c, dict) for c in calls):
        raise ValueError('Invalid control log')
    for key in ('deadline_exceeded', 'termination_confirmed', 'removed'):
        if type(r[key]) is not bool:
            raise ValueError('Invalid receipt boolean')
    if r['termination_confirmed']:
        raw = (output / 'final-inspect.json').read_bytes()
        final = strict_json(raw)
        if (hashlib.sha256(raw).hexdigest() != r['final_inspect_sha256'] or
            final['Id'] != r['container_id'] or final['Image'] != r['image_id'] or
            final['State'] != r['final_state'] or
            final['Config']['Labels'].get(LABEL) != r['run_id'] or not stopped(final['State'])):
            raise ValueError('Stop evidence mismatch')
    if r['status'] in {'EXEC_COMPLETED', 'EXEC_NONZERO_EXIT', 'EXEC_TIMEOUT', 'EXEC_CRASH', 'EXEC_OOM'}:
        if not r['termination_confirmed'] or not r['removed']:
            raise ValueError('Execution outcome without confirmed cleanup')
        if r['final_state']['Status'] != 'exited':
            raise ValueError('Container did not execute')
        code = r['final_state']['ExitCode']
        if type(code) is not int or r['exit_code'] != code:
            raise ValueError('Exit evidence mismatch')
        if r['status'] == 'EXEC_COMPLETED' and code != 0:
            raise ValueError('Exit mismatch')
        if r['status'] == 'EXEC_NONZERO_EXIT' and code in (0, 137):
            raise ValueError('Nonzero exit mismatch')
        if r['status'] == 'EXEC_CRASH' and (code != 137 or r['final_state']['OOMKilled']):
            raise ValueError('Crash evidence mismatch')
        if r['status'] == 'EXEC_OOM' and r['final_state']['OOMKilled'] is not True:
            raise ValueError('OOM without engine evidence')
        removal = ['docker', '--host', 'unix:///var/run/docker.sock', 'rm', r['container_id']]
        if not any(c.get('argv') == removal and c.get('returncode') == 0 for c in calls):
            raise ValueError('Missing removal acknowledgement')
    if r['status'] == 'EXEC_TIMEOUT' and r['deadline_exceeded'] is not True:
        raise ValueError('Timeout without deadline observation')
    if r['status'] == 'EXEC_TIMEOUT':
        kill = ['docker', '--host', 'unix:///var/run/docker.sock', 'kill', '--signal=KILL', r['container_id']]
        if not any(c.get('argv') == kill for c in calls):
            raise ValueError('Timeout without container kill attempt')
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='action', required=True)
    run = subs.add_parser('run'); run.add_argument('--spec', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    check = subs.add_parser('audit'); check.add_argument('output', type=Path)
    a = p.parse_args(argv)
    try:
        if a.action == 'audit':
            r = audit(a.output)
        else:
            r = supervise(strict_json(a.spec.read_text()), a.output)
            audit(a.output)
        print(json.dumps({'status': r['status'], 'receipt': str((a.output / 'receipt.json').resolve()),
                          'termination_confirmed': r['termination_confirmed'], 'removed': r['removed']}))
        if a.action == 'audit':
            return 0
        return {'EXEC_COMPLETED': 0, 'EXEC_TIMEOUT': 124, 'EXEC_CANCELLED': 130}.get(r['status'], 1)
    except (OSError, ValueError, KeyError, TypeError) as e:
        p.exit(1, 'Watchdog evidence error: ' + str(e) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
