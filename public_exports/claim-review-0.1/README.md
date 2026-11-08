# Reviewed public integration: Claim Review and Cairo source package

Claim Review 0.1 is exported from frozen local source `a5df4ad3` through the
explicit [allowlist](export.json). [Review](review.json) records original and
adapted bytes; [local checks](checks.json) record checks of the public layout.
Historical release 1.0.0 and tags are not replaced. The manifest version is the
existing export format version; the extension is published as ordinary source.

Run `python3 -B geek_work/check.py`, then the schema, harness, server and browser
commands in `.github/workflows/claim-review.yml`. Browser tests need Chrome,
`jsonschema==4.10.3` and `websocket-client==1.7.0`; the editor runtime has no CDN
or frontend library dependency. See the [coordinator guide](../../geek_work/contracts/claim-review-api/COORDINATOR.ru.md).

The public tree excludes private history, chats, raw operational logs, graph
content and session secrets. Frozen example JSON is unchanged; code paths and
links are adapted for `geek_work/`. An orbit harness self-test now regenerates
the adapter receipt instead of reading a private historical log.

[Stage 15](../../studies/mldsa44_stage15/README.md) separately preserves the exact
accepted source patch, inherited attribution and historical results. Final
Cairo model research is frozen at `7993221f` for publication in Leanbook.
The model's finite-trace completeness does not prove real VM correspondence,
compiler correctness, full ML-DSA verification or quantum security.

All four Claim assurance flags remain false. Permission to publish this reviewed
code comes from the repository owner, not from a validator output.
