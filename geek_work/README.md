# Geek Work 1.0.0

Local tools for preparing documents, tracking claims and reviewing reproducible
research artifacts. Python 3.12; the core uses the standard library. This is the
first consolidated public Geek Work release in SimLab. It is a component release:
it does not re-version or re-certify the Leanbook proof library.

## Start without installing anything

From the repository root:

```sh
python3 -B geek_work/check.py
python3 -B geek_work/tools/knowledge.py --help
python3 -B geek_work/tools/geek_work_finalize.py --help
python3 -B geek_work/tools/geek_work_manuscript.py --help
python3 -B geek_work/tools/geek_work_document_index.py --help
python3 -B geek_work/tools/geek_work_alcc_timing_replay.py --help
```

The first command verifies the exact package inventory and runs the complete
bundled synthetic/protocol suite. Tests create temporary fixtures and bounded
local processes; provider and container calls are mocked. They need no private
knowledge graph, model account, network, Lean installation or paid API call.

Use explicit input/output paths with the individual CLIs. A new package requires
a new output directory. Preserve the original bytes and retain the printed SHA
outside the package before moving it. Verification checks the declared contract;
it does not establish authenticity when package and anchor share an untrusted origin.

## Included capabilities

| Area | Tools and boundaries |
| --- | --- |
| Editorial intake | Chunked snapshots, reversible edits, protected spans, transactional finalize and cost/intervention records. Unknown cost remains null. |
| Knowledge | Versioned cards, selected Markdown views, bounded memory requests, context profiles and recovery. No private graph is included. |
| Documents | Manuscript proposals, individual/batched hunks, source-bound claims, protected numbers, file operations, Git preflight and review status. |
| Rendering | Separate PDF/LaTeX/Typst request, artifact and replay contracts; page selection, OCR candidate review and diagnostics. OCR is not scientific verification. |
| Retrieval | Document indexes, source ranges, retrieval assessment and query-fidelity records. Coverage is not answer correctness. |
| Review | Draft annotations, council comparison, abstentions, session ledgers and explicit evidence limits. Agreement is not independent validation. |
| Research | Experiment passports, fixed exact-arithmetic controls, bounded execution series and artifact inspection. No general autonomous scientist is installed. |
| Cryptography | Proof-envelope and nonce/recovery contracts, EVM evidence checks, rational ALCC controls and offline timing replay. No new proof system or deployed verifier is claimed. |
| Intake | Read-only Hexagon/alphaXiv adapters and source snapshots. Remote metadata is not peer review. |

See [TOOLS.md](TOOLS.md) for the exact module inventory and
[RELEASE.md](RELEASE.md) for qualifications and excluded scope.

## Optional external runtimes

Nothing is installed, downloaded, scheduled or connected during setup or tests.
Live PDF/LaTeX/Typst rendering requires separately provisioned, pinned binaries or
container images. Runtime source and historical profiles are supplied; an image
hash does not make that image available on another machine. Missing runtimes must
remain unavailable rather than silently falling back. Provider adapters likewise
require a separately installed CLI/account and explicit data-disclosure approval.
No provider is selected by this release, and no credentials are bundled.

The disposable CI operator is documented in
[ci/self-hosted/README.ru.md](ci/self-hosted/README.ru.md). Public pull requests
use hosted runners. Do not expose a privileged self-hosted runner to unreviewed code.

## Compatibility and trust

Version 1.0.0 uses the project's numeric alpha/beta/gamma convention: the leading
number identifies the consolidated architecture, not an unstable prerelease.
Existing artifact schema names remain unchanged. Read each schema's explicit
limits; future incompatible formats need a new schema identifier.

This release does not certify physical claims, independent annotation, model
quality, compiler correctness, production admission or a general ALCC speedup.
The third SimLab-to-Lean obligation remains OPEN. Hashes bind bytes, not authority.
The code is under the repository's Apache-2.0 license, also included here.

## Claim Review 0.1 extension

The local Extraction → Adapter → Transport pipeline now includes a loopback HTTP server
and a manual browser editor. See [Coordinator guide](contracts/claim-review-api/COORDINATOR.ru.md).
This main-branch addition does not replace the archived 1.0.0 release or its tags.
No semantic-equivalence, source-completeness or Lean-kernel replay guarantee is added.
