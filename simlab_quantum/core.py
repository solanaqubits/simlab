"""Floating-point CPU backends. Operations contract only their target tensor axes."""
from abc import ABC, abstractmethod
from collections import Counter
import platform
import time
import numpy as np
from .gates import X, FIXED, unitary, kraus
from .models import Circuit, RunConfig, RunResult, NOISE
from .resources import check_resources


def apply_axes(data: np.ndarray, matrix: np.ndarray, axes: list[int]) -> np.ndarray:
    rest = [i for i in range(data.ndim) if i not in axes]
    order = axes + rest
    arranged = data.transpose(order).reshape(2 ** len(axes), -1)
    output = (matrix @ arranged).reshape([2] * data.ndim)
    return output.transpose(np.argsort(order))

class SimulatorBackend(ABC):
    def __init__(self, n_qubits: int, initial_state=None):
        self.n = n_qubits
        self.dim = 2**n_qubits
        self.state = self.initialize(initial_state)

    @abstractmethod
    def initialize(self, initial_state): ...
    @abstractmethod
    def apply(self, matrix, targets): ...
    @abstractmethod
    def probabilities(self): ...
    @abstractmethod
    def reduced_state(self, qubit): ...
    @abstractmethod
    def collapse(self, mask, probability): ...

    def sample(self, shots: int, rng: np.random.Generator) -> dict[str, int]:
        """Born samples of independently prepared copies; state is unchanged."""
        if shots < 1:
            raise ValueError('shots must be positive')
        values = rng.choice(self.dim, shots, p=self.probabilities())
        keys, counts = np.unique(values, return_counts=True)
        return {format(int(k), f'0{self.n}b'): int(v) for k, v in zip(keys, counts)}

    def measure(self, targets: list[int], rng: np.random.Generator) -> list[int]:
        if not targets or len(set(targets)) != len(targets) or any(q < 0 or q >= self.n for q in targets):
            raise ValueError('Invalid measurement targets')
        probs = self.probabilities().reshape([2]*self.n)
        rest = [q for q in range(self.n) if q not in targets]
        marginal = probs.transpose(targets+rest).reshape(2**len(targets), -1).sum(axis=1)
        outcome = int(rng.choice(len(marginal), p=marginal/marginal.sum()))
        bits = [int(b) for b in format(outcome, f'0{len(targets)}b')]
        indices = np.arange(self.dim)
        mask = np.ones(self.dim, dtype=bool)
        for q, b in zip(targets, bits):
            mask &= ((indices >> (self.n-1-q)) & 1) == b
        self.collapse(mask, float(marginal[outcome]))
        return bits

    def expectation(self, pauli: str) -> float:
        if len(pauli) != self.n or any(p not in 'IXYZ' for p in pauli):
            raise ValueError('Pauli string must have one I/X/Y/Z per qubit')
        tensor = self.state.reshape([2] * (self.n if self.state.ndim == 1 else 2*self.n))
        for q, p in enumerate(pauli):
            if p != 'I':
                tensor = apply_axes(tensor, FIXED[p], [q])
        if self.state.ndim == 1:
            return float(np.vdot(self.state, tensor.reshape(-1)).real)
        return float(np.trace(tensor.reshape(self.dim, self.dim)).real)

    def diagnostics(self) -> dict:
        qubits = []
        for q in range(self.n):
            rho = self.reduced_state(q)
            qubits.append({'qubit': q, 'rho': encode_complex(rho),
                           'bloch': [float(np.trace(rho @ FIXED[p]).real) for p in 'XYZ'],
                           'purity': float(np.vdot(rho, rho).real)})
        return {'norm_or_trace': float(np.vdot(self.state, self.state).real) if self.state.ndim == 1 else float(np.trace(self.state).real),
                'purity': 1.0 if self.state.ndim == 1 else float(np.vdot(self.state, self.state).real),
                'qubits': qubits}

class StatevectorBackend(SimulatorBackend):
    def initialize(self, initial_state):
        if initial_state is None:
            state = np.zeros(self.dim, dtype=complex)
            state[0] = 1
        else:
            state = np.array(initial_state, dtype=complex, copy=True)
        if state.shape != (self.dim,) or not np.isfinite(state).all() or not np.isclose(np.vdot(state, state), 1, atol=1e-10, rtol=1e-10):
            raise ValueError('Initial vector must have shape (2**n,) and unit norm')
        return state

    def apply(self, matrix, targets):
        self.state = apply_axes(self.state.reshape([2]*self.n), matrix, targets).reshape(self.dim)

    def probabilities(self):
        return normalize_probabilities(np.abs(self.state)**2)

    def collapse(self, mask, probability):
        self.state *= mask
        self.state /= np.sqrt(probability)

    def reduced_state(self, qubit):
        a = np.moveaxis(self.state.reshape([2]*self.n), qubit, 0).reshape(2, -1)
        return a @ a.conj().T

    def reset(self, qubit, rng):
        if self.measure([qubit], rng)[0]:
            self.apply(X, [qubit])

