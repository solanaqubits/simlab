# ALCC compiled bridge and offline receipt audit

This optional package uses the public [Leanbook ALCC CLI](https://github.com/solanaqubits/leanbook/blob/v0.8.0/docs/alcc.en.md).
It is separate from SimLab's SQL verifier and authority gate; it grants no
operational authorization and installs no service.

## Build and run

Clone Leanbook at `v0.8.0` and this public SimLab revision. Python 3.11+ and
Linux/POSIX are required. Leanbook pins Lean/Lake and Mathlib. From SimLab:

```sh
python3 -m tools.alcc_compiled_pin --lean-project /absolute/leanbook --output /absolute/new-build
python3 -m tools.alcc_compiled_runner --engine compiled-pipeline \
  --passport /absolute/expected-passport.json --certificate /absolute/certificate.json \
  --pin /absolute/new-build/pin.json --output /absolute/runs
```

The build helper uses the reviewed `tools/alcc_kernel_sources.json` content pin
for eight formal modules, lean-toolchain and lake-manifest.json. It does not need
private Git objects. `kernel_base_commit` remains the historical model anchor;
the content manifest is the reproducible public source selection. One inherited
trailing whitespace was removed from the SHA256 source for this export; no Lean
term was changed. The CLI, build configuration, runner, helper and source manifest
must match their committed bytes. Toolchains/dependencies are checked; a strict
build produces a fresh machine-local PIN. Do not reuse another machine's PIN.

The PIN identifies separate kernel/CLI/runner provenance, the binary, build log,
environment manifest and runner source. Hashes do not authenticate a supplier or
prove a reproducible binary build. A caller-owned trusted PIN is required. The
expected passport must be selected and authenticated independently of the witness.

| Native exit | Outcome | Interpretation |
|---|---|---|
| 0 | VERIFIED_SUCCESS | zero polynomial residual |
| 2 | IDENTITY_MISMATCH | nonzero residual of this certificate only |
| 3 | DECODE_ERROR | decoder/binding refusal; no mathematical verdict |

Each run preserves raw byte snapshots, stdout/stderr and a receipt with
`evidence_kind: compiled_execution`. Snapshots use an isolated directory and
pre/post SHA-256 checks. This does not exclude a transient same-UID/privileged
TOCTOU substitution. Timeout, crash, I/O, output/protocol and confirmed runtime
OOM errors are kept separate from certificate outcomes. OOM is never inferred
from SIGKILL alone; diagnostic-path tests are synthetic, not physical OOM tests.

The standalone single-threaded runner sets wall/CPU, virtual-address-space and
output-file limits. Defaults are 30 seconds, 2 GiB address space (not RSS), 1 MiB
per input and per log. `preexec_fn` is not suitable for embedding in a multithreaded
service. File-system stalls are not covered by the child-process timeout.

## Offline receipt consistency

```sh
python3 -m tools.alcc_receipt_audit --receipt /absolute/run/receipt.json \
  --pin /absolute/new-build/pin.json \
  --passport-sha256 EXPECTED_PASSPORT_SHA256 --certificate-sha256 EXPECTED_CERTIFICATE_SHA256
```

Expected hashes must come from independently selected input files or a trusted
manifest, not from the receipt under test. The checker reads fixed snapshot/log
names adjacent to the receipt and trusted artifact paths from the PIN. It checks
hashes, sizes, Base64 logs, schema, recorded command/environment and exit/JSON
agreement, without executing the binary. Final symlinks and non-regular files
are refused. Receipt/environment have 4 MiB read limits, PIN 64 KiB, inputs/logs
1 MiB, and hashed artifacts 512 MiB. Archived run directories may be relocated;
PIN artifact paths must remain available.

`ARCHIVE_CONSISTENT` (exit 0) means internal consistency only. Normal recorded
0/2/3 outcomes are supported. `ARCHIVE_REJECTED` (exit 1) is not a mathematical
verdict; incomplete and EXEC_* failure archives are outside the supported class.
A fully fabricated self-consistent archive can pass. There is no authentication
of execution, proof of applied OS limits or independent replay of the theorem.
Individual olean files listed inside environment.json are not reopened: its bytes
are hashed as a manifest. Python and OS behavior remain in the trusted base.

## Checks

```sh
python3 -m unittest tests.test_alcc_public_pin tests.test_alcc_compiled_runner tests.test_alcc_receipt_audit -v
python3 -m tests.run_alcc_compiled_live --pin /absolute/new-build/pin.json --output /absolute/new-native
```

The first suite has 35 standard-library tests (2 public content-pin, 19 runner,
14 archive). The native matrix has 15 paired byte cases (3 accepted, 2 nonzero,
10 decode refusals) and one direct missing-file CLI case. Original raw inputs and
expected outcomes are generated independently of Lean's answers. No physical
counterexample or absence of an alternative certificate follows from rejection.

This public export contains no private logs, runtime artifact PIN, Digital Brain
content or private Git history. The historical ALCC-KERNEL-BRIDGE-2 proof mode
remains unchanged in the private source; it is not exported by this package.
