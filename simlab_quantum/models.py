"""Versioned public circuit format. q0 is the most significant bit."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

GATE_ARITY = {"I": 1, "X": 1, "Y": 1, "Z": 1, "H": 1, "S": 1, "T": 1,
              "RX": 1, "RY": 1, "RZ": 1, "CX": 2, "CZ": 2, "SWAP": 2, "CCX": 3}
NOISE = {"BIT_FLIP", "PHASE_FLIP", "DEPOLARIZING", "AMPLITUDE_DAMPING", "PHASE_DAMPING"}

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class Condition(Model):
    bit: StrictInt = Field(ge=0)
    value: Literal[0, 1]

class Operation(Model):
    gate: str
    targets: list[StrictInt] = Field(min_length=1, max_length=64)
    angle: float | None = Field(default=None, allow_inf_nan=False)
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    clbits: list[StrictInt] = Field(default_factory=list)
    condition: Condition | None = None
    inverse: bool = False
    # Every complex entry is [real, imaginary].
    matrix: list[list[tuple[float, float]]] | None = None

    @model_validator(mode="after")
    def valid_operation(self):
        if len(set(self.targets)) != len(self.targets) or min(self.targets) < 0:
            raise ValueError("Targets must be distinct non-negative indices")
        if self.gate not in set(GATE_ARITY) | NOISE | {"UNITARY", "MEASURE", "RESET"}:
            raise ValueError(f"Unknown gate: {self.gate}")
        arity = GATE_ARITY.get(self.gate, 1 if self.gate in NOISE | {"RESET"} else None)
        if arity and len(self.targets) != arity:
            raise ValueError(f"{self.gate} requires {arity} targets")
        if self.gate == "UNITARY":
            if len(self.targets) > 3 or self.matrix is None:
                raise ValueError("UNITARY requires a matrix and at most 3 targets")
            size = 2 ** len(self.targets)
            if len(self.matrix) != size or any(len(row) != size for row in self.matrix):
                raise ValueError("Matrix shape does not match targets")
        elif self.matrix is not None:
            raise ValueError("Only UNITARY accepts matrix")
        if (self.gate in {"RX", "RY", "RZ"}) != (self.angle is not None):
            raise ValueError("Only rotation gates require angle (radians)")
        if (self.gate in NOISE) != (self.probability is not None):
            raise ValueError("Only noise gates require probability")
        if self.gate == "MEASURE":
            if len(self.clbits) != len(self.targets) or len(set(self.clbits)) != len(self.clbits):
                raise ValueError("Measurement needs one distinct classical bit per target")
        elif self.clbits:
            raise ValueError("Only MEASURE accepts clbits")
        if self.inverse and self.gate in NOISE | {"MEASURE", "RESET"}:
            raise ValueError("This operation has no unitary inverse")
        return self

class Circuit(Model):
    version: Literal[1] = 1
    n_qubits: StrictInt = Field(ge=1, le=64)
    n_clbits: StrictInt = Field(default=0, ge=0, le=64)
    operations: list[Operation] = Field(default_factory=list, max_length=10000)
    name: str = Field(default="Untitled", max_length=200)

    @model_validator(mode="after")
    def valid_indices(self):
        for op in self.operations:
            if max(op.targets) >= self.n_qubits:
                raise ValueError("Qubit index outside register")
            if any(b < 0 or b >= self.n_clbits for b in op.clbits):
                raise ValueError("Classical index outside register")
            if op.condition and op.condition.bit >= self.n_clbits:
                raise ValueError("Condition references missing classical bit")
        return self

class RunConfig(Model):
    mode: Literal["statevector", "density_matrix"] = "statevector"
    shots: StrictInt = Field(default=1024, ge=1, le=1000000)
    seed: StrictInt = Field(default=42, ge=0, le=2**63-1)
    memory_gib: float = Field(default=8, gt=0, le=1024, allow_inf_nan=False)
    timeout_seconds: float = Field(default=120, gt=0, le=86400, allow_inf_nan=False)

class RunResult(Model):
    version: Literal[1] = 1
    circuit: Circuit
    config: RunConfig
    counts: dict[str, int]
    classical_counts: dict[str, int]
    probabilities: dict[str, float]
    probabilities_truncated: bool
    diagnostics: dict
    elapsed_seconds: float
    estimated_peak_bytes: int
    versions: dict[str, str]
