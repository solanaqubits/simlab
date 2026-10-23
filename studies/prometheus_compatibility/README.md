# Prometheus compatibility audit: public metadata snapshot

This package checks which results may **not** be combined into an end-to-end device claim. It publishes 14 editorial claims, 38 selected scenario records, 28 comparison groups and 77 field/requirement rules. Eight claims map to existing rules; six retain additional editorial boundaries. Metadata agreement is never a physical or cryptographic certificate.

Run with Python 3.10 or later, using only the standard library:

```sh
python3 -B studies/prometheus_compatibility/check.py --json
python3 -B -m unittest discover -s studies/prometheus_compatibility -p 'test_*.py' -v
```

The checker validates bundle hashes, typed values, units, metric scopes, references, claim coverage and recomputed group statuses. The published baseline contains 11 blocked groups, 2 unsupported groups, 13 mismatches and 2 metadata-only matches. Tests deliberately mutate inputs to check rejection behavior. These are metadata checks, not new simulations or Lean kernel runs.

`registry.json` records the exact accepted private snapshot identifier and digests, as provenance identifiers rather than publicly accessible source claims. It also links 11 mathematical source files at public Leanbook commit `aa5f03f2e1cf8777a819946bfd6328c3f66c3f7b`. Their bytes were compared with the accepted Lean source revision before export. Public readers can inspect those files and verify their recorded SHA-256 digests. The offline checker checks link structure, not network availability or theorem applicability.

[Public Leanbook source snapshot](https://github.com/solanaqubits/leanbook/tree/aa5f03f2e1cf8777a819946bfd6328c3f66c3f7b/Verification) supplies the mathematical companions. This SimLab package supplies selected compatibility metadata; it does not export the private scientific runners, complete source corpus or grant application. See [LIMITS.md](LIMITS.md) for the evidence boundary and [MANIFEST.json](MANIFEST.json) for the explicit file allowlist.

The `historical_verification` section reports earlier private checks. Running this public package does **not** reproduce those source-blob audits, their test counts, or their simulations. Hashes establish byte identity within the selected snapshot, not independent truth or authorship. No hardware admission or authorization is granted; the Third Obligation remains **OPEN**.
