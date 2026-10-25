# ALCC normalization comparative pilot

Contract ALCC-NORMALIZE-PILOT-1, fixed before running measurements.
This is an original diagnostic informed by the
[labinius measurement pattern](https://github.com/Layr-Labs/labinius-fast-challenge/blob/6de95237b03b90ed360b13099587d6846410a979/solution/native_diagnostics/src/compare.rs),
not copied Rust code or an official challenge benchmark.

## Statement and fixed corpus

Compare production `normalize` and the separately proved `normalizeCached` on
the same sparse rational lists. Full results must equal an independent Python
`Fraction` dictionary accumulator sorted in descending tuple order. Compare exact
exponents and reduced numerator/denominator strings, with no tolerance.

Nine cases are fixed in `tools/alcc_normalization_bench.py`: empty, zero, rational
addition, cancellation, 32 unique terms, 128 unique terms, 128 repeated terms,
128 canceling terms and 64 larger rational terms. Three variables, at most 128
terms, exponents at most 127, numerator magnitude below 2^41, denominator below
2^33. No random search, tuning after observing results, or corpus expansion.

## Measurement protocol and limits

One process per case; one validation round, two warmup rounds, eight sample
rounds per variant. Alternate baseline/cached and cached/baseline within the same
process. Each invocation rereads the same file outside the timer. The timed
operation includes normalization and a fold consuming every result term. Input
parsing, JSON serialization, complete-result checking and logging are excluded.
An empty case indicates fixed overhead but is not subtracted from measurements.

The Lean adapter must use a non-inlined IO computation between monotonic clocks.
Inspect generated C before accepting measurements: pure `let` bindings may be
floated beyond a timer by compilation. This inspection is not compiler verification.

Each case has a 15-second subprocess timeout, a 10-second CPU limit and a 1-GiB
address-space limit on Linux. Lean runs serially with `LEAN_NUM_THREADS=0`
(no background task-manager workers); the benchmark does not use `Task` APIs.
Set `LEAN_STACK_SIZE_KB=8192` as well: the
[v4.33.1 runtime default](https://github.com/leanprover/lean4/blob/v4.33.1/src/runtime/thread.cpp)
reserves a 1-GiB thread stack, which conflicts with the process address-space cap
even with one worker. Generated main initializes the task manager before reading
the stack-size override in `lean_run_main`, so disabling background workers is
also necessary. The pilot reduces reservations; it does not raise the cap.
Total driver budget: 180 seconds checked between
cases (up to one additional 15-second case before next check). No retries or
automatic budget escalation. Build budget is separate: 8-GiB container limit.

Save all inputs, raw stdout/stderr, sample durations and medians. Any mismatch,
unexpected schema/order, missing output, execution failure or changed input/binary
fails the run; no performance summary is accepted as evidence of correctness.
An infrastructure failure is not a mathematical counterexample. No significance
threshold or speedup promise is set; this is a diagnostic, not a promotion gate.

## Reproduction

Build the companion Leanbook branch's `alcc-normalize-bench` with `--wfail`.
Record its exact commit, toolchain, build log, executable hash and generated-C
timing-order inspection in the evidence package. Then run, with a new output path:

```sh
python3 -m unittest tests.test_alcc_normalization_bench -v
python3 tools/alcc_normalization_bench.py --binary /absolute/path/alcc-normalize-bench \
  --output /new/evidence/run --lean-commit FULL_COMMIT --build-log /path/build.log
```

The supplied commit metadata is a provenance assertion, not authenticated by the
driver. An auditor must reconcile it with the recorded sources/build. Hashes and
pre/post checks do not eliminate TOCTOU. The Lean runtime, compiler, OS, clock and
Python reference remain trusted for this diagnostic; kernel proofs certify the
source-level equality separately. No production ALCC speedup, EVM equivalence,
inequality checker, SIMD correctness or security certification is claimed.
