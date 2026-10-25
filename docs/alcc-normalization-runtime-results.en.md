# Controlled ALCC normalization runtime pilot: observed results

Source runner: `958be3c70e1e6cdd49b88526960895913441ed8c`.
Lean source: `ea945d65cd316fd209be77b4cf07cc94b2605b03`;
unchanged proof/documentation head: `e6862fc845f5829ce871226159346723fd677da6`.
Protocol and budgets: [runtime profile v2](alcc-normalization-runtime-v2.en.md).

## Outcome

The fixed native binary completed all nine cases with exit zero. All 198 full
outputs agreed with the independent exact Fraction reference: 18 validation,
36 warmup, and 144 measured outputs. These are 144 durations, not 144 independent
process trials. Nine native processes ran once each, with eight samples per
variant after warmup. The empty case passed before the remaining corpus.

Sixteen runner/reference/resource-contract unit tests passed, with no skips.
Offline replay rechecked the stored outputs using the same validator; this is
not a second independently implemented validator. The corpus, reference and
output validator are unchanged from the original pilot (AST comparison).

## Local timing observations

Medians are in nanoseconds. Ratio is baseline/cached; below 1 means the cached
variant's median was larger. No overhead subtraction or outlier removal is used.

| Case | Baseline median ns | Cached median ns | Ratio |
| --- | ---: | ---: | ---: |
| `empty` | 55.5 | 60.0 | 0.925 |
| `zero` | 370.5 | 381.0 | 0.972 |
| `rational` | 2509.5 | 1483.0 | 1.692 |
| `cancel` | 676.0 | 691.0 | 0.978 |
| `unique32` | 226979.5 | 122081.0 | 1.859 |
| `unique128` | 4242382.5 | 2285933.0 | 1.856 |
| `duplicate128` | 813369.5 | 457301.0 | 1.779 |
| `cancel128` | 1043255.0 | 1044493.0 | 0.999 |
| `large_rationals` | 312761.5 | 162517.5 | 1.924 |

Five cases had lower cached medians in this run. Empty, zero and cancellation
cases showed no useful gain; do not omit them from the report. The eight samples
are a small local diagnostic. They do not establish statistical significance,
hardware-independent speedup, or production ALCC throughput. No additional
measurement runs were selected to improve the result.

## Resource observations

Effective `memory.max` was 1,073,741,824 bytes; `memory.swap.max` was zero.
`cpu.max` was `100000 100000`. The child's hard/soft `RLIMIT_AS` of 4 GiB
and `RLIMIT_CPU` of 10 seconds were separately exercised by a preflight process.
Docker inspect confirmed those container settings, network isolation, successful
exit and `OOMKilled=false`.

Container memory peak was 150,204,416 bytes (about 143.2 MiB), including driver,
runtime and charged pages. It is not the isolated normalizer's working-set peak.
OOM and OOM-kill counters remained zero. CPU throttling increased by five periods
and 9,299 microseconds across the driver run; scheduling/quota noise is part of
these observations. Driver elapsed time was about 0.497 seconds, excluding
container startup and pre-report binary hashing. The host observed a successful
container completion within its 210-second watchdog.

Increasing address-space allowance solved this startup blocker without changing
the binary, raising the physical-memory cap, disabling swap isolation or patching
Lean. Earlier 1-GiB address-space failures remain preserved and correctly scoped.

## Proof and release boundary

The three source-level equivalence theorems and prior 129-declaration axiom audit
are reused only because their sources, binary and generated C are unchanged.
No fresh Lean compilation or full beta was performed in this resource-only step.
The generated-C hash still matches the inspected clock/compute/clock order; this
is not a compiler or machine-code verification proof.

Production ALCC is not replaced. The other optimization directions remain plans.
The independent combined audit and new full beta on final integrated bytes are
still pending. Public v0.9.0 qualification remains withdrawn; v0.8.0 remains the
last successful beta. Nothing in this pilot changes release status.
