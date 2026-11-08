#!/usr/bin/env python3
"""Run the unchanged harness CLI against two real local server CLI sessions.

Session tokens and temporary input/result copies are deleted after each run.
The evidence directory is new and contains only sanitized harness receipts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

BRAIN = Path(__file__).resolve().parents[3]
TOOLS = BRAIN/'tools'


def configuration(mode):
    if mode == 'ready':
        example = BRAIN/'examples/claim-adapter-ready'
        pins = json.loads((example/'pins.json').read_bytes())
        return example/'source.txt', example/'expectations.json', example/'source-bundle', example/'record.json', pins
    example = BRAIN/'examples/claim-extraction-orbit'
    pins = json.loads((example/'pins.json').read_bytes())
    pins.update(claim_map_bundle_sha256='022bbbc4659daa6cb249aed9bdb8dc8a90c85f7fb9bd828ab53964458398281b', source_claim_id='subcritical-orbit-limit', source_revision=1)
    bundle = BRAIN/'examples/claim-transport-orbit/source-bundle'
    return bundle/'material-lean-source.txt', example/'expectations.json', bundle, example/'orbit-needs-context.json', pins


def run(mode, output):
    source, ledger, bundle, record, pins = configuration(mode)
    with tempfile.TemporaryDirectory(prefix='claim-api-replay-') as tmp:
        session = Path(tmp)/'session'
        command = [sys.executable, '-B', str(TOOLS/'geek_work_claim_api_server.py'),
            '--source-snapshot', str(source), '--source-sha256', pins['source_sha256'],
            '--expectations', str(ledger), '--expectations-sha256', pins['expectations_sha256'],
            '--claim-map-bundle', str(bundle), '--claim-map-bundle-sha256', pins['claim_map_bundle_sha256'],
            '--source-claim-id', pins['source_claim_id'], '--source-revision', str(pins['source_revision']),
            '--session-dir', str(session)]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic()+10
            while not (session/'session.json').exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('server_startup_failed')
                time.sleep(.02)
            # An exclusive file can briefly exist before its write completes.
            while True:
                try:
                    info = json.loads((session/'session.json').read_bytes())
                    break
                except ValueError:
                    if time.monotonic()>deadline:
                        raise RuntimeError('server_startup_failed')
                    time.sleep(.02)
            receipt = output/(mode+'.json')
            result = subprocess.run([sys.executable, '-B', str(TOOLS/'geek_work_claim_api_harness.py'),
                '--port', str(info['port']), '--token-file', info['token_file'], '--context-id', info['context_id'],
                '--mode', mode, '--record', str(record), '--output', str(receipt)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=270)
            report = json.loads(receipt.read_bytes())
            if result.returncode or report['status'] != 'passed':
                raise RuntimeError(mode+'_harness_failed')
            return dict(mode=mode, status='passed', http_exchanges=len(report['cases']),
                        receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    results=[]
    try:
        for mode in ('ready', 'orbit'):
            results.append(run(mode,args.output))
    finally:
        (args.output/'checks.json').write_text(json.dumps(dict(
            schema='claim-review-server-replay-1', results=results,
            semantic_equivalence_verified=False, source_extraction_complete=False,
            kernel_replayed=False, publication_authorized=False), indent=2)+'\n')
    print('Real server/harness CLI replay passed: ready, orbit')


if __name__ == '__main__':
    main()
