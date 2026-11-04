# Module inventory

Modules without a command-line entry point are libraries used by the other tools.

Optional runtime and provider commands remain opt-in. Read RELEASE.md first.

| Module | Purpose |
| --- | --- |
| `alcc.py` | ALCC-JSON-1 bounded prototype. Standard library only; no admission integration. |
| `chat_intake.py` | Offline, reversible staging before Digital Brain knowledge-card curation. |
| `geek_work.py` | Local coordination and byte-preserving intake archive utilities; no source execution. |
| `geek_work_addressed.py` | Explicit v3 adapter with a source-bound string-field index; no citation repair. |
| `geek_work_alcc_byte_preflight.py` | Fixed ALCC Python byte preflight; not Lean verification or full CLI throughput. |
| `geek_work_alcc_replay.py` | Portable, offline replay of the bounded typed ALCC pilot. Does not run archived code. |
| `geek_work_alcc_tasks.py` | Frozen complete typed ALCC tasks and independent rational oracle (not byte bridge). |
| `geek_work_alcc_timing_replay.py` | Portable native ALCC timing replay; never executes a recorded command or binary. |
| `geek_work_alphaxiv.py` | Bounded alphaXiv discovery intake, including failed responses and offline replay. |
| `geek_work_alphaxiv_content.py` | Offline saved alphaXiv content bindings, with explicit reported representation. |
| `geek_work_annotations.py` | Check declared review metadata and exact citations; prepare a sealed corpus, not verified knowledge. |
| `geek_work_batch_hunks.py` | Per-file hunk choices over an anchored manuscript batch; staged output only. |
| `geek_work_card_view.py` | Portable read-only cards over existing memory retrieval; no evidence promotion. |
| `geek_work_claim_audit.py` | Offline audit matrix over native manuscript claim bundles; judgments remain reported. |
| `geek_work_claude.py` | Bounded, text-only Claude CLI adapter for Geek Work. Estimates never become billed cost. |
| `geek_work_compile_verify.py` | Verify an anchored compile archive without Docker, compilation or PDF rendering. |
| `geek_work_context_coverage.py` | Measure annotated-span presence in native document selections, not answer quality. |
| `geek_work_context_profile.py` | Offline payload sizing; no model, tokenizer, billing or quality estimate. |
| `geek_work_council.py` | Compare bounded offline reviews; agreement is never a correctness verdict. |
| `geek_work_diagram.py` | Render a bounded, source-bound diagram; citations certify bytes, not meaning. |
| `geek_work_document_index.py` | Offline literal Markdown outlines and exact bounded context selections. |
| `geek_work_document_review.py` | Compose pinned manuscript proposals, guard reviews and declared diagram links. |
| `geek_work_draft_review.py` | Offline intake of provisional document reviews; never creates gold labels. |
| `geek_work_editorial_guards.py` | Route changed manuscript blocks to explicit excerpt guards; never accept semantics. |
| `geek_work_eval.py` | Offline, source-pinned paired evaluation. Never launches models or source code. |
| `geek_work_evm_audit.py` | Export a source-only EVM audit packet from pinned Git blobs; verify its seal. |
| `geek_work_evm_decisions.py` | Record evidence-bound dispositions of EVM findings without certifying them. |
| `geek_work_exact_pilot.py` | Fixed sum-of-squares control pilot; exact finite checks, not a universal proof. |
| `geek_work_exact_runner.py` | Supervise the trusted fixed arithmetic pilot; no arbitrary command execution CLI. |
| `geek_work_execution_series.py` | Selected fixed-profile executions: failure-inclusive accounting, not global completeness. |
| `geek_work_experiment.py` | Freeze bounded experiment plans and reproduce exact numeric claim maps offline. |
| `geek_work_experiment_tree.py` | Build an offline read-only experiment tree from pinned plans and reported ledgers. |
| `geek_work_explainer.py` | Build a three-level, source-bound explanation using native offline HTML disclosure controls. |
| `geek_work_fields.py` | Bounded index of exact string fields. Content stays in the original context. |
| `geek_work_file_operations.py` | Review explicit file lifecycle operations; stage bytes and removal intents only. |
| `geek_work_finalize.py` | Linux cooperative-writer transaction protocol. The registry rename is the commit point. |
| `geek_work_gnark_statement.py` | Prepare expected public inputs for the bounded gnark pilot; NOT a proof verifier. |
| `geek_work_hexagon.py` | Bounded read-only Hexagon metadata snapshots. No submission, crawling or graph promotion. |
| `geek_work_latex_compile.py` | Opt-in two-pass pdfLaTeX adapter, isolated from the Typst archive format. |
| `geek_work_latex_verify.py` | Check a pinned LaTeX compile archive offline; never replay its compiler. |
| `geek_work_ledger.py` | Validate reported task telemetry; never infer unavailable usage or currency rates. |
| `geek_work_local_retrieval.py` | Deterministic literal-term section retrieval with native bounded context output. |
| `geek_work_manuscript.py` | Review one manuscript-file proposal without modifying the live document. |
| `geek_work_manuscript_batch.py` | Stage a single decision for an explicit set of existing manuscript files. |
| `geek_work_manuscript_claims.py` | Bind selected manuscript excerpts to pinned evidence; no semantic adjudication. |
| `geek_work_manuscript_compile.py` | Opt-in offline Typst compilation of a pinned selected snapshot in local Docker. |
| `geek_work_manuscript_hunks.py` | Explicit per-hunk manuscript decisions with byte-preserving staged results. |
| `geek_work_manuscript_preflight.py` | Bounded, offline literal-LaTeX dependency lint over an explicit file selection. |
| `geek_work_manuscript_release.py` | Prepare explicitly allowlisted manuscript source packages; never publish them. |
| `geek_work_manuscript_status.py` | Check an explicitly pinned manuscript chain and report its next unresolved step. |
| `geek_work_memory.py` | Read-only versioned memory and explicit review eligibility. Never promotes truth. |
| `geek_work_memory_pilot.py` | Bounded single-call memory off/on pilot. Gold stays outside the runner plan. |
| `geek_work_model_proposer.py` | One bounded text-only Claude call, then isolated relay and frozen tool evaluation. |
| `geek_work_model_review.py` | Bounded separate-session model annotation. Never promotes labels to gold. |
| `geek_work_nonce_recovery.py` | Consistent nonce-registry snapshots and no-overwrite recovery against a pinned checkpoint. |
| `geek_work_numeric_history.py` | Preserve numeric revisions and bind selected document numbers; no scientific promotion. |
| `geek_work_observations.py` | Archive bounded observations and read exact anchored ranges offline; no execution. |
| `geek_work_ocr_candidate.py` | Capture untrusted OCR candidates bound to an existing verified page packet. |
| `geek_work_operation_apply.py` | Prepare, apply and recover bounded manuscript worktree edits; leave Git index/refs unchanged. |
| `geek_work_operation_git.py` | Export a preflight-bound Git patch using disposable objects and index only. |
| `geek_work_operation_preflight.py` | Recheck a file-operation baseline and lint its selected final LaTeX projection. |
| `geek_work_pdf_binding.py` | Explicit verified LaTeX/Typst dispatch for PDF page consumers; no compiler execution. |
| `geek_work_pdf_container.py` | Pinned no-network Docker PDF page packets with recorded cleanup outcomes. |
| `geek_work_pdf_diagnostics.py` | Read-only diagnostics for verified container page/failure archives. |
| `geek_work_pdf_pages.py` | Render a source-bound PDF into a private, bounded page-review packet. |
| `geek_work_pdf_review.py` | Record explicit page-by-page visual judgments against pinned PDF/PNG bytes. |
| `geek_work_pdf_runtime_context.py` | Prepare/verify an offline pinned Poppler container build context; no execution. |
| `geek_work_polynomial_candidate.py` | Small deterministic interpolation generator; receives training samples only. |
| `geek_work_proof_contract.py` | Bind a proof request to local artifacts. Never verifies or generates ZK proofs. |
| `geek_work_proof_nonce.py` | Verify a pinned local gnark proof, then atomically consume its scoped nonce. |
| `geek_work_proposer.py` | Isolated single-file proposer and host-controlled handoff to frozen evaluation. |
| `geek_work_protected.py` | Host-owned exact-JSON evaluator for bounded, single-file Python candidates. |
| `geek_work_quantum_package.py` | Offline bounded ZIP layout inventory. Never executes or certifies circuits. |
| `geek_work_query_fidelity.py` | Question-pair-only fidelity packets; exact evidence checks, not semantic approval. |
| `geek_work_ranges.py` | Canonical prepared-range views. Counts are provenance records, not semantic review. |
| `geek_work_raw_pdf_container.py` | Original-PDF Docker packets, with no manuscript compile binding or native fallback. |
| `geek_work_raw_pdf_pages.py` | Bound a small page selection to original PDF bytes, without a compile claim. |
| `geek_work_raw_pdf_selection.py` | Bounded original-page selection using a separately pinned Docker runtime. |
| `geek_work_references.py` | Offline literal HTTP(S) reference queue; source text is never fetched or executed. |
| `geek_work_release_compile.py` | Bind an archived pdfLaTeX result to exact allowlisted manuscript package bytes. |
| `geek_work_retrieval_assessment.py` | Assess frozen literal retrieval against provisional annotations, retaining misses. |
| `geek_work_retrieval_review.py` | Source-only annotation packets and offline response intake; no gold promotion. |
| `geek_work_science.py` | Select pinned scientific capabilities for a declared experiment, without executing them. |
| `geek_work_science_context.py` | Measure a verified science selection and refuse excess bytes; no model or token estimate. |
| `geek_work_session_ledger.py` | Host-recorded reservations and responses; not a provider attestation or cost meter. |
| `geek_work_session_review.py` | Prepare and check session annotations offline; never attest model identity or promote gold. |
| `geek_work_structured.py` | Versioned structured support review. Shape/citations are checked, never semantic truth. |
| `geek_work_study_executions.py` | Bind selected execution series to exact study-node plans without combining ledger costs. |
| `geek_work_transcript.py` | Archive a bounded WebVTT subset and source-bound notes offline; no ASR or media access. |
| `geek_work_transcript_json.py` | Convert bounded saved transcript JSON to exact-ms WebVTT offline; retain raw input. |
| `geek_work_transcript_materials.py` | Bind transcript cues to supplied material bytes; no media decoding or alignment claim. |
| `geek_work_typst_bibliography.py` | Classify literal reference candidates against selected reachable BibTeX keys. |
| `geek_work_typst_gate.py` | Gate Typst compilation on a clean literal preflight and bind its exact snapshot. |
| `geek_work_typst_preflight.py` | Bounded literal Typst dependency lint; no Typst evaluation or package resolution. |
| `geek_work_typst_references.py` | Bounded literal Typst label/reference inventory over an anchored preflight. |
| `geek_work_vault.py` | Deterministic, local Markdown view of selected knowledge; never a write-back authority. |
| `geek_work_vault_recovery.py` | Private local recovery snapshot; preserves the full graph and selected source bytes. |
| `knowledge.py` | Private knowledge cards, read-only pinned export, and reviewable dossiers. |
