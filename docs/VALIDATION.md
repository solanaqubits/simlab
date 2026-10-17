# Standalone public validation — β1 for the registered exported scope

The migration root commit remains in this independent public history. No private
Git history was imported. The source allowlist and shared byte hashes are in
EXPORT.json. Tree-local validation scope and dependency revisions are in
VALIDATION_SCOPE.json. The private numerical corpus is deliberately not exported.

Final public gate: strict Lean build passed; 40 tests passed, no errors or skips.
These are 10 inherited kernel regression invocations, 3 relocation smoke tests,
26 authority adapter tests and 1 authority kernel invocation with 8 examples.
These counts overlap private checks and replays and must not be added as distinct
mathematical cases. Build jobs include cached dependencies, not fresh compilations.

The full source-bound audit covers 21 formal modules / 2357 declarations and uses
only propext, Classical.choice and Quot.sound. The independent dependency auditor
agrees. This specific audit evidence is reused after exact equality checks on all
21 sources, import scope, audit template, Lake configuration, locked dependencies
and the installed toolchain. Public build, tests and catalog checks run in this
public tree. A larger historical Leanbook audit is not claimed as a public audit.

The new NumericSQLExpectedAuthority model proves that acceptance entails complete
grant eligibility and correct rounding of the same expected SQLInstance. It proves
refusal of missing/denied/self-issued/cross-task/stale grants and different inputs.
The authority policy and observed source principal are external parameters.

The Python supervisor API checks task/spec/revision, explicit grant membership,
source ownership and permissions, Unix peer credentials and issuer/executor
separation. It passes exactly approved bytes through an immutable sealed memfd to
the native checker. No hash or filename grants authority. See authority/CONTRACT.md.

There is no deployed two-principal authorization service in the test environment.
Actual same-UID launch is rejected. Positive policy tests with synthetic UIDs are
separate from real sealed-file/native tests; no production authorization is claimed.
Two isolated replays of the 26 adapter tests agree. Their repeats are not new cases.
No generator or numerical search is part of that replay.

No release tag is assigned. β1 means the stated finite and formal gate passed; it
does not close OS/runtime assumptions, the supervisor's actual entitlement, Python,
external parsing/serialization, SHA-256, data authenticity or physical validity.
The third SimLab-to-Lean obligation remains OPEN.
