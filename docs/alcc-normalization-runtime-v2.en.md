# Controlled runtime resource profile, version 2

The user explicitly authorized controlled budget expansion after the original
1-GiB address-space pilot failed during runtime initialization. This profile is
a new experiment; prior failures and their contract remain immutable evidence.

## Fixed limits and acceptance

| Resource | New limit | Enforcement |
| --- | --- | --- |
| Total container memory | 1 GiB | Docker/cgroup v2 `memory.max` |
| Swap | 0 | `memory.swap.max` |
| Per-process virtual address space | 4 GiB (previously 1 GiB) | `RLIMIT_AS` |
| CPU quota | At most 1 CPU | `cpu.max` |
| CPU time per native case | 10 seconds | `RLIMIT_CPU` |
| Wall time per native case | At most 15 seconds | Subprocess timeout |
| Driver elapsed budget | 180 seconds | Remaining deadline caps each subprocess |
| Outer container lifetime | 210 seconds | Host watchdog; failure is preserved |
| Network | None | Docker network namespace |

Only virtual address space increases. The 1-GiB memory limit includes the driver,
runtime, charged file pages and other cgroup memory: it is not a measurement of
the polynomial operation's isolated working set. `memory.peak` is reported with
that scope; virtual stack reservation does not imply committed physical memory.

Use explicit `--resource-profile isolated-as-4g-memory-1g-v2`. The legacy default
remains `legacy-as-1g`. The new profile checks observable cgroup-v2 memory, swap
and CPU limits before executing the binary and again after successful completion.
Missing/incompatible limits fail closed. Record raw `memory.events` and `cpu.stat`
before and after, as well as the memory peak; do not infer OOM from a signal alone.

## Frozen inputs and runtime

Reuse Lean source commit `ea945d65cd316fd209be77b4cf07cc94b2605b03` and the
unchanged executable SHA-256
`4ffcd34b786dd5ff2f495e81ea7e0795919aa1029be5e9fa19916b54f3389128`.
The existing generated-C evidence must still match and show clock/compute/clock.
No Lean rebuild, altered proof, production replacement or public integration is
part of this resource change.

Keep the same nine cases, rational reference and 22 full-output checks per case.
Each native process has one validation, two warmup and eight sample rounds for
both variants, alternating order. Keep serial execution (`LEAN_NUM_THREADS=0`)
and `LEAN_STACK_SIZE_KB=8192`; do not patch the compiler or preload a runtime shim.

The empty case is the startup check at the beginning of the same bounded run.
If it passes, finish the remaining frozen cases. A failure stops the run with
its evidence; there is no retry loop or automatic resource escalation. Another
change requires a new recorded reason and contract revision before execution.

## Reporting and boundaries

Keep commands, container image ID and inspect output, source/build/binary hashes,
effective cgroup limits, all stdout/stderr and sample times. Use a fresh output
directory. Initial runtime failure is not mathematical rejection. Passing this
pilot establishes exact agreement only on the fixed native corpus; the universal
source-level refinement theorem has separate proof evidence. Medians describe
this local diagnostic, not whole-pipeline throughput or a statistical claim.

The container image uses read-only host system libraries; hash the relevant
runtime executables/libraries separately. Its image digest alone is not a full
environment pin. No new successful beta is implied by the pilot.
