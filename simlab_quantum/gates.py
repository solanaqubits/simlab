import numpy as np
from .models import Operation

I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
CX = np.eye(4, dtype=complex)[[0, 1, 3, 2]]
SWAP = np.eye(4, dtype=complex)[[0, 2, 1, 3]]
CCX = np.eye(8, dtype=complex)[[0, 1, 2, 3, 4, 5, 7, 6]]
FIXED = {"I": I, "X": X, "Y": Y, "Z": Z, "H": H, "S": np.diag([1, 1j]),
         "T": np.diag([1, np.exp(1j*np.pi/4)]), "CX": CX,
         "CZ": np.diag([1, 1, 1, -1]), "SWAP": SWAP, "CCX": CCX}

def unitary(op: Operation) -> np.ndarray:
    if op.gate == "UNITARY":
        a = np.asarray(op.matrix, dtype=float)
        u = a[..., 0] + 1j * a[..., 1]
        if not np.isfinite(u).all() or not np.allclose(u.conj().T @ u, np.eye(len(u)), atol=1e-10, rtol=1e-10):
            raise ValueError("Custom matrix must be finite and unitary")
    elif op.gate in {"RX", "RY", "RZ"}:
        u = np.cos(op.angle / 2) * I - 1j * np.sin(op.angle / 2) * FIXED[op.gate[1:]]
    else:
        u = FIXED[op.gate]
    return u.conj().T if op.inverse else u

def kraus(op: Operation) -> list[np.ndarray]:
    p = op.probability
    if op.gate == "BIT_FLIP":
        return [np.sqrt(1-p)*I, np.sqrt(p)*X]
    if op.gate == "PHASE_FLIP":
        return [np.sqrt(1-p)*I, np.sqrt(p)*Z]
    if op.gate == "DEPOLARIZING":
        # E(rho) = (1-p)rho + p I/2 for a single-qubit state.
        return [np.sqrt(1-3*p/4)*I] + [np.sqrt(p/4)*a for a in (X, Y, Z)]
    if op.gate == "AMPLITUDE_DAMPING":
        return [np.diag([1, np.sqrt(1-p)]), np.array([[0, np.sqrt(p)], [0, 0]])]
    if op.gate == "PHASE_DAMPING":
        return [np.diag([1, np.sqrt(1-p)]), np.diag([0, np.sqrt(p)])]
    raise ValueError("Unknown noise channel")
