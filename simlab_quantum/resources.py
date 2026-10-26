from pathlib import Path
import psutil
from .models import Circuit, RunConfig

def available_memory() -> int:
    available = psutil.virtual_memory().available
    # Root cgroup v2 and v1 mounts (typical containers).
    for limit_path, used_path in [('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
                                 ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')]:
        try:
            limit, used = Path(limit_path).read_text().strip(), int(Path(used_path).read_text())
            if limit != 'max':
                available = min(available, max(0, int(limit)-used))
        except (OSError, ValueError):
            pass
    return available

def estimate(circuit: Circuit, config: RunConfig) -> dict:
    elements = 1 << (circuit.n_qubits * (2 if config.mode == 'density_matrix' else 1))
    base = elements * 16
    # State copies, contractions, diagnostics, initial state and trajectory buffers.
    peak = base * 12 + config.shots * 256 + 16 * 1024**2
    available = available_memory()
    budget = min(int(config.memory_gib * 1024**3), int(available * 0.8))
    return dict(state_bytes=base, estimated_peak_bytes=peak, available_bytes=available,
                budget_bytes=budget, fits=peak <= budget)

def check_resources(circuit: Circuit, config: RunConfig) -> dict:
    report = estimate(circuit, config)
    if not report['fits']:
        raise MemoryError(f"Estimated peak {report['estimated_peak_bytes']/1024**3:.3f} GiB exceeds available budget {report['budget_bytes']/1024**3:.3f} GiB")
    return report
