"""Small, inspectable demonstrations; not cryptanalytic workloads."""
import numpy as np
from .models import Circuit, Operation, Condition

NAMES = ['bell', 'ghz', 'interference', 'teleportation', 'grover', 'qft', 'noise']

def op(gate, *targets, **kwargs):
    return Operation(gate=gate, targets=list(targets), **kwargs)

def qft_operations(n: int):
    operations = []
    for q in range(n):
        operations.append(op('H', q))
        for other in range(q+1, n):
            phase = np.pi / 2**(other-q)
            diagonal = [1, 1, 1, np.exp(1j*phase)]
            matrix = [[[float(z.real), float(z.imag)] for z in row] for row in np.diag(diagonal)]
            operations.append(op('UNITARY', q, other, matrix=matrix))
    for q in range(n//2):
        operations.append(op('SWAP', q, n-1-q))
    return operations

def example(name: str) -> Circuit:
    if name == 'bell':
        return Circuit(name='Bell', n_qubits=2, operations=[op('H', 0), op('CX', 0, 1)])
    if name == 'ghz':
        return Circuit(name='GHZ', n_qubits=3, operations=[op('H', 0), op('CX', 0, 1), op('CX', 1, 2)])
    if name == 'interference':
        return Circuit(name='Interference H·H', n_qubits=1, operations=[op('H', 0), op('H', 0)])
    if name == 'teleportation':
        return Circuit(name='Teleportation Ry(π/3)|0⟩', n_qubits=3, n_clbits=2, operations=[
            op('RY', 0, angle=np.pi/3), op('H', 1), op('CX', 1, 2), op('CX', 0, 1), op('H', 0),
            op('MEASURE', 0, 1, clbits=[0, 1]),
            op('X', 2, condition=Condition(bit=1, value=1)),
            op('Z', 2, condition=Condition(bit=0, value=1))])
    if name == 'grover':
        return Circuit(name='Grover: search for 11', n_qubits=2, operations=[
            op('H', 0), op('H', 1), op('CZ', 0, 1),
            op('H', 0), op('H', 1), op('X', 0), op('X', 1), op('CZ', 0, 1),
            op('X', 0), op('X', 1), op('H', 0), op('H', 1)])
    if name == 'qft':
        forward = qft_operations(3)
        backward = [g.model_copy(update={'inverse': not g.inverse}) for g in reversed(forward)]
        return Circuit(name='QFT and inverse QFT', n_qubits=3, operations=[op('X', 0), op('H', 2)] + forward + backward)
    if name == 'noise':
        return Circuit(name='Excited-qubit damping', n_qubits=1,
                       operations=[op('X', 0), op('AMPLITUDE_DAMPING', 0, probability=0.3)])
    raise ValueError(f'Unknown example {name!r}; choose from {NAMES}')
