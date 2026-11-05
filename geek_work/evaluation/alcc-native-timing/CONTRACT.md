# Instrumented native ALCC byte verification

Predeclared 2026-11-05. Separate IO adapter over unchanged
AlgebraicCertificateVerify.verifyCertificateBytes. Read both input files between
monotonic clocks; then call a noinline IO function converting ByteArrays to lists,
decoding/binding SHA and computing the verdict between the next two clocks.
Inspect generated C to confirm clock/check/clock ordering before the pilot.
Serialization, output, process startup and external pin hashing are excluded from
these two intervals. These are instrumented-adapter times, not subtractions from
historical wrapper measurements. No pure checkCert isolation or speedup claim.

Compile only the adapter with Lean 4.33.1 against the preserved original CLI
project at 8768dc18c1846df60b26a564004f9fd232d8b32e; compare original source/olean
hashes against the retained environment receipt. Reuse its link object closure,
record object hashes, do not rebuild Mathlib or modify formal modules. Compiler,
C compilation and link each have 120 s timeout. No new theorem/audit claim.

After successful build and C inspection: all 12 fixed byte-preflight cases, three
rounds (one warmup, two measured), reverse order on odd rounds, 36 processes maximum.
Same fixed expected decision codes 0/2/3 as the earlier full-corpus study. Per child:
30 s wall timeout, 2 GiB virtual address space, 1 MiB per log stream, existing pinned
runtime environment, CPU/file/core limits. Stop on any unexpected result, malformed
row, limit failure or changed binary/input. Retain partial evidence; no retries or
budget expansion. Entire native process time is separately observed externally.

Verify all code/type/order fields, nonnegative integer timings, and read+verify
intervals no greater than outer elapsed process time. Two measured samples per
case are descriptive only. Visible shared-author development corpus, no independent
holdout, no throughput qualification. Production binary and original sources stay
unchanged; compiler/runtime correctness and third obligation remain OPEN.
