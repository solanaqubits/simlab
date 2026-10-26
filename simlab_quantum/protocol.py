"""Standard-library-only boundary shared by the launcher and numerical worker."""
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'SIMLAB-QUANTUM-1'
LIMITS = dict(address_space_bytes=1024**3, cpu_seconds=20, wall_seconds=30,
              max_input_bytes=1024**2, max_file_bytes=8*1024**2,
              max_qubits_sv=16, max_qubits_dm=8, max_shots=4096,
              max_operations=512, max_work_units=50_000_000)
STATUSES = {'COMPLETED', 'INVALID_INPUT', 'RESOURCE_LIMIT', 'DEPENDENCY_ERROR',
            'NUMERICAL_ERROR', 'EXEC_TIMEOUT', 'EXEC_ERROR', 'INTEGRITY_ERROR', 'IO_ERROR'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(data):
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate JSON key: ' + k)
            result[k] = v
        return result
    def bad(value):
        raise ValueError('nonfinite JSON token: ' + value)
    def finite(value):
        x = float(value)
        if not math.isfinite(x):
            raise ValueError("nonfinite JSON number")
        return x
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad, parse_float=finite)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+'\n')


def implementation_manifest():
    root = Path(__file__).parent
    return {p.name: sha(p.read_bytes()) for p in sorted(root.iterdir())
            if p.is_file() and (p.suffix == '.py' or p.name in {'UPSTREAM.json', 'requirements.txt'})}


def implementation_hash():
    return sha(json.dumps(implementation_manifest(), sort_keys=True).encode())


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {'schema', 'circuit', 'config'} or request['schema'] != SCHEMA:
        raise ValueError('Expected schema, circuit and config for '+SCHEMA)
    config = request['config']
    if not isinstance(config, dict) or set(config) != {'mode', 'shots', 'seed'}:
        raise ValueError('config requires mode, shots and seed; resource limits are fixed by the runner')
    if config['mode'] not in ('statevector', 'density_matrix'):
        raise ValueError('Unknown simulation mode')
    for k, low, high in [('shots', 1, LIMITS['max_shots']), ('seed', 0, 2**63-1)]:
        if type(config[k]) is not int or not low <= config[k] <= high:
            raise ValueError('Invalid '+k)
    c = request['circuit']
    if not isinstance(c, dict) or type(c.get('n_qubits')) is not int or c['n_qubits'] < 1:
        raise ValueError('circuit requires a positive integer n_qubits')
    ops = c.get('operations', [])
    if not isinstance(ops, list) or any(not isinstance(op, dict) for op in ops):
        raise ValueError('operations must be objects')
    dm = config['mode'] == 'density_matrix'
    if c['n_qubits'] > LIMITS['max_qubits_dm' if dm else 'max_qubits_sv'] or len(ops) > LIMITS['max_operations']:
        raise MemoryError('Circuit exceeds fixed qubit/operation policy')
    dynamic = any(op.get('gate') == 'MEASURE' or (op.get('gate') == 'RESET' and not dm) for op in ops)
    work = max(1, len(ops)) * (config['shots'] if dynamic else 1) * 2**(c['n_qubits']*(2 if dm else 1))
    if work > LIMITS['max_work_units']:
        raise MemoryError('Circuit exceeds fixed conservative work policy')
    return work
