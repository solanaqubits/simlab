# Optional host container watchdog

`tools.container_watchdog` creates and supervises one **new local Docker
container**. It provides bounded execution evidence, not a mathematical verdict,
formal proof, production authorization or replacement for ALCC/Quantum receipts.
The existing ALCC runner, Rust oracle, Quantum engine and authority gate are
unchanged. This is a separate opt-in command and Python API.

## Run and inspect

The selected immutable image ID must already exist on the local Docker daemon.
There is no image pull, network access, service installation or automatic budget
expansion. The included fixture refers to the locally qualified Alpine image.
Use a new output directory for every run:

```sh
python3 -B -m tools.container_watchdog run \
  --spec studies/container_watchdog/timeout.json --output .local/watchdog/run-001
# Expected CLI exit: 124. The container has a parent and child sleeping 120 s.
python3 -B -m tools.container_watchdog audit .local/watchdog/run-001
```

The API is `supervise(spec, output)`. Its result is the same structured receipt as
`receipt.json`. CLI stdout names the receipt and reports status, confirmed stop
and removal. `audit` checks archive consistency and exits 0 even for a consistent
failure receipt; it does not re-execute the task or authenticate historical logs.

The host uses `unix:///var/run/docker.sock` explicitly. Access to this socket is
an existing prerequisite, not an entitlement granted by the wrapper. The host and
Docker daemon remain trusted. The wrapper is not a sandbox for hostile operators.

## Fixed safety settings and explicit resources

The spec supplies an image **ID**, complete argv, wall deadline, cgroup memory
bytes, CPU quota, PID limit, tmpfs bytes and explicit optional bind mounts. Unknown
fields, mutable image tags, NaN/infinity, invalid limits and ambiguous paths are
rejected. A unique random name and ownership label identify the created container;
all subsequent destructive commands address its inspected ID. A foreign label is
never killed or removed. No global cleanup/prune command is used.

Every container has network `none`, read-only root, all capabilities dropped,
no-new-privileges, UID/GID 65534, no restart, memory+swap equal to memory (no extra
swap), and a size-limited noexec/nosuid/nodev tmpfs. Docker CPU quota is a rate cap,
not a CPU-time deadline. Memory is a total cgroup cap, not RLIMIT_AS or measured
process RSS. The example uses 64 MiB, 0.5 CPU, 32 PIDs, 8 MiB tmpfs and 3 seconds.

Optional binds have `{source, target, read_only}`; sources must be resolved local
files/directories, destinations unique beneath `/work/`, `/inputs/` or `/outputs/`.
The trusted caller must provision permissions for UID/GID 65534, choose safe
sources and snapshot/hash study inputs separately. The watchdog does not change
host permissions, freeze bind contents or attest their authenticity. Bind sources
need not still exist when auditing an old receipt.

Workload stdout/stderr collection is deliberately disabled (`log-driver=none`).
A study can save its own outputs to an explicitly provisioned writable bind.
`docker-calls.json` records Docker control-client output, **not workload logs**.
The wrapper does not parse certificate results or infer them from process exit 0.

## Deadline, cleanup and statuses

A monotonic execution deadline starts immediately before `docker start`, including
start latency. Polling is outside the container. On observing a running container
after the deadline, the host sends `docker kill --signal=KILL ID`, then inspects it.
Stop is confirmed only when `Running=false`, `Restarting=false`, `Pid=0` and the
state is exited/created. A merely created container is not successful execution.
The final inspect is saved before removal; `rm` must acknowledge success.

Each Docker control call has a separate five-second limit; startup uses the smaller
of five seconds and the execution budget. Scheduling and daemon IPC mean that this
is not a hard real-time termination guarantee at the exact deadline. A stopped
process observed at the deadline keeps its exit outcome. A natural-exit/kill race
is resolved by inspect, not by assuming the kill client succeeded.

| Status | Meaning |
| --- | --- |
| `EXEC_COMPLETED` | Container exited 0; no mathematical acceptance implied |
| `EXEC_NONZERO_EXIT` | Other nonzero task exit, separate from any decoder verdict |
| `EXEC_TIMEOUT` | Deadline observed, kill attempted, stop and removal confirmed |
| `EXEC_OOM` | Docker explicitly records `OOMKilled=true` |
| `EXEC_CRASH` | Exit 137 without Docker OOM evidence |
| `EXEC_DOCKER_ERROR` | Docker/image/start/control failure |
| `EXEC_CLEANUP_ERROR` | Ownership, confirmed stop or removal could not be established |
| `EXEC_CANCELLED` | Host KeyboardInterrupt; cleanup attempted and recorded |

CLI exits 0 for completed, 124 for timeout, 130 for cancellation, 1 for other
failures. Cleanup failure overrides the earlier classification. The daemon may
be unavailable; an unconfirmed container is reported, never called safely stopped.
A killed/rebooted host or SIGKILL of the watchdog cannot be handled by Python's
finally block. This is not a persistent external service guaranteeing cleanup
across host/daemon failure. Inspect `termination_confirmed` and `removed` for
infrastructure failure receipts.

## Evidence and tests

The new receipt schema is `simlab-container-watchdog-1`, with
`evidence_kind: container_execution`. It records spec/image hashes, container
identity, timestamps, elapsed monotonic duration, deadline observation, task exit,
final engine state, cleanup status and hashes of control/inspect records. These
are local traceability and consistency claims, not execution authentication.
`EXEC_*` receipts are not passed to the existing ALCC mathematical receipt auditor.

```sh
python3 -B -m unittest tests.test_container_watchdog -v
# Explicit local Docker tests: no silent skips, no mock substitute for live cases.
WATCHDOG_EVIDENCE=/absolute/new/evidence-directory \
  python3 -B tests/run_container_watchdog_live.py
```

Live tests cover exit 0, exit 7, parent+child timeout and host interruption. The
host records `/proc` PID/start-time identities before stop and checks their absence
(or PID reuse with a different start time) afterwards; Docker absence is checked
separately after removal. They also inspect actual resource/isolation settings.
Unit tests cover ownership mismatch, control/cleanup failures, ambiguous creation,
OOM classification and archive tampering. Physical OOM is not induced.

This versioned mechanism closes the bounded timeout-to-receipt experiment. It does
not retroactively prove the old normalization pilot's reported 210-second host
watchdog, integrate a new supervisor into existing production execution, qualify
performance measurements, or complete the Leanbook beta gate.
