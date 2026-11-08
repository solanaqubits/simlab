# Claim Extraction–Transport Adapter 0.1

`geek_work/tools/geek_work_claim_adapter.py` builds **one** transport pair
from a manually prepared extraction record and an existing pinned claim-map
bundle. It replays both existing validators; it accepts no saved validation
report as authority. No new extraction, semantic reasoning, Lean execution,
network call, UI, knowledge-graph update or publication is performed.

## Coordinator inputs

CLI requires:

- `--source-snapshot` and independent `--source-sha256`;
- `--expectations` and independent `--expectations-sha256`;
- `--record`;
- `--claim-map-bundle` and independent `--claim-map-bundle-sha256`;
- `--source-claim-id`, `--source-revision`, and a **new** `--output` directory.

The third hash is SHA-256 of the claim-map **bundle's `manifest.json` bytes**, as
required by Claim Transport. It is not SHA-256 of `map.json`. The existing bundle
reader verifies exact file sets, individual hashes, bounded regular files and
reproduces claim-map reports. The selected claim and declared source revision are
coordinator arguments, not candidate-selected defaults. The revision is metadata;
claim-map does not prove a revision history. Pins identify bytes relative to
coordinator input; they do not authenticate the coordinator or prove source truth.

Limits are inherited: one source up to 1 MiB, extraction expectations+record up to
2 MiB combined, at most 32 atoms per role and quantities, 64 coverage checks and
32 questions. The source claim-map bundle has its own 16 MiB bound. Generated
plan+candidate obey the Transport 2 MiB bound. Strict JSON/Unicode and regular-file
rules remain unchanged. There are no new dependencies beyond the standard library
and existing local tools.

## Admission and mapping

1. Run `extraction.check` over current bytes and external pins. Require the exact
   string `status == "record_consistent"`.
2. Require the supplied editorial state `ready_for_transport`.
3. Require `unresolved_questions == []`, including no closed or optional entries.
   This is an **adapter restriction**; the Extraction validator is unchanged and
   can retain closed questions in its own records.
4. Replay the pinned claim-map bundle. Require the selected claim to exist.
5. Bind the source to that claim: selected quote must equal the claim statement;
   either the source snapshot hash and offsets equal the statement's document,
   or the claim cites a material with the same hash, commit and exact span.
   Identical words in an unrelated snapshot are insufficient. Repository/path
   labels are metadata and can differ between a material's packaged path and
   original path; this check is not Git provenance authentication.
6. Project **all five** atom roles with their IDs, exact strings and hashes.
   Compare assumptions through the existing `transport.adapt` rules. Preserve
   scope, evidence state/IDs, non-claims and mathematical open obligations, and
   compare them to the source card. Do not silently replace them with template
   defaults. Order of unique collections is canonicalized, not text content.
7. Create `plan.json` and a single initial `candidate.json`; run the existing
   `transport.check`. Only `contract_preserved` permits a successful build.

The plan pair is `extraction-pair`; source selection/revision come from CLI,
candidate ID/revision from the pinned editorial record. The newly generated plan
hash is a **derived artifact**, not a separate independent approval event. For
later third-party candidate checks the coordinator must independently deliver
that plan hash to Claim Transport.

### Units

| Editorial interpretation | Transport `unit` |
| --- | --- |
| `unknown` | Literal `unknown`, only when both raw and canonical units are null. |
| `literal` | Exact `unit_raw`; canonical must be null or identical. |
| `dimensionless` | Literal `dimensionless`; requires the already pinned editorial basis; canonical null or identical. |
| `mapped` | Explicit non-null `unit_canonical` with the pinned editorial basis. |

Ambiguous mappings block assembly. No automatic normalization, conversion, unit
inference from `ℝ`, or `unknown → dimensionless` occurs. The validator checks the
presence and preservation of editorial mapping assertions, **not their semantic
adequacy**. A separately ready record with unknown units can preserve `unknown`;
the orbit control is blocked because its editorial review is unresolved.

Extraction-only spans, unit provenance, coverage and checklist details are not
fields of the existing Transport contract. They remain intact in the packaged
record, expectations and source snapshot; they are never claimed to have become
Transport semantic guarantees.

## Outputs and errors

A successful directory contains:

- `source-snapshot.txt`, `expectations.json`, `record.json` (unchanged input bytes);
- fresh `extraction-report.json`;
- `plan.json`, `candidate.json`, fresh `transport-report.json`;
- `adapter-report.json` and `manifest.json` with input pins and per-file hashes.

The original claim-map bundle remains an external pinned dependency and must be
retained for replay. The directory is exclusively created; existing outputs are
never overwritten. The manifest is written last as a completion marker. On I/O
failure a partial directory is retained without a completed manifest; power-loss
atomicity and durable-storage guarantees are not claimed.

| Adapter status | Meaning | Exit |
| --- | --- | --- |
| `built` | Both validators and all assembly checks passed. | 0 |
| `build_blocked` | Editorial readiness, mapping or contract compatibility failed. | 1 |
| `invalid_input` | Input/binding/hash/schema/budget error. | 2 |

Rejected builds contain diagnostic receipts, **no plan or candidate**. A fresh
Extraction or Transport report is included only if that phase ran. The adapter
report gives `stage` and a reason, e.g. `extraction_not_record_consistent`,
`editorial_state_not_ready`, `unresolved_questions_not_empty`,
`unit_mapping_ambiguous`, `source_not_bound_to_selected_claim`, or
`claim_map_inconsistent: …`. There is no `admitted` boolean implying proof.
CLI syntax/output-path errors are process errors; they do not overwrite evidence.

All four assurance flags remain false in every adapter receipt, validator report
and package manifest: `semantic_equivalence_verified`, `source_extraction_complete`,
`kernel_replayed`, `publication_authorized`.

## Controls and future UI compatibility

[Ready fixture and CLI](../../examples/claim-adapter-ready/README.ru.md),
[regression tests](../../tests/test_claim_adapter.py).

The prior orbit record remains `needs_context`. Do not resolve its unit annotation
just to make a green demonstration. The positive fixture is a clearly labelled
synthetic hypothesis, not a new mathematical result.

A future UI must render all existing Extraction outcomes (`record_consistent`,
`needs_context`, `review_required`, `invalid_input`) and all six inherited claim-map
evidence states. Coverage keeps `condition_not_inspected` as the wire value;
`missing_extracted_atom` is a separate finding, not a fourth observation enum.
Atom identity includes the exact quotation location as well as text/hash. UI work
and changes to those existing contracts are outside this implementation.
