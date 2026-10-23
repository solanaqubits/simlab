# SimLab

Exact numerical experiments and formal SQL-gap verification, maintained independently
of Leanbook. The mathematical statement is G=A/I+B*I−2√(A*B), with A,B,I>0.

The native path decodes byte-level JSON into exact rational inputs, compares the
actual SQLInstance with a separately supplied ExpectedInstance, verifies rounding,
and reads framed requests through a proved finite-state accumulation machine.

```sh
./scripts/build-native.sh
python3 -B scripts/audit.py
lake build --wfail
```

Lean and mathlib are pinned by lean-toolchain and lake-manifest.json. Native linking
uses the reviewed stack initialization shim; the build script compiles it explicitly.
The native tests and authority adapter use the Python standard library. The private
research tree separately pins its numerical dependencies.

The third SimLab-to-Lean obligation remains OPEN: authority of the expected-context
source, actual OS IO effects, compiler/runtime, and external data provenance are not
proved by the finite-state or arithmetic theorems. Hashes are integrity metadata, not
authorization. No physical detector claim is made.

See docs/BOUNDARIES.md, docs/HIERARCHY.md and docs/CATALOG.json. Historical evidence
is retained separately; a new directory or repository does not turn indeterminate
into accepted. This is an infrastructure migration, not a new mathematical release.

The optional supervisor API in `authority/gate.py` adds explicit task/revision
authorization, Linux peer-credential checks and a sealed context snapshot. Read
`authority/CONTRACT.md` before use: no authority service is installed by this code,
and same-UID issuer/executor deployment is deliberately refused.

## Selected research metadata

The [Prometheus compatibility snapshot](studies/prometheus_compatibility/README.md)
publishes 14 non-composition claims and an offline metadata checker, with pinned
links to public Leanbook sources. It is separate from the formal SQL core and
does not establish physical feasibility, secret-key security or hardware authority.
Its explicit export scope is recorded in [docs/PROMETHEUS_EXPORT.json](docs/PROMETHEUS_EXPORT.json);
`docs/EXPORT.json` remains the historical SQL-core export record.

The [Prometheus coverage supplement](docs/prometheus-coverage/README.md)
distinguishes direct, partial and contextual coverage of its 14 claim boundaries.
