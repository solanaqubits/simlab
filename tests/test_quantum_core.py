# Migrated from Quantum f787b02 tests/test_core.py; see simlab_quantum/UPSTREAM.json.
import numpy as np
import pytest
from simlab_quantum.models import Circuit, Operation, RunConfig
from simlab_quantum.core import StatevectorBackend, DensityMatrixBackend, run
from simlab_quantum.gates import FIXED, unitary, kraus
from simlab_quantum.examples import example, op, qft_operations
from simlab_quantum.models import NOISE

@pytest.mark.parametrize('name', list(FIXED))
def test_gate_unitarity(name):
    u = FIXED[name]
    np.testing.assert_allclose(u.conj().T @ u, np.eye(len(u)), atol=1e-12)

@pytest.mark.parametrize('mode', ['statevector', 'density_matrix'])
def test_bell_and_ghz(mode):
    for name, size in [('bell', 4), ('ghz', 8)]:
        result, state = run(example(name), RunConfig(mode=mode, shots=4000))
        psi = np.zeros(size, complex); psi[0] = psi[-1] = 1/np.sqrt(2)
        np.testing.assert_allclose(state, psi if mode == 'statevector' else np.outer(psi, psi.conj()), atol=1e-12)
        assert abs(result.counts['0' * result.circuit.n_qubits] / 4000 - 0.5) < .04
        for qubit in result.diagnostics['qubits']:
            np.testing.assert_allclose(qubit['bloch'], [0, 0, 0], atol=1e-12)
            assert qubit['purity'] == pytest.approx(.5)


def dense_embed(u, targets, n):
    """Independent basis-index reference, no tensor contractions."""
    matrix = np.zeros((2**n, 2**n), complex)
    for col in range(2**n):
        bits = list(format(col, f'0{n}b'))
        local_col = int(''.join(bits[q] for q in targets), 2)
        for row in range(2**len(targets)):
            output = bits.copy()
            for q, b in zip(targets, format(row, f'0{len(targets)}b')):
                output[q] = b
            matrix[int(''.join(output), 2), col] = u[row, local_col]
    return matrix


def test_random_local_operators_against_dense():
    rng = np.random.default_rng(4)
    psi = rng.normal(size=16) + 1j*rng.normal(size=16); psi /= np.linalg.norm(psi)
    sv, dm = StatevectorBackend(4, psi), DensityMatrixBackend(4, psi)
    reference = psi.copy()
    for targets in [[3], [3, 0], [2, 0, 3], [0, 2], [1]]:
        size = 2**len(targets)
        u, _ = np.linalg.qr(rng.normal(size=(size,size)) + 1j*rng.normal(size=(size,size)))
        reference = dense_embed(u, targets, 4) @ reference
        sv.apply(u, targets); dm.apply(u, targets)
        np.testing.assert_allclose(sv.state, reference, atol=1e-12)
        np.testing.assert_allclose(dm.state, np.outer(reference, reference.conj()), atol=1e-12)
    assert sv.expectation('XYZI') == pytest.approx(dm.expectation('XYZI'))

@pytest.mark.parametrize('backend', [StatevectorBackend, DensityMatrixBackend])
def test_sampling_collapse_and_order(backend):
    b = backend(2); b.apply(FIXED['H'], [0]); b.apply(FIXED['CX'], [0,1])
    previous = b.state.copy()
    b.sample(100, np.random.default_rng(1))
    np.testing.assert_array_equal(previous, b.state)
    bits = b.measure([1,0], np.random.default_rng(2))
    assert bits[0] == bits[1]
    assert b.measure([0,1], np.random.default_rng(3)) == bits
    b.reset(0, np.random.default_rng(3))
    assert b.measure([0], np.random.default_rng(9)) == [0]

@pytest.mark.parametrize('noise', sorted(NOISE))
@pytest.mark.parametrize('p', [0, .37, 1])
def test_noise_physical(noise, p):
    operators = kraus(op(noise, 0, probability=p))
    np.testing.assert_allclose(sum(k.conj().T@k for k in operators), np.eye(2), atol=1e-12)
    b = DensityMatrixBackend(2); b.apply(FIXED['H'], [0]); b.apply(FIXED['CX'], [0,1])
    before = b.state.copy(); b.channel(operators, [0])
    np.testing.assert_allclose(b.state, b.state.conj().T, atol=1e-12)
    assert np.trace(b.state) == pytest.approx(1)
    assert np.linalg.eigvalsh(b.state).min() > -1e-12
    if p == 0:
        np.testing.assert_allclose(before, b.state)


