# Claim Transport 0.1

This optional, offline layer compares selected structured contracts from a pinned
`geek-work-manuscript-claim-bundle-1`. It neither changes `claim-map-1` nor publishes
claims or writes the knowledge graph. Source statements and evidence remain
reported content. A `formal_reported` label is not a new kernel check.

## Wire and authority

[wire.schema.json](wire.schema.json) describes the shape of the plan, candidate and
report. The Python validator is the executable authority for additional checks:
unique IDs, exact hashes/quotes, pair coverage, source replay and cumulative limits.
JSON Schema alone cannot establish those properties. The executable uses only
Python's standard library and the existing local claim-map/JSON helpers.

The coordinator supplies `--source-sha256` (the source bundle's **manifest bytes**)
and `--plan-sha256` independently of the candidate. The candidate merely repeats
these anchors. Source-file hashes in the manifest and plan cannot be self-selected
by the candidate. This trusts the coordinator's choice; it does not authenticate
the coordinator, repository commits, or a remote source.

A plan has `schema: geek-work-claim-transport-plan-1`, `mode: exact_contract`,
`source_bundle_sha256`, and 1–16 `pairs`. Each pair declares unique pair/source/
candidate IDs, positive source/candidate revisions, and coordinator annotations:
`premise_atoms`, `conclusion_atoms`, `domain_atoms`, `quantifier_atoms`,
`negation_atoms`, `quantities`. Revisions are declared metadata, not verified Git
history. All declared source assumptions must be represented exactly once by
text multiplicity. Conclusion annotations quote the source statement; other
annotated roles quote its statement, assumptions or scope. Quantities quote an
exact literal. Role assignment and extraction completeness remain unverified.

Atoms contain `id`, `text`, `sha256` of UTF-8 text. A single ID has one immutable
text/hash across all selected source and candidate cards. Rebinding is invalid,
even with a newly calculated hash. New candidate IDs are allowed but require
review. Each quantity has `id`, `symbol`, `exact_literal` as a string, and an explicit
`unit` (use `dimensionless` when appropriate). No float or arithmetic normalization
occurs: `"1/4"` and `"0.25"` differ.

The adapter independently replays the pinned claim-map snapshot, preserving
source paths, file hashes, statement codepoint ranges and material repository/
commit metadata where supplied by claim-map. A manuscript document has no commit
field in claim-map-1; none is invented. Each evidence ID is SHA-256 of the canonical
JSON (`geek_work_manuscript.encoded`) of its `{binding, material}` record, retaining
quote, declaration and material origin. Scope, reported state, non-claims and open
obligations come directly from the source map, not the annotations.

The candidate has `schema: geek-work-claim-transport-candidate-1`, the two anchors,
and exactly the planned cards. Each card has its candidate ID/revision, copied
source binding, contract, `proof_reference` (null or text), and a statement:
`text`, UTF-8 `sha256`, `start`, `end`, `quote`. Offsets count Unicode codepoints,
end-exclusive, preserving CRLF; they are not UTF-8 byte offsets.

## Exact mode and reports

Comparison ignores ordering of unique atoms/quantities and evidence/non-claim/
obligation lists. All remaining strings and selected statement quotes match
exactly. No semantic implication or equivalent-number recognition is attempted.

- `contract_preserved`: selected structural fields and quote match.
- `review_required`: valid bound inputs differ, or a `proof_reference` is supplied.
  Difference classes identify fields, not inferred natural-language meanings.
  A new ID for `≤` → `<` requires review; changing text under the old ID is invalid.
  A named Lean theorem cannot justify or automatically approve a difference.
- `invalid_input`: malformed schema, wrong anchors/hashes/quotes, atom rebinding,
  duplicate/missing pairs, source mutation/replay failure, or exceeded limits.
  `selected_pairs: 0` means no completed comparison report, not partial approval.

Every outcome sets `semantic_equivalence_verified`, `source_extraction_complete`,
`kernel_replayed`, and `publication_authorized` to **false**. Text outside a selected
quote is preserved in the report for inspection, but not certified. Even exact
fields can encode an incomplete or false source claim.

Limits: plan plus candidate together ≤2 MiB; ≤16 pairs, ≤32 entries per atom role,
quantity/evidence/obligation list, ≤4000 codepoints per text field, nesting ≤32.
Duplicate JSON keys, floats, NaN/Infinity, booleans as integer offsets/revisions,
unknown fields, symlink leaves and nonregular inputs are rejected. Source bundles
retain their inherited 16 MiB total and 1 MiB source-file bounds. The adapter reads
one directory-FD snapshot and replays it; it does not verify then reread mutable
files. Snapshot integrity is relative to the supplied hash, not a live-directory
immutability promise.

## Commands

Run from the private SimLab root. The plan must first be reviewed and pinned by
the coordinator. These commands do not contact NotebookLM, GitHub or Lean.

```sh
python3 geek_work/tools/geek_work_claim_transport.py template \
  --bundle SOURCE_BUNDLE --source-sha256 SOURCE_MANIFEST_SHA256 \
  --plan plan.json --plan-sha256 PLAN_BYTES_SHA256 --output candidate.json

python3 geek_work/tools/geek_work_claim_transport.py check \
  --bundle SOURCE_BUNDLE --source-sha256 SOURCE_MANIFEST_SHA256 \
  --plan plan.json --plan-sha256 PLAN_BYTES_SHA256 \
  --candidate candidate.json --output report.json
```

Output is exclusively created; existing files are never overwritten. Exit codes
for `check`: 0 preserved, 1 review, 2 invalid. An unwritable/existing output causes
an I/O failure rather than a fabricated report. Successful `template` returns 0;
it generates an editable candidate, not a verdict. All inputs are data; no source
instructions, proof references or candidate programs are executed.

## Lean boundary

The companion `Verification/ClaimTransportContract.lean` models finite contracts,
exact decidable equality, independently supplied anchors, proof-reference refusal
and conservative report flags. Its decoder-validity input is an explicit external
premise. Under a fixed `Atom → Prop` interpretation it proves transport from equal
contracts, and the more general sufficient inclusions `A ⊆ A'`, `B' ⊆ B`.

No theorem establishes correspondence of Python/JSON to this model, SHA security,
source authentication, natural-language interpretation, completeness or scientific
truth. The general inclusion theorem establishes consequence, not equivalence or
non-vacuity. The executable v0.1 does **not** accept inclusion-only changes.
