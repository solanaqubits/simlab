# Quantum and hardware contract registry

This metadata package indexes twelve published Leanbook contracts. Each entry
links to exact public source and card commits, states assumptions and limits,
and binds source bytes by SHA-256. Proofs remain in Leanbook; this directory does
not duplicate a formal library or turn a simulation into a device certificate.

Run `python3 -B studies/quantum_contracts/check.py` for offline package integrity.
With an existing Leanbook Git checkout, add `--lean-repo /path/to/leanbook` to
compare all twelve pinned Git blobs and the copied check summary. No network
fetch or Lean execution occurs. Run the package unittest for mutation controls.

See [registry](registry.json), [reported public checks](lean_checks.json) and
[limitations](LIMITS.md). A later independent whole-stack audit is separate.
Private conversations, research journals and grant documents are not exported.
