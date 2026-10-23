# Ten conditional Prometheus research audits: metadata supplement

This is an additive historical summary, prepared for public synchronization. It does not replace the earlier `prometheus_compatibility` snapshot. The private consolidation identifier is recorded in [snapshot.json](snapshot.json). Private SHA identifiers are provenance references; public readers cannot inspect those private sources from this package.

The five historical verification scopes cover ten questions. Counts are reported by stage and must not be added as disjoint tests or declarations. No historical scientific run is reproduced by this package. The 38-scenario projection and 14 negative predicates are historical scopes, not a current repository-wide count or a public implementation of those predicates.

Run with Python 3.10+ (standard library only):

```sh
python3 -B studies/prometheus_program/check.py
python3 -B -m unittest discover -s studies/prometheus_program -p 'test_*.py' -v
```

The checker verifies package hashes, schema relationships, historical scope separation and OPEN markers. It does not verify private source bytes, theorem applicability, simulations or quantum security. Its mutation tests are packaging tests, not an independent scientific audit. See [LIMITS.md](LIMITS.md).

## Public formal companions

Nine additional Prometheus Lean modules are now available in the pinned public
Leanbook revision recorded in [the source map](../../docs/prometheus-lean-sources.json).
That map supplies exact source hashes, public links and the scoped verification
receipt. It does not change the historical numerical snapshot or certify physical
realizability, positive SKR or hardware WCET.