class DensityMatrixBackend(SimulatorBackend):
    def initialize(self, initial_state):
        if initial_state is None:
            rho = np.zeros((self.dim, self.dim), dtype=complex)
            rho[0, 0] = 1
        else:
            rho = np.array(initial_state, dtype=complex, copy=True)
            if rho.shape == (self.dim,):
                if not np.isfinite(rho).all() or not np.isclose(np.vdot(rho, rho), 1, atol=1e-10, rtol=1e-10):
                    raise ValueError('Initial vector must be normalized')
                rho = np.outer(rho, rho.conj())
            if rho.shape != (self.dim, self.dim) or not np.isfinite(rho).all():
                raise ValueError('Invalid density matrix shape or entries')
            if not np.allclose(rho, rho.conj().T, atol=1e-10, rtol=1e-10) or not np.isclose(np.trace(rho), 1, atol=1e-10, rtol=1e-10):
                raise ValueError('Density matrix must be Hermitian with trace one')
            if np.linalg.eigvalsh(rho).min() < -1e-10:
                raise ValueError('Density matrix must be positive semidefinite')
        return rho

    def transformed(self, matrix, targets):
        tensor = apply_axes(self.state.reshape([2]*(2*self.n)), matrix, targets)
        return apply_axes(tensor, matrix.conj(), [self.n+q for q in targets]).reshape(self.dim, self.dim)

    def apply(self, matrix, targets):
        self.state = self.transformed(matrix, targets)

    def channel(self, operators, targets):
        out = np.zeros_like(self.state)
        for operator in operators:
            out += self.transformed(operator, targets)
        self.state = out

    def probabilities(self):
        return normalize_probabilities(self.state.diagonal().real)

    def collapse(self, mask, probability):
        self.state *= mask[:, None]
        self.state *= mask[None, :]
        self.state /= probability

    def reduced_state(self, qubit):
        remaining = [q for q in range(self.n) if q != qubit]
        order = [qubit] + remaining + [self.n+qubit] + [self.n+q for q in remaining]
        tensor = self.state.reshape([2]*(2*self.n)).transpose(order).reshape(2, self.dim//2, 2, self.dim//2)
        return np.einsum('aibi->ab', tensor)

    def reset(self, qubit, rng):
        self.channel([np.array([[1, 0], [0, 0]]), np.array([[0, 1], [0, 0]])], [qubit])


def normalize_probabilities(p):
    if not np.isfinite(p).all() or p.min() < -1e-9 or p.sum() <= 0:
        raise ValueError('Invalid Born probabilities')
    p = np.maximum(p, 0)
    return p / p.sum()


def encode_complex(a):
    return np.stack([a.real, a.imag], axis=-1).tolist()


def validate_run(circuit, config):
    # Revalidate even if caller mutated an operations list after construction.
    circuit = Circuit.model_validate(circuit.model_dump())
    if config.mode == 'statevector' and any(op.gate in NOISE for op in circuit.operations):
        raise ValueError('Noise operations require density_matrix mode')
    for op in circuit.operations:
        if op.gate not in NOISE | {'MEASURE', 'RESET'}:
            unitary(op)
    return check_resources(circuit, config)


def run(circuit: Circuit, config: RunConfig | None = None, initial_state=None):
    """Return (serializable result, final state of the first trajectory).

    For dynamic circuits, each shot re-prepares the input. Diagnostic state and
    probabilities refer to the first trajectory, never an ensemble average.
    """
    config = config or RunConfig()
    report = validate_run(circuit, config)
    start = time.monotonic()
    deadline = start + config.timeout_seconds
    rng = np.random.default_rng(config.seed)
    cls = StatevectorBackend if config.mode == 'statevector' else DensityMatrixBackend
    compiled = [(op, kraus(op) if op.gate in NOISE else None if op.gate in {'MEASURE', 'RESET'} else unitary(op)) for op in circuit.operations]
    dynamic = any(op.gate == 'MEASURE' or (op.gate == 'RESET' and config.mode == 'statevector') for op in circuit.operations)
    counts, classical_counts = Counter(), Counter()
    first_state = first_probs = first_diagnostics = None
    for shot in range(config.shots if dynamic else 1):
        if time.monotonic() > deadline:
            raise TimeoutError('Simulation time limit exceeded')
        backend = cls(circuit.n_qubits, initial_state)
        classical = [0] * circuit.n_clbits
        for op, matrix in compiled:
            if time.monotonic() > deadline:
                raise TimeoutError('Simulation time limit exceeded')
            if op.condition and classical[op.condition.bit] != op.condition.value:
                continue
            if op.gate == 'MEASURE':
                for bit, value in zip(op.clbits, backend.measure(op.targets, rng)):
                    classical[bit] = value
            elif op.gate == 'RESET':
                backend.reset(op.targets[0], rng)
            elif op.gate in NOISE:
                backend.channel(matrix, op.targets)
            else:
                backend.apply(matrix, op.targets)
        counts.update(backend.sample(1 if dynamic else config.shots, rng))
        if circuit.n_clbits:
            classical_counts[''.join(map(str, classical))] += 1 if dynamic else config.shots
        if shot == 0:
            first_state = backend.state.copy()
            first_probs = backend.probabilities()
            first_diagnostics = backend.diagnostics()
    first_diagnostics['state_scope'] = 'first_trajectory' if dynamic else 'final_state'
    first_diagnostics['shots_reprepared'] = dynamic
    # Sort the bounded preview by basis index. Full probability vector is in NPZ.
    indices = np.flatnonzero(first_probs > 1e-15)
    truncated = len(indices) > 256
    if truncated:
        indices = indices[np.argpartition(first_probs[indices], -256)[-256:]]
    probabilities = {format(int(i), f'0{circuit.n_qubits}b'): float(first_probs[i]) for i in sorted(indices)}
    if time.monotonic() > deadline:
        raise TimeoutError('Simulation time limit exceeded')
    result = RunResult(circuit=circuit, config=config, counts=dict(sorted(counts.items())),
                       classical_counts=dict(sorted(classical_counts.items())), probabilities=probabilities,
                       probabilities_truncated=truncated, diagnostics=first_diagnostics,
                       elapsed_seconds=time.monotonic()-start, estimated_peak_bytes=report['estimated_peak_bytes'],
                       versions={'quantum_sim': '0.1.0', 'python': platform.python_version(), 'numpy': np.__version__})
    return result, first_state