def test_noise_limits_and_reset_entanglement():
    b = DensityMatrixBackend(1); b.apply(FIXED['X'], [0])
    b.channel(kraus(op('AMPLITUDE_DAMPING', 0, probability=1)), [0])
    np.testing.assert_allclose(b.state, np.diag([1,0]))
    b.channel(kraus(op('DEPOLARIZING', 0, probability=1)), [0])
    np.testing.assert_allclose(b.state, np.eye(2)/2)
    b = DensityMatrixBackend(2); b.apply(FIXED['H'], [0]); b.apply(FIXED['CX'], [0,1]); b.reset(0, None)
    np.testing.assert_allclose(b.state, np.diag([.5,.5,0,0]), atol=1e-12)

@pytest.mark.parametrize('mode', ['statevector', 'density_matrix'])
def test_teleportation(mode):
    for seed in range(8):
        result, state = run(example('teleportation'), RunConfig(mode=mode, seed=seed, shots=8))
        bloch = result.diagnostics['qubits'][2]['bloch']
        np.testing.assert_allclose(bloch, [np.sqrt(3)/2, 0, .5], atol=1e-12)
        assert sum(result.classical_counts.values()) == 8
        assert result.diagnostics['state_scope'] == 'first_trajectory'


def test_grover_qft_and_inverse():
    assert run(example('grover'), RunConfig(shots=30))[0].counts == {'11': 30}
    operations = qft_operations(3)
    circuit = Circuit(n_qubits=3, operations=operations)
    f = np.exp(2j*np.pi*np.outer(np.arange(8),np.arange(8))/8)/np.sqrt(8)
    for k in range(8):
        psi = np.eye(8, dtype=complex)[:,k]
        np.testing.assert_allclose(run(circuit, RunConfig(shots=1), psi)[1], f[:,k], atol=1e-12)
    expected = np.zeros(8); expected[4:6] = 1/np.sqrt(2)
    np.testing.assert_allclose(run(example('qft'), RunConfig(shots=1))[1], expected, atol=1e-12)
    for gate in ['RX','RY','RZ']:
        u = unitary(op(gate, 0, angle=.713))
        inv = unitary(op(gate, 0, angle=.713, inverse=True))
        np.testing.assert_allclose(inv@u, np.eye(2), atol=1e-12)


def test_reproducibility_and_serialization():
    circuit = example('bell')
    assert Circuit.model_validate_json(circuit.model_dump_json()) == circuit
    assert run(circuit)[0].counts == run(circuit)[0].counts

@pytest.mark.parametrize('data', [dict(gate='CX', targets=[0,0]), dict(gate='H', targets=[-1]),
    dict(gate='RX', targets=[0]), dict(gate='H', targets=[0], angle=1),
    dict(gate='MEASURE', targets=[0]), dict(gate='BIT_FLIP', targets=[0], probability=2)])
def test_bad_operations(data):
    with pytest.raises(ValueError): Operation(**data)


def test_bad_inputs_and_limits():
    with pytest.raises(ValueError): StatevectorBackend(1, [1,1])
    with pytest.raises(ValueError): DensityMatrixBackend(1, [[2,0],[0,-1]])
    with pytest.raises(ValueError): run(example('noise'))
    with pytest.raises(ValueError): Circuit(n_qubits=1, operations=[op('H', 1)])
    with pytest.raises(MemoryError): run(Circuit(n_qubits=40))
    with pytest.raises(TimeoutError): run(example('bell'), RunConfig(timeout_seconds=1e-10))
    with pytest.raises(ValueError):
        run(Circuit(n_qubits=1, operations=[op('UNITARY', 0, matrix=[[(1,0),(1,0)],[(0,0),(1,0)]])]))


def test_reduced_states_against_explicit_partial_trace():
    rng = np.random.default_rng(16)
    a = rng.normal(size=(8,8)) + 1j*rng.normal(size=(8,8))
    rho = a @ a.conj().T; rho /= np.trace(rho)
    backend = DensityMatrixBackend(3, rho)
    for q in range(3):
        expected = np.zeros((2,2), complex)
        for i in range(8):
            for j in range(8):
                a_bits, b_bits = format(i,'03b'), format(j,'03b')
                if all(a_bits[k] == b_bits[k] for k in range(3) if k != q):
                    expected[int(a_bits[q]),int(b_bits[q])] += rho[i,j]
        np.testing.assert_allclose(backend.reduced_state(q), expected, atol=1e-12)


def test_resource_budget_and_container_limit(monkeypatch, tmp_path):
    import simlab_quantum.resources as resources
    monkeypatch.setattr(resources, 'available_memory', lambda: 128*1024**2)
    report = resources.estimate(Circuit(n_qubits=20), RunConfig())
    assert report['budget_bytes'] == int(128*1024**2*.8)
    assert not report['fits']
