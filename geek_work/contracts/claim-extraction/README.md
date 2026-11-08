# Claim Extraction 0.1 — bounded editorial record validator

`geek_work/tools/geek_work_claim_extraction.py` checks a **manually prepared**
record against an externally pinned source snapshot and editorial expectations.
It does not extract claims, decide semantic completeness, run Lean, authorize
publication, or export Claim Transport plans. Runtime uses Python's standard
library and existing local helpers; no network, subprocess or model calls.

## Trust and bounds

The coordinator supplies `--source-sha256` and `--expectations-sha256` separately
from the candidate. The candidate cannot select these pins. SHA-256 identifies
bytes relative to these inputs, not authorship or independent approval. Repository
and commit labels are checked metadata, not live Git queries. A malicious or
incomplete coordinator ledger remains outside the assurance boundary.

One record and one UTF-8 source per invocation; source limit 1 MiB, combined
expectations + record limit 2 MiB. Strict JSON rejects duplicate keys, floats,
NaN, excessive nesting (32), and oversized integer tokens. At most 32 atoms per
role, 32 quantities, 64 coverage rows, 32 questions, 32 spans per coverage group;
texts are nonempty and at most 4,000 Unicode codepoints. Exactly ten distinct
checklist IDs are required. Integer fields reject booleans. Input leaf files must
be regular non-symlinks; paths are supplied by the operator, not followed from
record metadata. The source is read once as bytes; line endings and Unicode are
not normalized. Output uses exclusive creation and never overwrites a receipt.

## Wire objects

These are new executable formats, distinct from the historical **drafting
example** `FILLED-ORBIT-RECORD.json`. Unknown and missing object fields fail.
The implementation is the authoritative structural validator, not a claim that
JSON Schema can verify hashes or semantic extraction. No new JSON Schema parser
or schema-based semantic checker is supplied.

Expectations use `schema = geek-work-claim-extraction-expectations-1` and the
following common fields; the record uses `geek-work-claim-extraction-record-1`.

| Common field | Contents / verification |
| --- | --- |
| `extraction_id` | Stable lowercase ID, at most 64 characters. |
| `source_snapshot` | `repository`, full 40-hex `commit`, safe relative `file_path`, 64-hex `sha256`, `encoding: UTF-8`. Metadata must match the ledger. CLI controls the actual snapshot path. |
| `selected_span` | `start_char`, `end_char`, `quote`; nonempty half-open Unicode codepoint interval. |
| `claim_type` | `definition`, `hypothesis`, `computation_result`, or `theorem`. Assignment remains editorial. |
| `reported_evidence_state` | Exact inheritance of any existing claim-map state: `source_only`, `hypothesis`, `formal_reported`, `empirical_reported`, `reference_only`, `open`. `checked_here` is not accepted. |
| `contract` | Five atom roles, scope, quantities, evidence IDs, non-claims and open mathematical obligations. |
| `coverage_checks` | Pinned editorial observations and expected role/ID bindings. |
| `unresolved_questions` | Extraction issues with `item_id`, `description`, boolean `required_before_transport`, nullable nonempty `resolution`. |

Record-only fields: positive integer `revision`, `editorial_state` (`draft`,
`needs_context`, `ready_for_transport`), `checklist`, `review`, `assurances`.
`review` has nonempty `reviewer_record`, `reviewed_at`, `decision_notes`; these are
reported editorial metadata, not authenticated identity or timestamp proofs.
All four assurance booleans must be literally `false`.

The contract contains `premise_atoms`, `conclusion_atoms`, `domain_atoms`,
`quantifier_atoms`, `negation_atoms`, `scope`, `quantities`, `evidence_ids`,
`non_claims`, `open_obligations`. Each atom has `atom_id`, `text_raw`,
`text_sha256`, `quote_span`. Its text equals the exact source slice and its UTF-8
SHA-256. Reusing an ID with another text, hash or location fails, including across
roles and between ledger/candidate. The same exact atom may occur in several
roles. Role assignment changes require review; there is no historical ID registry
beyond the supplied pinned ledger.

Quantities have `quantity_id`, `symbol` (editorial label), `exact_literal`,
`literal_span`, `unit_raw`, `unit_span`, `unit_interpretation`, `unit_canonical`,
`unit_mapping_basis`. Literal spans equal the exact string; present raw units
have their own exact span. Null raw unit requires null unit span. `unknown`
requires null canonical unit. `dimensionless`/`mapped` require a nonempty basis,
which is only a **pinned editorial assertion**, not machine proof of sufficiency.
Any quantity change relative to the ledger requires review. No conversion or
normalization is performed. This version binds spans in the one selected source
fragment; multi-source context dossiers remain a future extension.

Coverage rows retain the manual template fields: `check_id`,
`expected_condition_editorial_text`, `expected_role`, `source_observation`,
`inspected_spans`, `evidence_spans`, `extracted_atom_ids`, `finding`, `review_notes`.
All quoted spans must lie inside the selected fragment. Present observations need
inspected evidence; referenced atoms must exist in the declared role and quote
that evidence. Absence requires an inspected scope and no fictitious atom/evidence.
Uninspected observations cannot contain extracted atoms/evidence. Absence is an
editorial observation, not a machine search result. Present quantitative context
can be described by evidence spans without atom IDs, but remains pending in this
version; it is not silently promoted to an extracted atom.

Coverage and questions are compared to the external ledger. Deleting a condition
and its coverage row cannot erase the ledger expectation. Missing expected atoms
produce `missing_extracted_atom:<role>` (if remaining links are structurally valid).
A stale dangling atom reference instead makes the record invalid. Removing a
question, making it optional or inventing a resolution cannot override the pinned
mandatory open question. To accept a resolution, the coordinator must separately
review and supply a revised ledger and hash; candidate text alone is insufficient.

The ten checklist IDs are those in the original template. Each has `id`, `state`
(`checked`, `needs_context`, `not_inspected`), and nullable `notes`. The validator
checks the declarations and their consistency. It does not independently perform
the semantic/editorial work represented by `checked`.

## Outcomes

| Outcome | Meaning | CLI exit |
| --- | --- | --- |
| `record_consistent` | Mechanical checks and ledger comparison pass; retains supplied editorial state, including `draft`. | 0 |
| `needs_context` | Mechanical comparison passes, but editorial work remains or supplied state is `needs_context`. | 1 |
| `review_required` | Structurally valid change from the pinned ledger. | 1 |
| `invalid_input` | Binding/schema/budget failure or inconsistent readiness declaration. | 2 |

An open mandatory question in either ledger or record requires `needs_context`.
A declaration of `ready_for_transport` in its presence yields exactly
`mandatory_unresolved_question_incompatible_with_ready_for_transport`.
Other unfinished checklist/coverage items also block ready. Unresolved mathematical
`open_obligations` alone do not block editorial readiness.

Every report has `semantic_equivalence_verified`, `source_extraction_complete`,
`kernel_replayed`, `publication_authorized` set to **false**, including invalid
inputs. The script does not change the input state or emit a Transport plan.
Syntax/quote checks do not prove source truth, type classification, atom roles,
absence of omitted conditions outside the ledger, or unit interpretation.

See the [orbit fixture and invocation](../../examples/claim-extraction-orbit/README.ru.md)
and [regression tests](../../tests/test_claim_extraction.py).
