# ALCC Python byte preflight: fixed development pilot

This profile measures the existing `tools.alcc.bind` and `tools.alcc.residual` on
canonical in-memory JSON bytes. Binding includes JSON syntax/schema validation,
expected-passport digest calculation and certificate problem/hypothesis binding.
It does not call `tools.alcc.verify`, Lean, a native ALCC executable or the production
CLI. `residual_zero` is a Python observation, never the bridge's formal PASS.

Freeze before launch: the nine existing typed development cases, converted to
canonical ALCC-JSON-1, plus three explicit rejection controls (wrong problem ID,
noncanonical JSON and unreduced rational). Duplicate terms in the typed corpus are
combined for byte representation; the duplicate-cancellation case therefore does
not measure a duplicate input accepted by the canonical parser. Compare the entire
residual with the existing typed Fraction oracle, not just its zero/nonzero bit.
The adapter and reference share an author and Python Fraction; no independent audit.

Five rounds per case: one warmup, four measured. Case order reverses each round.
Record binding, residual and result-serialization nanoseconds and inclusive elapsed
time; unavailable stages after a refusal are null. Inputs are loaded before timing.
Timing excludes disk I/O, startup, expected-reference computation, logging, archive
writes and replay. Inclusive process wall time is separate, not added to stage time.
Per-case medians are descriptive; no cached/baseline speedup comparison is made.

Pilot: two sequential process invocations, no corpus tuning. Each child has 30 s
wall time, 256 MiB per-process RLIMIT_AS, disabled core dumps and 64 KiB per captured
stream using the installed trusted supervisor. Native arithmetic bounds remain in
force, with a one-second arithmetic deadline per evaluation. No budget escalation.
Stop the pilot if any invocation does not match the expected controls; retain its
request, logs, process outcome and available artifacts. Hard kills/parent failures
can leave an incomplete directory, never a completed result. No automatic retry.

Only fixed installed code is executable. The CLI accepts a fresh output directory,
not a supplied script or arbitrary task. Replay checks an externally retained
manifest SHA, exact file bytes, fixed corpus/code binding, full outputs and summary
calculation without executing a child or archived code. It does not authenticate
execution, measured timings, origin or host limits. Stable trusted local paths are
assumed; no hostile-code containment or crash-durable storage claim.

Unknown tokens, monetary cost and peak RSS remain null. Production, existing
formal imports and the older typed-pilot artifacts stay unchanged. Full native
byte/JSON/SHA/CLI throughput, a generic executor and third obligation remain OPEN.
