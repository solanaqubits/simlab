# Expected-instance-authority 1.0.0 — SIMLAB-δ2, parent SIMLAB-γ1

## Observed deployment, not invented authority

The inherited native executable accepts an operator-selected --context pathname.
It has no credential issuer, task registry or authorization service. The existing
in-memory pin prevents later request replacement; it does not entitle the original
selector. This batch introduces a supervisor API, not an installed identity service.
No default grant, request-derived policy, registry lookup by request ID, hash-based
permission, or fallback to an unbound native invocation exists in this API.

## Separate trusted inputs

A trusted supervisor provides an immutable Policy of complete Grants, and a Job:
(task, specification, revision, executor UID). Each Grant contains issuer UID,
task, specification, revision and the exact approved control bytes. The policy
binds content, not a path or just a digest. Only the supervisor may create/update
these objects. Request senders cannot provide them through the request channel.
A callable Python constructor is not a security capability against arbitrary code
running inside the trusted supervisor. Protecting the supervisor is an assumption.

The gate checks every field, policy membership, observed source UID, issuer !=
executor, matching task/revision and supported spec sql-gap-binary64-1.0.0. An
unknown/absent grant fails closed. Source ownership alone never grants permission.
Byte-exact source approval is a stricter authorization policy than rational
semantic equivalence. Different whitespace in an approval file requires the
supervisor to approve those bytes; equivalent request representations are still
handled by the unchanged native decoder. No historic input schema is changed.

## Concrete Linux connection

snapshot opens a regular non-group/world-writable file relative to an already open,
issuer-owned directory descriptor, without following a final symlink. The directory
must also not be group/world writable. The caller's selection of that directory
handle remains trusted. fstat supplies observed owner; bounded reads and pre/post
metadata checks reject changed files. Exact bytes are compared to the grant.
An immutable Linux memfd with WRITE/GROW/SHRINK/SEAL seals passes those SAME bytes
to the native reader via an inherited descriptor. The original pathname is not
reread. Replacing the source afterwards cannot replace the sealed snapshot.

launch authenticates the SAME Unix socket used for native stdin/stdout using
SO_PEERCRED and compares its peer UID to the trusted Job. The source issuer must
be a different UID. The executable selection is also supervisor-owned. The old
binary remains a low-level mathematical tool; only results obtained through the
authorized supervisor route may carry this new authority claim. A consumer that
accepts arbitrary old-binary output bypasses that route and is outside this claim.

There is no separately deployed issuer/executor pair in this working environment.
Actual same-UID socket launch is deliberately rejected. Positive grant logic uses
synthetic distinct UIDs; actual sealed snapshot/native integration is tested
separately. No positive two-principal production deployment is claimed.

## Lifetime

Job/revision is fixed before launch. All requests in that launched native session
reuse the same sealed context and bounded request budget. New task/revision needs
a new supervisor-approved launch. There is no online revocation or wall-clock
expiry: process termination is the supervisor's revocation mechanism. Old signed
or unsigned receipts cannot authorize another Job; session/task correlation must
remain attached by the trusted caller. Native response schema is unchanged.

## Formal and external boundaries

NumericSQLExpectedAuthority formalizes complete-grant eligibility and composition
with the native mathematical run: accepted implies permitted grant, observed
issuer match, different executor, task/spec/revision match, same SQLInstance and
realRound of that grant's actual G. Missing/denied/self-issued/cross-task/stale
choices reject. A policy can inspect the complete expected input; it is not merely
a name allowlist. Neither the boolean policy function nor the observed UID is
asserted to be authentic by Lean.

Python's byte pin is stronger than the Lean typed-instance policy, but their
universal implementation correspondence is NOT proved. fstat, SO_PEERCRED, seals,
process descriptor inheritance, runtime/compiler, trusted storage and the real
supervisor's entitlement remain external. OS IO is a separate open subobligation.
Third SimLab-to-Lean obligation: OPEN. Hashes are not authorization or authorship.
