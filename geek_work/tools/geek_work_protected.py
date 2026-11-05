#!/usr/bin/env python3
"""Host-owned exact-JSON evaluator for bounded, single-file Python candidates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import statistics
import subprocess
import sys
import time
import uuid

import geek_work_eval as ev
import geek_work_ledger as ledger

SCHEMA = 'geek-work-protected-plan-1'
DEFAULT_LIMITS = dict(wall_time_ms=3000, total_wall_time_ms=120000,
                      memory_bytes=268435456, pids=32, output_bytes=65536)
MAX_FILE = 1024 * 1024


def require(ok, why):
    if not ok:
        raise ValueError(why)


def blob(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'regular_file_required')
    with path.open('rb') as f:
        data = f.read(MAX_FILE + 1)
    require(len(data) <= MAX_FILE, 'file_too_large')
    return data


def parse(data):
    return json.loads(data, object_pairs_hook=ev.pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def pins():
    return {p.name: ev.digest(p.read_bytes()) for p in
            (Path(__file__), Path(ev.__file__), Path(ledger.__file__))}


def validate_corpus(corpus):
    require(isinstance(corpus, dict) and set(corpus) == {'schema', 'cases'} and
            corpus['schema'] == 'geek-work-tool-corpus-1', 'corpus_schema')
    rows = corpus['cases']
    require(isinstance(rows, list) and 1 <= len(rows) <= 100, 'case_count')
    seen = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'id', 'input', 'expected'}, 'case_schema')
        cid = row['id']
        require(isinstance(cid, str) and re.fullmatch('[a-z0-9-]{1,64}', cid) and cid not in seen,
                'case_id')
        seen.add(cid)
        for key in ('input', 'expected'):
            raw = ev.encoded(row[key])
            require(len(raw) <= 8192, 'case_payload_limit')
            parse(raw)  # Reject NaN/Infinity even for Python callers.
    return corpus


def validate_limits(limits):
    require(isinstance(limits, dict) and set(limits) == set(DEFAULT_LIMITS), 'limits_schema')
    bounds = dict(wall_time_ms=(50, 60000), total_wall_time_ms=(1000, 600000),
                  memory_bytes=(67108864, 2147483648), pids=(4, 128), output_bytes=(64, 1048576))
    for k, (lo, hi) in bounds.items():
        require(type(limits[k]) is int and lo <= limits[k] <= hi, 'limit:' + k)
    require(limits['total_wall_time_ms'] >= limits['wall_time_ms'], 'total_limit')


def make_plan(corpus, candidate, image, interpreter='/usr/local/bin/python3',
              repetitions=2, limits=None):
    validate_corpus(corpus)
    limits = dict(DEFAULT_LIMITS if limits is None else limits)
    validate_limits(limits)
    require(isinstance(image, str) and re.fullmatch('sha256:[0-9a-f]{64}', image), 'immutable_image_id_required')
    require(interpreter in ('/usr/bin/python3', '/usr/local/bin/python3'), 'interpreter_not_allowed')
    require(type(repetitions) is int and 1 <= repetitions <= 5, 'repetitions')
    require(isinstance(candidate, bytes) and 0 < len(candidate) <= MAX_FILE, 'candidate_size')
    return dict(schema=SCHEMA, corpus=corpus, corpus_sha256=ev.digest(ev.encoded(corpus)),
                candidate_sha256=ev.digest(candidate), image_id=image, interpreter=interpreter,
                repetitions=repetitions, limits=limits, evaluator=pins(),
                criterion='exact_json_all_cases_all_repetitions',
                isolation='fresh_docker_container_per_case',
                scope='Deterministic tool fixtures; no scientific truth, model review or speedup qualification')


def validate_plan(p, candidate):
    require(p == make_plan(p['corpus'], candidate, p['image_id'], p['interpreter'],
                          p['repetitions'], p['limits']), 'plan_or_evaluator_drift')


def capture(argv, data, timeout_ms, cap):
    """Bound both streams and stdin without blocking on a non-reading child."""
    started = time.monotonic_ns()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    out = {'stdout': bytearray(), 'stderr': bytearray()}
    pending = memoryview(data)
    issue = None
    with selectors.DefaultSelector() as sel:
        for stream, label in ((proc.stdout, 'stdout'), (proc.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            sel.register(stream, selectors.EVENT_READ, label)
        os.set_blocking(proc.stdin.fileno(), False)
        if pending:
            sel.register(proc.stdin, selectors.EVENT_WRITE, 'stdin')
        else:
            proc.stdin.close()
        try:
            while sel.get_map() or proc.poll() is None:
                remaining = timeout_ms / 1000 - (time.monotonic_ns() - started) / 1e9
                if remaining <= 0:
                    issue = 'EXEC_TIMEOUT'; break
                for key, _ in sel.select(min(remaining, .05)):
                    if key.data == 'stdin':
                        try:
                            pending = pending[os.write(key.fd, pending[:8192]):]
                        except BrokenPipeError:
                            pending = memoryview(b'')
                        if not pending:
                            sel.unregister(key.fileobj); key.fileobj.close()
                    else:
                        part = os.read(key.fd, 8192)
                        if not part:
                            sel.unregister(key.fileobj); key.fileobj.close(); continue
                        dest = out[key.data]
                        room = cap - sum(len(v) for v in out.values())
                        dest.extend(part[:max(room, 0)])
                        if len(part) > room:
                            issue = 'OUTPUT_LIMIT'; break
                if issue:
                    break
        finally:
            if proc.poll() is None or issue:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            proc.wait(timeout=5)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
    return dict(stdout=bytes(out['stdout']), stderr=bytes(out['stderr']),
                exit_code=proc.returncode, issue=issue,
                wall_time_ms=(time.monotonic_ns() - started) // 1000000)


class Docker:
    """Local Unix daemon only. No repository, gold labels, secrets or socket mounts."""
    def __init__(self):
        self.prefix = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']

    def control(self, args):
        r = capture(self.prefix + args, b'', 10000, MAX_FILE)
        require(r['issue'] is None and r['exit_code'] == 0,
                'docker_control:' + args[0] + ':' + r['stderr'].decode(errors='replace')[:300])
        return r['stdout']

    def preflight(self, p):
        info = parse(self.control(['image', 'inspect', p['image_id']]))[0]
        require(info['Id'] == p['image_id'] and info.get('Os') == 'linux', 'image_mismatch')
        require(not info['Config'].get('Volumes'), 'image_declares_volumes')
        return dict(image_id=info['Id'], image_architecture=info.get('Architecture'),
                    docker_version=self.control(['version', '--format', '{{.Server.Version}}']).decode().strip(),
                    host_platform=os.uname().sysname + ' ' + os.uname().release,
                    host_machine=os.uname().machine, host_python=sys.version,
                    host_cpu_count=os.cpu_count(),
                    host_cpu_model=next((line.split(':', 1)[1].strip() for line in
                        Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), None))

    def create_args(self, p, snapshot, name):
        lim = p['limits']
        require(',' not in str(snapshot), 'mount_path_comma')
        return ['create', '--pull', 'never', '--name', name, '--label', 'geek-work.protected=1',
                '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--user', '65534:65534',
                '--pids-limit', str(lim['pids']), '--memory', str(lim['memory_bytes']),
                '--memory-swap', str(lim['memory_bytes']), '--cpus', '1',
                '--ulimit', 'nofile=64:64', '--ulimit', 'core=0:0', '--log-driver', 'none',
                '--no-healthcheck', '--ipc', 'none', '--workdir', '/tmp',
                '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777',
                '--mount', 'type=bind,src=' + str(snapshot) + ',dst=/candidate.py,readonly',
                '--entrypoint', p['interpreter'], '-i', p['image_id'], '-I', '-B', '/candidate.py']

    def check_isolation(self, info, p, snapshot):
        h, c = info['HostConfig'], info['Config']
        lim = p['limits']; mounts = info['Mounts']
        require(info['Image'] == p['image_id'] and c['User'] == '65534:65534' and
                c['Entrypoint'] == [p['interpreter']] and c['Cmd'] == ['-I', '-B', '/candidate.py'],
                'container_command_changed')
        require(h['NetworkMode'] == 'none' and h['ReadonlyRootfs'] and not h['Privileged'] and
                h['CapDrop'] == ['ALL'] and not h.get('CapAdd') and
                'no-new-privileges' in h['SecurityOpt'] and h['Memory'] == lim['memory_bytes'] and
                h['MemorySwap'] == lim['memory_bytes'] and h['PidsLimit'] == lim['pids'] and
                h['NanoCpus'] == 1000000000 and h['IpcMode'] == 'none' and
                not h.get('PidMode') and h['LogConfig']['Type'] == 'none', 'isolation_config_changed')
        require(len(mounts) == 1 and mounts[0]['Type'] == 'bind' and not mounts[0]['RW'] and
                mounts[0]['Source'] == str(snapshot) and mounts[0]['Destination'] == '/candidate.py',
                'unexpected_mount')
        require(h['Tmpfs'] == {'/tmp': 'rw,noexec,nosuid,nodev,size=16777216,mode=1777'}, 'tmpfs_changed')

    def execute(self, p, snapshot, public, wall_ms):
        name = 'geek-work-eval-' + uuid.uuid4().hex
        result = dict(stdout=b'', stderr=b'', exit_code=None, issue='INFRA_ERROR', wall_time_ms=0)
        audit = dict(container_name=name, config_checked=False, cleanup_confirmed=False,
                     stopped_before_removal=None, oom_killed=None)
        try:
            self.control(self.create_args(p, snapshot, name))
            info = parse(self.control(['inspect', name]))[0]
            self.check_isolation(info, p, snapshot); audit['config_checked'] = True
            audit['configuration'] = dict(Image=info['Image'], HostConfig=info['HostConfig'],
                                          Mounts=info['Mounts'], Config={k: info['Config'][k]
                                              for k in ('User', 'Entrypoint', 'Cmd')})
            audit['snapshot_host_path'] = str(snapshot)
            result = capture(self.prefix + ['start', '--attach', '--interactive', name],
                             ev.encoded(public), wall_ms, p['limits']['output_bytes'])
            info = parse(self.control(['inspect', name]))[0]
            if info['State']['Running']:
                audit['kill_requested'] = True
                self.control(['kill', '--signal', 'KILL', name])
                info = parse(self.control(['inspect', name]))[0]
            audit['stopped_before_removal'] = not info['State']['Running']
            audit['oom_killed'] = info['State']['OOMKilled']
            audit['container_exit_code'] = info['State']['ExitCode']
            if audit['oom_killed']:
                result['issue'] = 'EXEC_OOM'
            elif result['issue'] is None and info['State']['ExitCode'] != 0:
                result['issue'] = 'EXEC_ERROR'
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            result['issue'] = 'INFRA_ERROR'
            audit['error'] = str(exc)
        finally:
            try:
                # Force removal also covers failure after creation or during inspection.
                self.control(['rm', '--force', name])
                names = self.control(['ps', '--all', '--filter', 'name=^/' + name + '$',
                                      '--format', '{{.Names}}']).decode().splitlines()
                audit['cleanup_confirmed'] = name not in names
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                audit['cleanup_error'] = str(exc)
        return result, audit


def verdict(result, audit, expected):
    require(result['issue'] in (None, 'EXEC_TIMEOUT', 'EXEC_OOM', 'OUTPUT_LIMIT', 'EXEC_ERROR', 'INFRA_ERROR'),
            'invalid_process_issue')
    require(result['exit_code'] is None or type(result['exit_code']) is int, 'invalid_exit_code')
    require(type(result['wall_time_ms']) is int and result['wall_time_ms'] >= 0, 'invalid_process_time')
    for key in ('cleanup_confirmed', 'config_checked'):
        require(type(audit[key]) is bool, 'invalid_audit_boolean')
    require(audit['stopped_before_removal'] is None or type(audit['stopped_before_removal']) is bool,
            'invalid_stopped_state')
    require(audit['oom_killed'] is None or type(audit['oom_killed']) is bool, 'invalid_oom_state')
    if not audit['cleanup_confirmed']:
        return 'CLEANUP_UNCONFIRMED'
    if not audit['config_checked']:
        return 'ISOLATION_UNCONFIRMED'
    if audit['oom_killed']:
        return 'EXEC_OOM'
    if result['issue']:
        return result['issue']
    if result['exit_code'] != 0 or audit['stopped_before_removal'] is not True:
        return 'EXEC_ERROR'
    try:
        actual = parse(result['stdout'])
    except (ValueError, UnicodeError, RecursionError):
        return 'INVALID_OUTPUT'
    return 'PASS' if ev.encoded(actual) == ev.encoded(expected) else 'RESULT_MISMATCH'


def trial_rows(p):
    return [(f'{rep:02d}-{i:03d}', row) for rep in range(p['repetitions'])
            for i, row in enumerate(p['corpus']['cases'])]


def run(p, candidate, output, expected_plan_sha, engine=None):
    require(ev.digest(ev.encoded(p)) == expected_plan_sha, 'expected_plan_mismatch')
    validate_plan(p, candidate)
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'candidate.py'
    snapshot.write_bytes(candidate); snapshot.chmod(0o444)
    ev.write(output / 'plan.json', p)
    execution_kind = 'container' if engine is None else 'fixture'
    engine = Docker() if engine is None else engine
    started = time.monotonic_ns()
    environment = engine.preflight(p)  # Failure leaves an explicitly unsealed directory.
    rows = []
    for tid, case in trial_rows(p):
        remaining = p['limits']['total_wall_time_ms'] - (time.monotonic_ns() - started) // 1000000
        if remaining <= 0:
            break
        before = time.monotonic_ns()
        result, audit = engine.execute(p, snapshot, case['input'], min(remaining, p['limits']['wall_time_ms']))
        for key in ('stdout', 'stderr'):
            (output / (tid + '.' + key)).write_bytes(result[key])
        status = verdict(result, audit, case['expected'])
        elapsed = (time.monotonic_ns() - before) // 1000000
        rows.append(dict(trial_id=tid, case_id=case['id'], status=status, audit=audit,
                         process={k: v for k, v in result.items() if k not in ('stdout', 'stderr')},
                         lifecycle_wall_time_ms=elapsed))
        if not audit['cleanup_confirmed'] or result['issue'] == 'INFRA_ERROR':
            break  # Do not accumulate uncertain containers.
    drift = blob(snapshot) != candidate or p['evaluator'] != pins()
    total = (time.monotonic_ns() - started) // 1000000
    passed = (len(rows) == len(trial_rows(p)) and all(r['status'] == 'PASS' for r in rows)
              and not drift and total <= p['limits']['total_wall_time_ms'])
    receipt = dict(schema='geek-work-protected-receipt-1', plan_sha256=ev.digest(ev.encoded(p)),
                   status='passed' if passed else 'failed', trials=rows, source_drift=drift,
                   run_id=uuid.uuid4().hex, execution_kind=execution_kind,
                   total_wall_time_ms=total, environment=environment, paid_model_calls=0,
                   limits='Host/daemon/runtime trusted; hashes are not signatures or reviewer independence. '
                          'No protection from hostile host user, kernel escape, hardware or daemon failure.')
    ev.write(output / 'receipt.json', receipt)
    ev.write(output / 'ledger.json', make_ledger(receipt))
    seal = {f.name: ev.digest(f.read_bytes()) for f in output.iterdir() if f.is_file()}
    ev.write(output / 'seal.json', dict(schema='geek-work-protected-seal-1', files=seal))
    return receipt


def make_ledger(receipt):
    tasks = []
    for row in receipt['trials']:
        accepted = row['status'] == 'PASS' and not receipt['source_drift']
        tasks.append(dict(task_id=receipt['run_id'] + ':' + row['trial_id'],
                          outcome='accepted' if accepted else 'rejected', attempts_count=1,
                          acceptance=dict(kind='machine_check', evidence=[dict(path='receipt.json',
                            sha256=ev.digest(ev.encoded(receipt)))]) if accepted else None,
                          attempts=[dict(attempt_id=1, model_profile=None, model_transition='initial',
                            token_usage=None, monetary_cost=None,
                            verification_wall_time_ms=row['lifecycle_wall_time_ms'],
                            failure_classes=[] if accepted else [row['status'] if not receipt['source_drift'] else 'SOURCE_DRIFT'],
                            human_interventions=None)]))
    costs = dict(schema='geek-work-ledger-1', currency='USD',
                 cost_scope='attempt_including_verification', tasks=tasks)
    ledger.validate(costs)
    return costs


def verify(output, expected_plan_sha):
    output = Path(output)
    seal = parse(blob(output / 'seal.json'))
    require(set(seal) == {'schema', 'files'} and seal['schema'] == 'geek-work-protected-seal-1', 'seal_schema')
    p = parse(blob(output / 'plan.json'))
    require(ev.digest(ev.encoded(p)) == expected_plan_sha, 'expected_plan_mismatch')
    validate_plan(p, blob(output / 'candidate.py'))
    receipt = parse(blob(output / 'receipt.json'))
    require(receipt['plan_sha256'] == expected_plan_sha, 'receipt_plan_mismatch')
    require(receipt['execution_kind'] in ('container', 'fixture'), 'execution_kind')
    require(type(receipt['total_wall_time_ms']) is int and receipt['total_wall_time_ms'] >= 0, 'receipt_time')
    rows = receipt['trials']; trials = trial_rows(p)
    require(len(rows) <= len(trials), 'extra_trials')
    names = {'plan.json', 'candidate.py', 'receipt.json', 'ledger.json'}
    for row, (tid, case) in zip(rows, trials):
        require(row['trial_id'] == tid and row['case_id'] == case['id'], 'trial_sequence')
        require(type(row['lifecycle_wall_time_ms']) is int and row['lifecycle_wall_time_ms'] >= 0, 'trial_time')
        if receipt['execution_kind'] == 'container' and row['audit']['config_checked']:
            Docker().check_isolation(row['audit']['configuration'], p, Path(row['audit']['snapshot_host_path']))
        r = dict(row['process'])
        for key in ('stdout', 'stderr'):
            name = tid + '.' + key; names.add(name); r[key] = blob(output / name)
        require(row['status'] == verdict(r, row['audit'], case['expected']), 'verdict_changed')
    require(set(seal['files']) == names and {f.name for f in output.iterdir()} == names | {'seal.json'},
            'artifact_set_changed')
    for name in names:
        require(ev.digest(blob(output / name)) == seal['files'][name], 'artifact_hash:' + name)
    passed = (len(rows) == len(trials) and all(r['status'] == 'PASS' for r in rows) and
              not receipt['source_drift'] and receipt['total_wall_time_ms'] <= p['limits']['total_wall_time_ms'])
    require(receipt['status'] == ('passed' if passed else 'failed'), 'receipt_status_changed')
    require(parse(blob(output / 'ledger.json')) == make_ledger(receipt), 'ledger_receipt_mismatch')
    return receipt


def compare(baseline, candidate, baseline_sha, candidate_sha):
    a, b = verify(baseline, baseline_sha), verify(candidate, candidate_sha)
    pa, pb = [parse(blob(Path(x) / 'plan.json')) for x in (baseline, candidate)]
    require({k: v for k, v in pa.items() if k != 'candidate_sha256'} ==
            {k: v for k, v in pb.items() if k != 'candidate_sha256'}, 'comparison_contract_changed')
    require(a['environment'] == b['environment'] and a['execution_kind'] == b['execution_kind'],
            'comparison_environment_changed')
    def median(r):
        return statistics.median(t['lifecycle_wall_time_ms'] for t in r['trials']) if r['trials'] else None
    return dict(schema='geek-work-protected-comparison-1',
                baseline_status=a['status'], candidate_status=b['status'],
                correctness_preserved=a['status'] == b['status'] == 'passed',
                baseline_median_lifecycle_ms=median(a), candidate_median_lifecycle_ms=median(b),
                performance_qualified=False, actual_monetary_cost=None,
                limits='Includes cold container lifecycle; no causal speedup/RSI or production promotion.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--corpus', type=Path, required=True); plan.add_argument('--candidate', type=Path, required=True)
    plan.add_argument('--image-id', required=True); plan.add_argument('--interpreter', default='/usr/local/bin/python3')
    plan.add_argument('--repetitions', type=int, default=2); plan.add_argument('--limits', type=Path)
    plan.add_argument('--output', type=Path, required=True)
    execute = sub.add_parser('run'); execute.add_argument('--plan', type=Path, required=True)
    execute.add_argument('--candidate', type=Path, required=True); execute.add_argument('--output', type=Path, required=True)
    execute.add_argument('--expected-plan-sha256', required=True)
    check = sub.add_parser('verify'); check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-plan-sha256', required=True)
    comp = sub.add_parser('compare')
    for arg in ('baseline', 'candidate', 'baseline-plan-sha256', 'candidate-plan-sha256'):
        comp.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            p = make_plan(parse(blob(args.corpus)), blob(args.candidate), args.image_id, args.interpreter,
                          args.repetitions, parse(blob(args.limits)) if args.limits else None)
            ev.write(args.output, p); result = dict(plan_sha256=ev.digest(ev.encoded(p)))
        elif args.command == 'run':
            result = run(parse(blob(args.plan)), blob(args.candidate), args.output, args.expected_plan_sha256)
        elif args.command == 'verify':
            result = verify(args.bundle, args.expected_plan_sha256)
        else:
            result = compare(args.baseline, args.candidate, args.baseline_plan_sha256, args.candidate_plan_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('status') == 'failed' else 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status='refused', reason=str(exc)), ensure_ascii=False)); return 2


if __name__ == '__main__':
    sys.exit(main())
