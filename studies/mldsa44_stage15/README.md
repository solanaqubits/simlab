# ML-DSA-44 Stage 15: frozen selected-source replay

This public package preserves the accepted Stage 15 candidate independently of the
historical [Stage 11 package](../mldsa44_arithmetic/README.md). It contains the exact
production patch, twelve candidate Cairo files, the selected baseline lib.cairo,
MIT upstream license and recorded toolchain context. Private Git history, raw
operational logs, upstream Git bundles, compiled artifacts and host diagnostics
are excluded.

Upstream base: `78c83599f57ecb28847ba3ebc4528598318129b8`.
Patch SHA-256: `cfbe31ae486aca6f79954b154d78da9a5be4190731c53064caf633b00cf4c155`.
[Public candidate](https://postquantum.provably.fast/code?job=mj_51c7a1c99b6f41ee96bc62c13b950396).

## Attribution

Retain [UPSTREAM-LICENSE](UPSTREAM-LICENSE) and inherited source attribution.
Stage 15 combines ardianreffa's NTT batching (including inherited binharold work),
rukafe0x's result-only `ubr` / `cbr` recursion, and solanaqubits' `pt4` / `rt1`.
It restores two direct `i2` sites relative to the leader, for five total. No claim
of exclusive authorship of the inherited implementation is made.

## Reproduce the exported source identity

```sh
python3 -B studies/mldsa44_stage15/check_package.py
python3 -B -m unittest tests.test_mldsa_stage15_public_package -v
```

The checker uses Python and Git, applies the patch to the selected baseline subset
and compares all twelve resulting sources. It performs no network requests, Cairo
compilation, benchmark or Lean verification. This is not a complete upstream
checkout. Source hashes establish identity, not correctness or receipt authenticity.

[Recorded observations](results.json) include mean gas 168436945, CASM 81499/81920,
Sierra 4082603/4089446 and historical 805/805 candidate/control tests. These are
historical observations, not fresh measurements or a current leaderboard claim.
The validation-cap flag remains false. No all-input speedup is asserted.

The arithmetic/compiler research in Leanbook has separate assumptions and evidence.
This source replay does not establish full Cairo refinement, whole-verifier
correctness, ML-DSA security or quantum hardness. SimLab's third obligation is OPEN.
