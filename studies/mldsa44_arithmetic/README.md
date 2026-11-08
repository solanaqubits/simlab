# ML-DSA-44: frozen Cairo candidate and arithmetic proofs

This package publishes the completed Stage 11 Cairo candidate and a bounded,
offline source replay. It accompanies the public Leanbook modules
[MlDsaPackedPredicate](https://github.com/solanaqubits/leanbook/blob/f891396e8e98f00d03beef1b1263ee32258a3cc0/Verification/MlDsaPackedPredicate.lean)
and [MlDsaWtBranch](https://github.com/solanaqubits/leanbook/blob/f891396e8e98f00d03beef1b1263ee32258a3cc0/Verification/MlDsaWtBranch.lean).
This is postquantum signature research, separate from entanglement-repeater models.

## Source and reproduction scope

- `candidate.patch` is the unchanged patch against benchmark commit
  `78c83599f57ecb28847ba3ebc4528598318129b8` (SHA-256
  `068f95d97bd1aa44940eaebe5e46e665653e780e1ce999be7fe5bde44460497e`).
- `candidate/` contains its 12 affected production Cairo files.
- `baseline/` contains the original `lib.cairo`; the other 11 affected paths are
  new files. These exact bytes were checked against the selected upstream commit.
- `context/` preserves the original Scarb manifests and toolchain pins. It is
  contextual metadata, not a complete buildable workspace.
- `manifest.json` pins the selected source bytes and the derived historical
  summary. Private Git history, raw execution logs, compiler artifacts and
  unrelated research stages are outside this public package.

From the SimLab repository root, with Python 3.10+ and Git available:

```sh
python3 -B studies/mldsa44_arithmetic/check_package.py
python3 -B -m unittest tests.test_mldsa_public_package -v
```

The checker creates a temporary Git index for the baseline subset, checks and
applies the fixed patch, verifies the exact set of 12 changed paths, and compares
all output source bytes. It requires no network, Cairo compiler or archived
runtime. The five tests include corrupted patch, candidate and baseline rejection
and rejection of an unexpected production path. The path-scoped public CI runs
these checks and the existing catalog check.

This establishes source correspondence for the affected subset, not reconstruction
of the entire upstream Git commit. Building Cairo requires a separate full upstream
checkout at the stated commit and its pinned dependencies; apply `candidate.patch`
there. This export did not compile Cairo or run a new benchmark.

## Recorded results

The historical Stage 11 experiment used Scarb/Cairo 2.18.0 and snforge 0.59.0.
Both reference (Stage 10) and candidate passed 593 tests; paired per-test gas
matched in all 593 cases. Three strict account builds and matching production
replay artifacts were recorded.

| Measurement | Stage 10 | Stage 11 | Change |
| --- | ---: | ---: | ---: |
| Paired gas | 168511857 | 168511857 | 0 |
| CASM felts | 81805 | 81782 | -23 |
| Sierra JSON bytes | 4063744 | 4062967 | -777 |

Stage 11 leaves 138 felts below the recorded 81920 CASM limit. The 520 gas
improvement relative to the original predecessor came from Stage 6; it is not a
new Stage 11 result. [results.json](results.json) records these finite-corpus
observations and the original report/manifest digests. They remain historical
measurements, not independently repeated public performance results or all-input
guarantees. Official submission processing is separate from this export.

## Formal companion and attribution

The two Lean modules retain 15 + 55 original arithmetic theorems and their exact
hypotheses, plus two registry wrappers. They cover packed range predicates,
no-carry/no-wrap bounds and conditional repair. Split-word checks are conservative;
the repair premise `part = 0 → valid` still requires application-specific discharge.
Stage 11 rotations do not acquire a Lean proof through this publication.

[lean-companion.json](lean-companion.json) pins the public source hashes and
[successful Leanbook main CI](https://github.com/solanaqubits/leanbook/actions/runs/42454944423).
These are arithmetic model proofs, not a proof of complete ML-DSA security,
constant-time execution, Cairo compiler refinement or FIPS certification.

The predecessor candidate is credited to **rukafe0x**, job
`mj_2c1f51cffb854f4d90254e8d6b7b6500`. Its work is not claimed as new here.
Original source notices and [MIT / third-party licensing](UPSTREAM-LICENSE) are
preserved. The source patch and candidate files are byte-identical to the accepted
Stage 11 package; the public checker and documentation describe this narrower
export scope explicitly.
