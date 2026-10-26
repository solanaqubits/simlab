# Optional Quantum simulator (local migration candidate)

SimLab can run small quantum circuits without enabling a service or changing the
SQL/ALCC verifiers. The numerical engine was migrated from
[solanaqubits/quantum-simulator](https://github.com/solanaqubits/quantum-simulator)
at `f787b023e57cd4b011ccae73638706d441707400`. Exact original file hashes are in
`simlab_quantum/UPSTREAM.json`; the original checkout is not a runtime dependency.
The selected Python core is retained, with a lazy package entry point and a new
SimLab subprocess, resource, input and receipt boundary. The original Quantum
README's description of the CPU backends as “exact” is corrected to floating point.

## Optional use

Linux, Python 3.12. Ordinary SimLab tools do not import this runtime. Help, content
pin and archive integrity checks use only Python's standard library:

```sh
python3 -B -m simlab_quantum --help
python3 -B -m simlab_quantum pin
```

For numerical execution provision a dedicated environment if needed:

```sh
python3 -m venv .venv-quantum
.venv-quantum/bin/pip install -r simlab_quantum/requirements.txt
python3 -B -m simlab_quantum run studies/quantum_simulator/cases/bell.json \
  --python "$PWD/.venv-quantum/bin/python" --output .local/quantum/bell-001
```

The output directory must not already exist. Resource budgets cannot be increased
through circuit JSON. This migration used an existing active Quantum Python
3.12.3 environment with the pinned versions, without installing packages. Its
executable supplies dependencies only; the worker imports the migrated SimLab
implementation explicitly. For a standalone installation use the dedicated venv.
Requirements pin package versions, not wheel hashes or a cross-platform environment.
A different dependency version is a `DEPENDENCY_ERROR`, not an accepted run.

The six sample requests cover Bell, GHZ, Grover, QFT, amplitude noise and
teleportation. Edit a copy for your task. Requests have exactly `schema`, `circuit`
and `config`; schema is `SIMLAB-QUANTUM-1`, config requires mode, shots and seed.
The engine's circuit-v1 format is retained: q0 is the most significant bit, angles
are radians, complex matrix entries are `[real, imaginary]`. Supported gates:
I/X/Y/Z/H/S/T, RX/RY/RZ, CX/CZ/SWAP/CCX, up to three-qubit UNITARY, measurement,
reset and classical single-bit conditions. Density-matrix mode additionally
supports bit/phase flip, depolarization and amplitude/phase damping. Initial input
is |0…0⟩; arbitrary initial states are not exposed by this CLI protocol.

## Fixed execution contract

- Statevector: at most 16 qubits; density matrix: at most 8.
- At most 512 operations and 4096 shots. Seed is an explicit integer.
- Conservative work guard: state elements × operations × trajectories ≤ 50 million.
  This is a refusal policy, not a runtime complexity proof.
- Input ≤ 1 MiB, strict UTF-8 JSON, duplicate keys and nonfinite values refused.
- Worker address space `RLIMIT_AS`: 1 GiB; CPU: 20 seconds; parent wall timer: 30 seconds.
  **Address space is not a physical-memory cgroup limit.** File size limit 8 MiB,
  core dumps disabled, numerical libraries limited to one thread.
- The parent's wall timeout kills the worker process group and waits for exit.
  A real sleeping-process termination test accompanies the protocol tests.
- The engine's own estimate uses a 0.5 GiB budget and cooperative 25-second timeout.
  OS limits enclose imports, initialization and computation as well.
- No automatic retries with larger budgets. No GPU, cloud, background service or
  network interface is started. The local worker runs trusted source under the
  invoking user's account; it is **not a security sandbox** against hostile Python.

## Outcomes and evidence

`COMPLETED` means the numerical run completed and basic consistency checks passed:
finite values, norm/trace within absolute 1e-9, Hermiticity and nonnegative density
matrix spectrum within 1e-9, and exact shot count. It is not formal acceptance.
`INVALID_INPUT`, `RESOURCE_LIMIT`, `DEPENDENCY_ERROR`, `NUMERICAL_ERROR`,
`EXEC_TIMEOUT`, `EXEC_ERROR`, `IO_ERROR`, `INTEGRITY_ERROR` remain distinct.
A signal/SIGKILL alone is not classified as proven OOM. CLI exit 0 means completion;
exit 2 requires inspecting the receipt/error status. Failure before output-directory
creation is reported on stdout and cannot have a receipt in that directory.

Each run saves the exact request snapshot, stdout/stderr, receipt, and on success
`result.json` plus full complex128 `state.npy` (load with `allow_pickle=False`).
The JSON probability preview is bounded to 256 entries and marked when truncated;
use the full state for full probabilities. With intermediate measurements or
statevector reset, the saved state/probabilities describe **the first trajectory**;
counts describe all independently prepared shots. They must not be interpreted
as a density-matrix ensemble. Seed reproducibility is limited to this environment.

The receipt records input/content hashes, implementation files and content pin,
source origin, command, timestamps, enforced policy, exit and artifact hashes.
Successful results additionally record actual dependency versions, applied rlimits
and Linux worker `ru_maxrss` in KiB. This is worker peak RSS, not whole-container
memory. Input and implementation pre/post checks detect persistent changes; they
do not exclude temporary substitution (TOCTOU) or establish execution authenticity.

Retain independently selected pins before execution:

```sh
sha256sum studies/quantum_simulator/cases/bell.json
python3 -B -m simlab_quantum pin
python3 -B -m simlab_quantum audit .local/quantum/bell-001 \
  --expected-request-sha256 <INPUT_SHA256> \
  --expected-implementation-sha256 <IMPLEMENTATION_SHA256>
```

The audit is offline archive consistency only, with no numerical recomputation.
It is not an independent numerical oracle and cannot detect a wholly fabricated
but self-consistent archive. Independent analytical expectations, dense-index
reference tests, and preserved source tests check finite cases, not all circuits.

## Scope and provenance boundaries

`evidence_kind` is always `numerical_simulation`. No new Lean proof, cryptographic
certificate, physical quantum-device validation, speedup or ALCC verdict is
produced. SimLab's quantum-contract registry remains metadata about separate
formal models; this adapter does not prove implementation refinement to them.
The original web UI, API, notebooks, CAD, Solana, entropy, Jolt/ZK and Lean bridge
are deliberately not activated or copied into this numerical extension.

Local transfer is authorized by the repository owner. No general LICENSE was
found in the pinned upstream tree; upstream notices and commit attribution are
retained. This migration does not invent a redistribution license, copy third-party
Jolt code or authorize publication. Review licensing separately before public export.

## Tests

```sh
.venv-quantum/bin/python -B -m unittest tests.test_quantum_runner -v
# Additional optional development dependency, version used locally: pytest 9.1.1
.venv-quantum/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_quantum_core.py tests/test_quantum_runner.py
```

The migrated core tests retain analytic Bell/GHZ/noise/teleportation/QFT cases,
dense basis-index reference application, Kraus completeness, partial traces,
invalid inputs and reproducibility. Wrapper tests additionally cover real missing
dependencies, real host timeout, malformed output, integrity tampering, policy
refusals, optional imports and archive pinning. Fault injection tests are identified
in code and must not be reported as physical OOM experiments.
