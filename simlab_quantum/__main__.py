import argparse
import json
import sys
from .protocol import implementation_hash
from .runner import run_request, audit_archive


def main():
    parser = argparse.ArgumentParser(description='Optional bounded Quantum simulator for SimLab; numerical evidence only')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('run'); p.add_argument('request'); p.add_argument('--output', required=True)
    p.add_argument('--python', default=sys.executable, help='Python environment with optional numerical requirements')
    sub.add_parser('pin', help='Print current implementation content hash')
    p = sub.add_parser('audit'); p.add_argument('directory')
    p.add_argument('--expected-request-sha256', required=True); p.add_argument('--expected-implementation-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'pin':
            print(implementation_hash()); return 0
        if args.command == 'audit':
            result = audit_archive(args.directory, args.expected_request_sha256, args.expected_implementation_sha256)
            print(json.dumps(result)); return 0
        r = run_request(args.request, args.output, args.python)
        print(json.dumps({'status': r['status'], 'receipt': str(__import__('pathlib').Path(args.output).resolve()/'receipt.json')}))
        return 0 if r['status'] == 'COMPLETED' else 2
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({'status': 'REQUEST_ERROR', 'detail': str(e)})); return 2


if __name__ == '__main__':
    sys.exit(main())
