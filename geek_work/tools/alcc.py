"""ALCC-JSON-1 bounded prototype. Standard library only; no admission integration.

The expected passport is a verifier-owned input, never taken from the certificate.
Python parsing, exact arithmetic, rendering, and process supervision are NOT verified
implementations. PASS requires two compiled Lean theorems and their axiom audits.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import time
import uuid

PROFILE = "ALCC-JSON-1"
VERSION = "1.0"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
Poly = dict[tuple[int, ...], Fraction]


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 1024 * 1024
    depth: int = 16
    variables: int = 16
    hypotheses: int = 32
    monomials: int = 256
    coefficient_bits: int = 256
    exponent: int = 64
    degree: int = 128
    identifier_bytes: int = 64
    products: int = 100_000
    residual_monomials: int = 10_000
    intermediate_bits: int = 4096
    arithmetic_seconds: float = 5.0
    lean_seconds: float = 30.0
    lean_memory_bytes: int = 2 * 1024**3
    lean_output_bytes: int = 2 * 1024**2
    lean_source_bytes: int = 2 * 1024**2


class Refusal(Exception):
    def __init__(self, status: str, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


def require(ok: bool, reason: str, status: str = "INVALID_FORMAT") -> None:
    if not ok:
        raise Refusal(status, reason)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def passport_id(passport: dict) -> str:
    return sha(canonical({k: v for k, v in passport.items() if k != "problem_id"}))


def parse_canonical(data: bytes, limits: Limits) -> dict:
    require(len(data) <= limits.input_bytes, "input byte limit", "RESOURCE_EXHAUSTED")
    require(data.isascii(), "non-ASCII or BOM input")
    # Bound nesting before json.loads constructs containers. Quoted braces are ignored.
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            require(depth <= limits.depth, "nesting limit", "RESOURCE_EXHAUSTED")
        elif byte in (93, 125):
            depth -= 1

    def integer(token: str) -> int:
        require(token != "-0", "negative zero")
        require(len(token.lstrip("-")) <= 78, "integer digit limit", "RESOURCE_EXHAUSTED")
        value = int(token)
        require(abs(value).bit_length() <= limits.coefficient_bits,
                "integer bit limit", "RESOURCE_EXHAUSTED")
        return value

    def noninteger(token: str):
        raise Refusal("INVALID_FORMAT", "noninteger JSON number: " + token[:24])

    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, "duplicate JSON key")
            obj[key] = value
        return obj

    try:
        value = json.loads(data, parse_int=integer, parse_float=noninteger,
                           parse_constant=noninteger, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refusal("INVALID_FORMAT", "JSON parsing failed") from exc
    require(type(value) is dict, "root must be object")
    require(canonical(value) == data, "noncanonical input bytes")
    return value


def keys(obj: object, expected: set[str]) -> None:
    require(type(obj) is dict and set(obj) == expected, "incorrect object fields")


def identifier(value: object, limits: Limits) -> None:
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_]+", value) is not None,
            "invalid identifier")
    require(len(value) <= limits.identifier_bytes, "identifier length limit", "RESOURCE_EXHAUSTED")


def header(obj: dict) -> None:
    require(obj["format_version"] == VERSION and obj["profile_id"] == PROFILE,
            "unsupported format/profile")
    require(type(obj["problem_id"]) is str and
            re.fullmatch(r"[0-9a-f]{64}", obj["problem_id"]) is not None, "invalid problem_id")


def polynomial(raw: object, n: int, limits: Limits) -> Poly:
    require(type(raw) is list, "poly must be array")
    require(len(raw) <= limits.monomials, "monomial limit", "RESOURCE_EXHAUSTED")
    result: Poly = {}
    previous = None
    for term in raw:
        keys(term, {"coeff", "powers"})
        c, powers = term["coeff"], term["powers"]
        require(type(c) is list and len(c) == 2 and all(type(v) is int for v in c),
                "coefficient must be integer pair")
        num, den = c
        require(num != 0 and den > 0 and math.gcd(abs(num), den) == 1,
                "noncanonical rational")
        require(max(abs(num).bit_length(), den.bit_length()) <= limits.coefficient_bits,
                "coefficient bit limit", "RESOURCE_EXHAUSTED")
        require(type(powers) is list and len(powers) == n and
                all(type(v) is int and v >= 0 for v in powers), "invalid powers")
        require(all(v <= limits.exponent for v in powers) and sum(powers) <= limits.degree,
                "degree limit", "RESOURCE_EXHAUSTED")
        index = tuple(powers)
        require(previous is None or previous > index, "monomials not strictly lex-descending")
        result[index] = Fraction(num, den)
        previous = index
    return result


@dataclass(frozen=True)
class Task:
    problem_id: str
    n: int
    hypotheses: tuple[Poly, ...]
    target: Poly
    multipliers: tuple[Poly, ...]


def bind(expected: bytes, certificate: bytes, limits: Limits) -> Task:
    p = parse_canonical(expected, limits)
    keys(p, {"format_version", "profile_id", "problem_id", "variables", "hypotheses", "target"})
    header(p)
    require(passport_id(p) == p["problem_id"], "expected passport digest invalid", "PROBLEM_MISMATCH")
    variables, hypotheses = p["variables"], p["hypotheses"]
    require(type(variables) is list and type(hypotheses) is list, "expected arrays")
    require(len(variables) <= limits.variables and len(hypotheses) <= limits.hypotheses,
            "task dimensions limit", "RESOURCE_EXHAUSTED")
    for var in variables:
        identifier(var, limits)
    require(len(set(variables)) == len(variables), "duplicate variable")
    n = len(variables)
    ids, fs = [], []
    for h in hypotheses:
        keys(h, {"id", "poly"})
        identifier(h["id"], limits)
        require(h["id"] not in ids, "duplicate hypothesis identifier")
        ids.append(h["id"])
        fs.append(polynomial(h["poly"], n, limits))
    keys(p["target"], {"poly"})
    g = polynomial(p["target"]["poly"], n, limits)
    c = parse_canonical(certificate, limits)
    keys(c, {"format_version", "profile_id", "problem_id", "multipliers"})
    header(c)
    require(c["problem_id"] == p["problem_id"], "certificate does not bind expected task", "PROBLEM_MISMATCH")
    require(type(c["multipliers"]) is list, "multipliers must be array")
    require(len(c["multipliers"]) == len(ids), "multiplier count mismatch", "PROBLEM_MISMATCH")
    qs = []
    for expected_id, q in zip(ids, c["multipliers"]):
        keys(q, {"hypothesis_id", "poly"})
        identifier(q["hypothesis_id"], limits)
        require(q["hypothesis_id"] == expected_id, "hypothesis order/id mismatch", "PROBLEM_MISMATCH")
        qs.append(polynomial(q["poly"], n, limits))
    return Task(p["problem_id"], n, tuple(fs), g, tuple(qs))


def residual(task: Task, limits: Limits) -> Poly:
    operations = sum(len(q) * len(f) for q, f in zip(task.multipliers, task.hypotheses))
    require(operations <= limits.products, "product operation limit", "RESOURCE_EXHAUSTED")
    deadline = time.monotonic() + limits.arithmetic_seconds
    result = dict(task.target)
    for q, f in zip(task.multipliers, task.hypotheses):
        for a, ca in q.items():
            for b, cb in f.items():
                require(time.monotonic() <= deadline, "arithmetic timeout", "RESOURCE_EXHAUSTED")
                power = tuple(x + y for x, y in zip(a, b))
                value = result.get(power, Fraction(0)) - ca * cb
                require(max(abs(value.numerator).bit_length(), value.denominator.bit_length())
                        <= limits.intermediate_bits, "intermediate bit limit", "RESOURCE_EXHAUSTED")
                if value:
                    result[power] = value
                else:
                    result.pop(power, None)
                require(len(result) <= limits.residual_monomials,
                        "residual term limit", "RESOURCE_EXHAUSTED")
    return result


def lean_poly(poly: Poly, evaluation: bool = False) -> str:
    terms = []
    for power, coefficient in sorted(poly.items(), reverse=True):
        rat = f"(({coefficient.numerator} : ℚ) / {coefficient.denominator})"
        factors = [rat if evaluation else f"(MvPolynomial.C {rat} : P)"]
        factors += [(f"(values {i} ^ {e})" if evaluation else f"((MvPolynomial.X {i} : P) ^ {e})")
                    for i, e in enumerate(power) if e]
        terms.append("(" + " * ".join(factors) + ")")
    return " + ".join(terms) or ("(0 : ℚ)" if evaluation else "(0 : P)")


def render(task: Task, limits: Limits) -> str:
    g = lean_poly(task.target)
    fs = [lean_poly(f) for f in task.hypotheses]
    qs = [lean_poly(q) for q in task.multipliers]
    evaluated_g = lean_poly(task.target, True)
    evaluated_rhs = " + ".join(f"(({lean_poly(q, True)}) * ({lean_poly(f, True)}))"
                               for q,f in zip(task.multipliers,task.hypotheses)) or "(0 : ℚ)"
    rhs = " + ".join(f"(({q}) * ({f}))" for q, f in zip(qs, fs)) or "(0 : P)"
    hypotheses = "\n".join(f"    (h_{i} : ev ({f}) = 0)" for i, f in enumerate(fs))
    vanish = "\n".join(f"  have e_{i} : ev (({q}) * ({f})) = 0 := by\n"
                       f"    rw [map_mul, h_{i}, mul_zero]" for i,(q,f) in enumerate(zip(qs,fs)))
    used, seen = [], set()
    for i,pair in enumerate(zip(qs,fs)):
        if pair not in seen:
            used.append(f"e_{i}")
            seen.add(pair)
    if not fs:
        finish = "exact ev.map_zero"
    elif len(fs) == 1:
        finish = "exact e_0"
    else:
        finish = "(simp only [" + ", ".join(["map_add"] + used) + "]; ring)"
    source = f'''import Mathlib.Algebra.MvPolynomial.Funext
import Mathlib.Algebra.CharZero.Infinite
import Mathlib.Tactic.Ring

namespace ALCC
abbrev P := MvPolynomial (Fin {task.n}) ℚ

theorem identity : ({g}) = ({rhs}) := by
  apply MvPolynomial.funext
  intro values
  have left_eval : MvPolynomial.eval values ({g}) = ({evaluated_g}) := by simp
  have right_eval : MvPolynomial.eval values ({rhs}) = ({evaluated_rhs}) := by simp
  have arithmetic : ({evaluated_g}) = ({evaluated_rhs}) := by ring
  exact left_eval.trans (arithmetic.trans right_eval.symm)

theorem consequence (ev : P →+* ℚ)
{hypotheses}
    : ev ({g}) = 0 := by
{vanish}
  calc
    ev ({g}) = ev ({rhs}) := congrArg ev identity
    _ = 0 := by {finish}

end ALCC
#check ALCC.identity
#check ALCC.consequence
#print axioms ALCC.identity
#print axioms ALCC.consequence
'''
    require(len(source.encode()) <= limits.lean_source_bytes, "Lean source size limit", "RESOURCE_EXHAUSTED")
    return source


def audit_output(output: str) -> dict[str, list[str]]:
    found = {}
    for theorem in ("ALCC.identity", "ALCC.consequence"):
        pattern = rf"'{re.escape(theorem)}' (?:depends on axioms: \[([^\]]*)\]|does not depend on any axioms)"
        matches = list(re.finditer(pattern, output))
        require(len(matches) == 1, "missing/ambiguous axiom audit: " + theorem, "VERIFICATION_ERROR")
        axioms = {a.strip() for a in (matches[0].group(1) or "").split(",") if a.strip()}
        require(axioms <= ALLOWED_AXIOMS, "disallowed axiom dependency", "VERIFICATION_ERROR")
        found[theorem] = sorted(axioms)
    return found


def run_lean(source: Path, project: Path, limits: Limits, details: dict) -> str:
    require((project / "lean-toolchain").is_file() and (project / "lake-manifest.json").is_file(),
            "trusted Lean project missing", "VERIFICATION_ERROR")
    lake = shutil.which("lake")
    require(lake is not None and shutil.which("systemd-run") is not None,
            "lake/systemd-run unavailable; no unbounded fallback", "VERIFICATION_ERROR")
    unit = "alcc-" + uuid.uuid4().hex
    lean_command = [lake, "env", "lean", "-j1", "-DwarningAsError=true",
               "-DmaxHeartbeats=2000000", str(source.resolve())]
    command = ["systemd-run", "--user", "--wait", "--pipe", "--quiet", "--unit=" + unit,
               "--working-directory=" + str(project.resolve()),
               "-p", f"MemoryMax={limits.lean_memory_bytes}", "-p", "MemorySwapMax=0",
               "-p", f"RuntimeMaxSec={limits.lean_seconds}", "-p", "LimitCORE=0",
               "-p", f"LimitFSIZE={limits.lean_output_bytes}", "--"] + lean_command
    details.update(command=command, cwd=str(project.resolve()),
                   toolchain=(project / "lean-toolchain").read_text().strip(),
                   lake_manifest_sha256=sha((project / "lake-manifest.json").read_bytes()),
                   memory_measure="systemd user cgroup MemoryMax; swap disabled", unit=unit)

    start = time.monotonic()
    with (source.parent / "lean.log").open("wb") as output:
        process = subprocess.Popen(command, cwd=project, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=limits.lean_seconds + 5)
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=10)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            details.update(returncode=process.returncode, elapsed_seconds=time.monotonic() - start)
            raise Refusal("RESOURCE_EXHAUSTED", "Lean wall-clock timeout")
        finally:
            state = subprocess.run(["systemctl", "--user", "show", unit,
                                    "-p", "Result", "-p", "MemoryPeak", "-p", "ExecMainStatus"],
                                   capture_output=True, text=True, timeout=10)
            details["systemd_state"] = state.stdout.strip()
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=10)
            subprocess.run(["systemctl", "--user", "reset-failed", unit], capture_output=True, timeout=10)
    details.update(returncode=code, elapsed_seconds=time.monotonic() - start)
    output = (source.parent / "lean.log").read_text(errors="replace")
    require(not any(f"Result={r}" in details["systemd_state"] for r in ("oom-kill", "timeout")),
            "Lean cgroup memory/time limit", "RESOURCE_EXHAUSTED")
    require(code not in (-signal.SIGXCPU, -signal.SIGXFSZ), "Lean OS resource limit", "RESOURCE_EXHAUSTED")
    if code != 0 and ("out of memory" in output.lower() or "maximum number of heartbeats" in output.lower()):
        raise Refusal("RESOURCE_EXHAUSTED", "Lean reported resource exhaustion")
    require(code == 0, "Lean failed; no mathematical rejection inferred", "VERIFICATION_ERROR")
    return output


def verify(expected: bytes, certificate: bytes, project: Path, evidence: Path,
           limits: Limits = Limits()) -> dict:
    """Evidence must be new. Never overwrite a prior result or accept Python alone."""
    evidence.mkdir(parents=True, exist_ok=False)
    report = {"status": "VERIFICATION_ERROR", "profile_id": PROFILE,
              "expected_bytes_sha256": sha(expected), "certificate_bytes_sha256": sha(certificate),
              "input_hash_scope": "supplied bytes; CLI oversize reads are capped at input_bytes+1",
              "limits": asdict(limits), "implementation_sha256": sha(Path(__file__).read_bytes()),
              "lean": {}, "identity_basis": "not_checked", "axioms": {},
              "boundary": "Python/parser/renderer/process implementation and input authority are not formally verified"}
    try:
        task = bind(expected, certificate, limits)
        report["problem_id"] = task.problem_id
        # Preserve accepted syntax inputs (bounded) for independent reproduction.
        (evidence / "expected.json").write_bytes(expected)
        (evidence / "certificate.json").write_bytes(certificate)
        difference = residual(task, limits)
        report["identity_basis"] = "Python Fraction exact residual; not a Lean theorem"
        if difference:
            power = max(difference)
            value = difference[power]
            report["nonzero_coefficient"] = {"powers": list(power), "coeff": [value.numerator, value.denominator]}
            raise Refusal("IDENTITY_MISMATCH", "nonzero rational polynomial residual")
        source = render(task, limits)
        source_path = evidence / "Certificate.lean"
        source_path.write_text(source, encoding="utf-8")
        report["lean_source_sha256"] = sha(source.encode())
        output = run_lean(source_path, project, limits, report["lean"])
        report["axioms"] = audit_output(output)
        report.update(status="PASS", reason="compiled polynomial identity and consequence; allowed axioms",
                      identity_basis="Lean kernel, generated MvPolynomial identity; Python-to-Lean translation remains trusted")
    except Refusal as exc:
        report.update(status=exc.status, reason=exc.reason)
    except MemoryError:
        report.update(status="RESOURCE_EXHAUSTED", reason="Python memory allocation failure")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.update(status="VERIFICATION_ERROR", reason=type(exc).__name__ + ": " + str(exc))
    artifacts = {p.name: sha(p.read_bytes()) for p in evidence.iterdir() if p.is_file()}
    report["artifacts_sha256"] = artifacts
    (evidence / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True, help="verifier-owned canonical passport")
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--lean-project", type=Path, required=True, help="trusted local Lake project; never supplied by witness")
    parser.add_argument("--evidence", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    limits = Limits()
    try:
        # Bounded reads: oversize inputs are classified by the parser without loading whole files.
        with args.expected.open("rb") as f:
            expected = f.read(limits.input_bytes + 1)
        with args.certificate.open("rb") as f:
            cert = f.read(limits.input_bytes + 1)
        report = verify(expected, cert, args.lean_project, args.evidence, limits)
    except OSError as exc:
        print(json.dumps({"status": "VERIFICATION_ERROR", "reason": str(exc)}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
