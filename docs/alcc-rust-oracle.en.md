# Bounded Rust normalization oracle

This optional **second oracle** checks the experimental normalization corpus.
It supplements Python `fractions.Fraction`; it does not replace the Lean kernel,
`checkCert`, the byte verifier, or the Python reference. A match is empirical
agreement between implementations, not a new formal proof or a speed claim.

The implementation adapts the Fable audit's `fraction_oracle` prototype
(2026-10-25, source SHA-256
`903225e56461780dca8dd1327575b55781b840c4bf72528d51b73ad5c2eb3476`).
Integration adds checked absolute value for `i128::MIN`, strict input/error
handling, a versioned protocol, bounded execution and build binding. The original
audit prototype/archive is preserved. No policy-scanner prototype is integrated.

## Domain and outcomes

Input is UTF-8 text, one term per line: `x y z numerator denominator`.
There are exactly three nonnegative `u64` exponents, a signed `i128` numerator,
and a positive `i128` denominator. Zero coefficients and duplicate monomials
are allowed. The result combines equal exponents, reduces fractions, removes
zero sums and sorts exponent triples in descending lexicographic order.

The bounded implementation refuses `i128::MIN` and any intermediate overflow,
even when an unbounded calculation would have a representable final result.
This is deliberately not a general arbitrary-precision rational oracle.

| Native exit | Protocol status | Meaning |
| --- | --- | --- |
| 0 | `OK` | A complete reference is available |
| 2 | `INVALID_INPUT` | Outside the input syntax/domain |
| 3 | `RANGE_EXCEEDED` | Integer parse/arithmetic range refusal |
| 4 | `INPUT_LIMIT` | Input/term limit exceeded |
| 5 | `IO_ERROR` | Native input read failed |

The Python adapter checks the JSON schema and exit/status agreement. It emits
`MATCH` only on exact agreement with the Python reference. A disagreement is
`REFERENCE_MISMATCH`, not a certificate verdict. Range refusal, input refusal,
timeout, crash, malformed output or binding failure cannot become a match.
The benchmark records oracle refusals as `not_checked` and disagreements as
`oracle_mismatch`, stopping before accepting that case. Build-pin failures may
abort before a benchmark receipt is created. No fallback silently discards a
requested oracle.

## Build and pin

Rust **1.95.0** must already be installed locally. The crate is standard-library
only; Cargo runs `--offline --locked --release --jobs 1`, with a 120-second
build timeout. No build or test downloads dependencies locally. An external,
new output directory holds the target cache, binary, build log and manifest.

```sh
python3 -m tools.alcc_rust_oracle build --output /absolute/new/oracle-build
```

Save the printed manifest SHA-256 independently. The manifest records the four
crate source/config hashes, Rust/Cargo versions, build command, binary and log
hashes. Each oracle invocation checks this pin and the current crate sources,
and rechecks the binary/manifest and input after normal execution. These are
software integrity checks; they do not prove supplier authenticity, eliminate
TOCTOU, or establish bit-for-bit reproducibility across machines.

## Archive replay

```sh
python3 -m tools.alcc_rust_oracle replay \
  --archive /absolute/frozen/run-1 \
  --build /absolute/oracle-build \
  --manifest-sha256 EXPECTED_MANIFEST_SHA256 \
  --output /absolute/new/replay-output
```

Replay first matches each archived input against the independently selected
fixed corpus. It compares Rust with Python and validates all 22 archived full
outputs per case against that common result. It writes a separate report with
input/output/build hashes and raw oracle stdout/stderr. Original files are not
rewritten. No Lean process is launched and no new timing experiment occurs.
The archive validator and corpus selection are shared Python infrastructure;
only the rational normalization implementation is a separate Rust calculation.

## Benchmark integration

Add both options to the existing benchmark command:

```sh
python3 -m tools.alcc_normalization_bench \
  --binary /absolute/alcc-normalize-bench \
  --lean-commit EXPECTED_LEAN_COMMIT --build-log /absolute/lean-build.log \
  --output /absolute/new/benchmark-output \
  --resource-profile isolated-as-4g-memory-1g-v2 \
  --rust-oracle-build /absolute/oracle-build \
  --rust-oracle-manifest-sha256 EXPECTED_MANIFEST_SHA256
```

The isolated profile still requires its existing cgroup limits; use the qualified
container setup and mount the new runner and oracle build read-only. The optional
oracle runs before Lean, outside the Lean measurement interval, but affects the
overall run and potentially cache state. Old measurements must not be relabeled
as measurements of this new combined setup. No new benchmark run is part of
this integration.

The Linux adapter is for the single-threaded trusted diagnostic runner. Per
oracle call: at most 1 MiB input, 4096 terms, 256 MiB `RLIMIT_AS`, 2 CPU seconds,
5 wall seconds, 2 MiB per output stream and no core dump. The existing 180-second
benchmark budget is retained; no automatic resource expansion is performed.
The separately planned outer-container watchdog is not implemented here.

## Validation and limits

Run the Python integration tests (they build Rust once in a temporary directory)
and the crate tests:

```sh
python3 -m unittest tests.test_alcc_rust_oracle tests.test_alcc_normalization_bench -v
cargo +1.95.0 test --offline --locked \
  --manifest-path tools/alcc_fraction_oracle/Cargo.toml \
  --target-dir /absolute/test-target
```

Coverage includes the fixed corpus, 40 deterministic generated cases, algebraic
metamorphisms, overflow, `i128::MIN`, invalid input, limits, protocol mutations,
binary pinning and simulated timeout/crash handling. A benchmark adapter test
uses real Rust with fixture Lean output; it is not a native Lean measurement.
The CI job is configured separately from the existing portable ALCC tests.
Hosted CI and a full beta are not established by local tests.
