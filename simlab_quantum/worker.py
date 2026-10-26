"""Trusted numerical worker; OS limits precede imports of NumPy and Pydantic."""
import sys
import resource
from pathlib import Path
from .protocol import LIMITS, SCHEMA, read_json, validate_request, write_json


def numerical_checks(result, state):
    import numpy as np
    if not np.isfinite(state).all():
        raise ArithmeticError('Nonfinite state')
    tol = 1e-9
    if state.ndim == 1:
        norm = float(np.vdot(state, state).real)
        if abs(norm-1) > tol:
            raise ArithmeticError('State norm outside tolerance')
        checks = {'norm': norm}
    else:
        trace = np.trace(state)
        hermitian_error = float(np.max(np.abs(state-state.conj().T)))
        minimum = float(np.linalg.eigvalsh(state).min())
        if abs(trace-1) > tol or hermitian_error > tol or minimum < -tol:
            raise ArithmeticError('Density matrix outside numerical validity tolerance')
        checks = {'trace_real': float(trace.real), 'trace_imag': float(trace.imag),
                  'hermitian_error': hermitian_error, 'minimum_eigenvalue': minimum}
    if sum(result.counts.values()) != result.config.shots:
        raise ArithmeticError('Shot count disagreement')
    checks['absolute_tolerance'] = tol
    return checks


def main(directory):
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS['address_space_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS['cpu_seconds'],)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['max_file_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(directory)
    status, detail = 'EXEC_ERROR', ''
    try:
        data = (root/'request.json').read_bytes()
        if len(data) > LIMITS['max_input_bytes']:
            raise ValueError('Input size exceeded')
        request = read_json(data)
        work = validate_request(request)
        import numpy as np
        import pydantic
        import psutil
        import importlib.metadata
        versions = {}
        for line in (Path(__file__).parent/'requirements.txt').read_text().splitlines():
            if '==' in line and not line.startswith('#'):
                name, expected = line.split('==')
                actual = importlib.metadata.version(name)
                if actual != expected:
                    raise ImportError(f'{name}: expected {expected}, found {actual}')
                versions[name] = actual
        from .models import Circuit, RunConfig
        from .core import run
        circuit = Circuit.model_validate(request['circuit'])
        config = RunConfig(**request['config'], memory_gib=.5, timeout_seconds=25)
        result, state = run(circuit, config)
        checks = numerical_checks(result, state)
        result.versions.update(pydantic=pydantic.__version__, psutil=psutil.__version__)
        write_json(root/'result.json', {'schema': SCHEMA, 'evidence_kind': 'numerical_simulation',
                   'result': result.model_dump(), 'checks': checks, 'work_units': work,
                   'state_artifact': 'state.npy', 'dtype': str(state.dtype),
                   'shape': list(state.shape), 'bit_order': 'q0_most_significant',
                   'runtime_dependencies': versions,
                   'resources': {'rlimit_as_bytes': list(resource.getrlimit(resource.RLIMIT_AS)),
                                 'rlimit_cpu_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
                                 'worker_peak_rss_kib_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}})
        np.save(root/'state.npy', state, allow_pickle=False)
        status = 'COMPLETED'
    except ImportError as e:
        status, detail = 'DEPENDENCY_ERROR', str(e)
    except MemoryError as e:
        status, detail = 'RESOURCE_LIMIT', str(e)
    except TimeoutError as e:
        status, detail = 'EXEC_TIMEOUT', str(e)
    except (ValueError, TypeError, KeyError, RecursionError) as e:
        status, detail = 'INVALID_INPUT', str(e)
    except ArithmeticError as e:
        status, detail = 'NUMERICAL_ERROR', str(e)
    except Exception as e:
        status, detail = 'EXEC_ERROR', type(e).__name__+': '+str(e)
    print(__import__('json').dumps({'schema': SCHEMA, 'status': status, 'detail': detail[:2000]}, allow_nan=False))
    return 0 if status == 'COMPLETED' else 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
