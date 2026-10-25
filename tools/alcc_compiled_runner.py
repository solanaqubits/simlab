"""Separate compiled ALCC mode. No per-instance Lean kernel proof is produced."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone

PROTOCOL = "ALCC-BRIDGE-VERIFY-1"
KERNEL_BASE = "4c7e29b9735892e6979e439e9b4e08ea9a745ddc"
PAIRS = {0: "VERIFIED_SUCCESS", 2: "IDENTITY_MISMATCH", 3: "DECODE_ERROR"}
# An exact runtime diagnostic is recorded as evidence, not inferred from SIGKILL.
OOM_LINES = {b"INTERNAL PANIC: out of memory"}
RUNTIME_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LEAN_NUM_THREADS": "1",
               "LEAN_ABORT_ON_PANIC": "1", "LEAN_STACK_SIZE_KB": "65536", "MIMALLOC_ARENA_RESERVE": "67108864"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def strict_json(data: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"non-JSON constant: {value}")

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


def classify(code: int, stdout: bytes, stderr: bytes):
    if code != 0 and any(line in OOM_LINES for line in stderr.splitlines()):
        return "EXEC_OOM", "exact runtime allocation-failure diagnostic"
    if code < 0 or code == 137:
        return "EXEC_CRASH", "signal or unconfirmed exit 137; no OOM inference"
    try:
        obj = strict_json(stdout)
        if not isinstance(obj, dict) or set(obj) != {"protocol_version", "evidence_kind", "verdict"}:
            raise ValueError("unexpected JSON schema")
        if obj["protocol_version"] != PROTOCOL or obj["evidence_kind"] != "compiled_execution":
            raise ValueError("protocol version/evidence kind mismatch")
        if not isinstance(obj["verdict"], str):
            raise ValueError("verdict must be a string")
        if code == 74 and obj["verdict"] == "EXEC_IO_ERROR":
            return "EXEC_IO_ERROR", "CLI reported file input failure"
        if stderr:
            raise ValueError("unexpected stderr for a normal verdict")
        if code not in PAIRS or obj["verdict"] != PAIRS[code]:
            raise ValueError("exit code/verdict mismatch")
        return PAIRS[code], None
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        return "EXEC_PROTOCOL_ERROR", str(exc)


def load_pin(path: Path):
    pin = strict_json(path.read_bytes())
    required = {"protocol_version", "evidence_kind", "kernel_base_commit", "cli_source_commit",
                "bridge_runner_commit", "lean_toolchain", "artifacts"}
    if not isinstance(pin, dict) or set(pin) != required:
        raise ValueError("invalid pin schema")
    if pin["kernel_base_commit"] != KERNEL_BASE or pin["protocol_version"] != PROTOCOL or pin["evidence_kind"] != "compiled_execution":
        raise ValueError("wrong pin base/protocol/evidence")
    for key in ("cli_source_commit", "bridge_runner_commit"):
        value = pin[key]
        if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("full source commit SHA required")
    if not isinstance(pin["lean_toolchain"], str) or not pin["lean_toolchain"]:
        raise ValueError("toolchain required")
    if set(pin["artifacts"]) != {"binary", "build_log", "environment", "runner"}:
        raise ValueError("incomplete artifact chain")
    for name, item in pin["artifacts"].items():
        if set(item) != {"path", "sha256"} or file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"artifact hash mismatch: {name}")
    if Path(pin["artifacts"]["runner"]["path"]).resolve() != Path(__file__).resolve():
        raise ValueError("pin does not identify this runner")
    environment = strict_json(Path(pin["artifacts"]["environment"]["path"]).read_bytes())
    for key in ("kernel_base_commit", "cli_source_commit", "lean_toolchain"):
        if environment[key] != pin[key]:
            raise ValueError(f"environment mismatch: {key}")
    if environment["binary_sha256"] != pin["artifacts"]["binary"]["sha256"] or environment["build_log_hash"] != pin["artifacts"]["build_log"]["sha256"]:
        raise ValueError("environment artifact mismatch")
    return pin


def verify(passport: Path, certificate: Path, output: Path, pin_path: Path, *,
           timeout: float = 30, memory: int = 2 * 1024**3,
           input_limit: int = 1024**2, log_limit: int = 1024**2):
    """Linux/POSIX standalone runner; output is a NEW durable run directory.

    RLIMIT_AS caps virtual address space. Pre/post hashes are programmatic
    integrity checks; they do not exclude a transient hostile OS-level swap.
    The caller owns/authenticates the pin and the expected passport.
    """
    if not math.isfinite(timeout) or timeout <= 0 or any(type(x) is not int or x <= 0 for x in (memory, input_limit, log_limit)):
        raise ValueError("limits must be positive and timeout finite")
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="alcc-compiled-", dir=output))
    start = time.monotonic()
    receipt = dict(protocol_version=PROTOCOL, evidence_kind="compiled_execution",
                   started_at=datetime.now(timezone.utc).isoformat(), status="EXEC_IO_ERROR",
                   exit_code=None, run_directory=str(run.resolve()), runtime_environment=RUNTIME_ENV,
                   snapshot_integrity_verified=False, artifact_integrity_verified=False,
                   limits=dict(wall_seconds=timeout, address_space_bytes=memory,
                               cpu_seconds=math.ceil(timeout) + 1, input_bytes=input_limit,
                               log_bytes_per_stream=log_limit, lean_worker_threads=1), snapshots={}, errors=[])
    snapshots = []
    pin = None
    attempted = False
    timed_out = False
    raw_out = raw_err = b""
    proc = None
    try:
        try:
            pin = load_pin(pin_path)
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            receipt["status"] = "EXEC_PROTOCOL_ERROR"
            raise ValueError(f"provenance validation: {exc}") from exc
        receipt.update({k: pin[k] for k in ("kernel_base_commit", "cli_source_commit", "bridge_runner_commit", "lean_toolchain")})
        receipt.update(pin_sha256=file_hash(pin_path), binary_sha256=pin["artifacts"]["binary"]["sha256"],
                       build_log_hash=pin["artifacts"]["build_log"]["sha256"],
                       environment_manifest_hash=pin["artifacts"]["environment"]["sha256"])
        for label, source in (("passport", passport), ("certificate", certificate)):
            # Nonblocking open plus fstat avoids hanging on FIFO/device inputs.
            fd = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise OSError(f"{label}: input must be a regular file")
                data = stream.read(input_limit + 1)
            if len(data) > input_limit:
                raise OSError(f"{label}: runner input byte budget exceeded; Lean not invoked")
            snap = run / f"snapshot_{label}.bin"
            with snap.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            snap.chmod(0o400)
            expected = digest(data)
            if file_hash(snap) != expected:
                raise OSError("snapshot pre-execution hash mismatch")
            snapshots.append(snap)
            receipt["snapshots"][label] = dict(path=str(snap.resolve()), bytes=len(data), sha256_before=expected)

        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(timeout) + 1, math.ceil(timeout) + 2))
            resource.setrlimit(resource.RLIMIT_FSIZE, (log_limit, log_limit))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        # No shell, no witness-controlled arguments/environment configuration.
        command = [pin["artifacts"]["binary"]["path"], "--passport", str(snapshots[0].resolve()), "--certificate", str(snapshots[1].resolve())]
        receipt["command"] = command
        with (run / "stdout.bin").open("xb") as out, (run / "stderr.bin").open("xb") as err:
            attempted = True
            proc = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                    cwd=run, env=RUNTIME_ENV,
                                    start_new_session=True, preexec_fn=limits)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                # Clean up any remaining descendants as well as the timed-out leader.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        receipt["exit_code"] = proc.returncode
        raw_out = (run / "stdout.bin").read_bytes()[:log_limit]
        raw_err = (run / "stderr.bin").read_bytes()[:log_limit]
        if timed_out or proc.returncode == -signal.SIGXCPU:
            receipt["status"], detail = "EXEC_TIMEOUT", "wall/CPU time limit reached"
        elif proc.returncode == -signal.SIGXFSZ or len(raw_out) >= log_limit or len(raw_err) >= log_limit:
            receipt["status"], detail = "EXEC_PROTOCOL_ERROR", "output byte budget reached"
        else:
            receipt["status"], detail = classify(proc.returncode, raw_out, raw_err)
        if detail:
            receipt["errors"].append(detail)
    except OSError as exc:
        receipt["status"] = "EXEC_IO_ERROR"
        receipt["errors"].append(str(exc))
    except (ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        if attempted:
            receipt["status"] = "EXEC_CRASH"
        receipt["errors"].append(str(exc))
    finally:
        try:
            if len(snapshots) == 2:
                for label, item in receipt["snapshots"].items():
                    item["sha256_after"] = file_hash(Path(item["path"]))
                receipt["snapshot_integrity_verified"] = all(x["sha256_before"] == x["sha256_after"] for x in receipt["snapshots"].values())
                if not receipt["snapshot_integrity_verified"]:
                    raise OSError("snapshot post-execution hash mismatch")
            if pin:
                load_pin(pin_path)
                if file_hash(pin_path) != receipt["pin_sha256"]:
                    raise ValueError("pin changed during execution")
                receipt["artifact_integrity_verified"] = True
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            receipt["artifact_integrity_verified"] = False
            receipt["errors"].append(str(exc))
            # Never publish a verdict if evidence changed, even on normal exit.
            if receipt["status"] in PAIRS.values():
                receipt["status"] = "EXEC_IO_ERROR"
        receipt.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic() - start,
                       stdout_sha256=digest(raw_out), stderr_sha256=digest(raw_err),
                       raw_stdout_base64=base64.b64encode(raw_out).decode("ascii"),
                       raw_stderr_base64=base64.b64encode(raw_err).decode("ascii"))
        with (run / "receipt.json.tmp").open("x") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
        (run / "receipt.json.tmp").rename(run / "receipt.json")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["compiled-pipeline"], required=True)
    for key in ("passport", "certificate", "pin", "output"):
        parser.add_argument(f"--{key}", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--memory-bytes", type=int, default=2 * 1024**3)
    args = parser.parse_args()
    result = verify(args.passport, args.certificate, args.output, args.pin,
                    timeout=args.timeout, memory=args.memory_bytes)
    print(json.dumps(result, sort_keys=True))
    return {"VERIFIED_SUCCESS": 0, "IDENTITY_MISMATCH": 2, "DECODE_ERROR": 3}.get(result["status"], 70)


if __name__ == "__main__":
    raise SystemExit(main())
