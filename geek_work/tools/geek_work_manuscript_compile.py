#!/usr/bin/env python3
"""Opt-in offline Typst compilation of a pinned selected snapshot in local Docker."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import resource
import time
import uuid
import geek_work_manuscript as m
import geek_work_manuscript_claims as claims

IMAGE = 'ghcr.io/typst/typst@sha256:5410828f3b97f32fcc3eb95fed614c962d03f480f74cea06936540b95037d2ee'
IMAGE_ID = 'sha256:8e1eda206e172f03fd4c08b0be61161dd611f7abf1e9d09c358665311ba84ca7'
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_PDF = 8 * 1024 * 1024
TIMEOUT = 30


def request(value):
    return validate_request(value, 'geek-work-manuscript-compile-request-1', '.typ')


def validate_request(value, schema, extension):
    claims.obj(value, 'schema entry files')
    m.require(value['schema'] == schema, 'request schema')
    paths = set()
    for row in claims.rows(value['files'], 32, 1):
        claims.obj(row, 'path sha256'); claims.path_name(row['path']); claims.digest(row['sha256'])
        m.require(row['path'].casefold() not in paths, 'duplicate/case-colliding paths')
        paths.add(row['path'].casefold())
    names = [row['path'] for row in value['files']]
    for a in names:
        for b in names:
            m.require(a == b or not b.casefold().startswith(a.casefold() + '/'), 'path collision')
    m.require(value['entry'] in names and value['entry'].endswith(extension), 'selected entry required')
    return value


def source(root, name):
    parts = claims.path_name(name).parts
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as stream:
            m.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular selected file required')
            raw = stream.read(MAX_FILE + 1); m.require(len(raw) <= MAX_FILE, 'file byte limit')
            if name.endswith('.typ'):
                m.source(raw)
            return raw
    except OSError as error:
        raise ValueError('missing or unsafe selected input: ' + name) from error
    finally:
        if fd is not None: os.close(fd)


def create_command(name, snapshot, entry):
    # Only copied inputs are mounted. PDF is streamed to a size-limited host capture.
    return command_for_path(name, str(snapshot.resolve()), entry)


def command_for_path(name, snapshot, entry):
    # Pure profile: archived paths can be checked without touching the old root.
    m.require(type(snapshot) is str and snapshot.startswith('/') and ',' not in snapshot and '\n' not in snapshot, 'Docker mount path')
    return ['docker', 'create', '--pull=never', '--platform=linux/amd64', '--name', name,
            '--network=none', '--read-only', '--user=1000:1000', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=2', '--memory=512m', '--memory-swap=512m',
            '--pids-limit=64', '--ulimit=fsize=16777216:16777216', '--ulimit=core=0:0',
            '--log-driver=none',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777',
            '--mount', 'type=bind,src=' + snapshot + ',dst=/src,readonly',
            '--workdir=/src', '--env=HOME=/tmp', '--env=TZ=UTC', '--env=SOURCE_DATE_EPOCH=0',
            '--entrypoint=/bin/typst', IMAGE, 'compile', '--root=/src', '--ignore-system-fonts',
            '--package-path=/tmp/packages', '--package-cache-path=/tmp/package-cache',
            '--creation-timestamp=0', '/src/' + entry, '-']


def docker(args, timeout=15):
    # Local Docker daemon/CLI are trusted; this helper only captures control metadata.
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    m.require(len(result.stdout) + len(result.stderr) <= 40 * 1024 * 1024, 'Docker output byte limit')
    return result


def success(result):
    if result.returncode:
        raise RuntimeError('Docker command failed: ' + result.stderr[:2000].decode('utf-8', 'replace'))
    return result.stdout


def attach(name, output):
    def limit():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_PDF, MAX_PDF))
    # Limit the Docker client files as well as the container. Timeout kills the
    # client; execute() separately kills/removes the daemon-owned container.
    with (output/'compiler.stdout').open('xb') as stdout, (output/'compiler.log').open('xb') as stderr:
        return subprocess.run(['docker','start','-a',name], stdout=stdout, stderr=stderr,
                              timeout=TIMEOUT, preexec_fn=limit)


def execute(snapshot, entry, output):
    name = 'geek-work-typeset-' + uuid.uuid4().hex
    result = dict(status='infrastructure_error', container_name=name, image=IMAGE, image_id=IMAGE_ID,
                  exit_code=None, oom_killed=None, timed_out=False, container_removed=False)
    pdf = None
    start = time.monotonic()
    try:
        image = json.loads(success(docker(['docker', 'image', 'inspect', IMAGE])))
        m.require(len(image) == 1 and image[0]['Id'] == IMAGE_ID, 'installed image identity mismatch')
        with (output/'image.json').open('xb') as f: f.write(m.encoded(image))
        command = create_command(name, snapshot, entry)
        with (output/'command.json').open('xb') as f: f.write(m.encoded(command))
        success(docker(command))
        client_code = None
        try:
            client_code = attach(name, output).returncode
        except subprocess.TimeoutExpired:
            result['timed_out'] = True
            success(docker(['docker','kill',name]))
        state = json.loads(success(docker(['docker','inspect',name])))[0]
        m.require(state['Image'] == IMAGE_ID, 'container image identity mismatch')
        with (output/'container.json').open('xb') as f: f.write(m.encoded(state))
        result.update(exit_code=state['State']['ExitCode'], oom_killed=state['State']['OOMKilled'], client_exit_code=client_code)
        full = any((output/file).stat().st_size >= MAX_PDF for file in ('compiler.stdout','compiler.log'))
        if result['timed_out']: result['status'] = 'timeout'
        elif result['oom_killed']: result['status'] = 'oom'
        elif full: result['status'] = 'capture_limit'
        elif state['State']['Running']: result['status'] = 'infrastructure_error'
        elif result['exit_code'] != 0: result['status'] = 'compiler_failed'
        elif client_code != 0: result['status'] = 'infrastructure_error'
        else:
            pdf = m.read(output/'compiler.stdout', MAX_PDF)
            result['status'] = 'compiled' if pdf.startswith(b'%PDF-') else 'artifact_rejected'
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        result.update(status='infrastructure_error', error=str(error)[:4000])
    finally:
        try:
            docker(['docker','rm','-f',name])
            remaining = success(docker(['docker','container','ls','-aq','--filter','name=^/'+name+'$']))
            result['container_removed'] = remaining.strip() == b''
        except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            result['cleanup_error'] = str(error)[:4000]
        if not result['container_removed']:
            result['prior_status'] = result['status']; result['status'] = 'cleanup_failed'
        result['wall_time_ms'] = round((time.monotonic()-start)*1000)
    if result['status'] == 'compiled' and pdf is not None:
        with (output/'document.pdf').open('xb') as f: f.write(pdf)
        result['pdf_sha256'] = m.sha(pdf)
    return result


def build(root, request_path, request_sha, output):
    claims.digest(request_sha)
    raw = m.read(request_path)
    m.require(m.sha(raw) == request_sha, 'request SHA mismatch')
    spec = request(m.load(raw)); blobs, total = {}, 0
    for row in spec['files']:
        blob = source(root, row['path']); total += len(blob)
        m.require(total <= MAX_TOTAL, 'input byte limit')
        m.require(m.sha(blob) == row['sha256'], 'source SHA mismatch')
        blobs[row['path']] = blob
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'sources'; snapshot.mkdir(mode=0o755)
    for name, blob in blobs.items():
        path = snapshot/name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(blob)
        path.chmod(0o644)
    for directory in [snapshot, *[p for p in snapshot.rglob('*') if p.is_dir()]]: directory.chmod(0o755)
    with (output/'request.json').open('xb') as f: f.write(raw)
    result = execute(snapshot, spec['entry'], output)
    # Detect observed host-side changes to the copied inputs before sealing.
    unchanged = all(source(snapshot, name) == blob for name,blob in blobs.items())
    if not unchanged:
        result['prior_status'] = result['status']; result['status'] = 'snapshot_changed'
    receipt = dict(schema='geek-work-manuscript-compile-receipt-1', request_sha256=request_sha,
                   **result, compile_timeout_seconds=TIMEOUT, capture_limit_bytes=MAX_PDF,
                   snapshot_unchanged_at_final_check=unchanged,
                   scientific_verification=False, semantic_claim_check=False, pdf_visual_review=False,
                   limits='Opt-in local Linux/amd64 Docker pilot. Host/daemon/compiler trusted; not a VM or formal sandbox proof. Selected per-file snapshot only. PDF header is checked, not PDF safety/layout. No network/package downloads during compilation, no live writeback or publication.')
    with (output/'receipt.json').open('xb') as f: f.write(m.encoded(receipt))
    files = {str(p.relative_to(output)):m.sha(m.read(p,40*1024*1024)) for p in sorted(output.rglob('*')) if p.is_file()}
    manifest = m.encoded(dict(schema='geek-work-manuscript-compile-manifest-1', files=files))
    with (output/'manifest.json').open('xb') as f: f.write(manifest)
    return dict(status=receipt['status'], container_removed=receipt['container_removed'], manifest_sha256=m.sha(manifest), pdf_sha256=receipt.get('pdf_sha256'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--request',type=Path,required=True)
    p.add_argument('--request-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=build(a.root,a.request,a.request_sha256,a.output)
    print(m.encoded(result).decode(),end='')
    if result['status']!='compiled': raise SystemExit(2)


if __name__=='__main__': main()
