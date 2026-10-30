# Geek Work: local knowledge tools

Python 3.12, standard library only. Tools for versioned JSON knowledge, selected
Markdown views, context-size profiles/replay/preflight, and read-only Hexagon
metadata intake, recovery snapshots, offline reference queues and review comparison. This package contains no private knowledge graph, chats, API
credentials, model adapter or autonomous agent core.

Run `python3 -m unittest discover -s tests -v` from this directory.
Use `python3 tools/knowledge.py --help` and other tool `--help` commands.

All tests use synthetic inputs. Structural checks, source hashes and byte budgets
do not establish scientific truth, token cost, or authorization to transmit data.
Markdown views do not write back to the graph. Hexagon metadata is not peer review.
Context preflight covers the retrieval envelope only; prompts, tools and output
need separate budgets. No installation service or background scheduler is included.

Source tooling is exported by explicit allowlist; test_memory uses a newly written
synthetic fixture rather than the private curated graph. No private Git history
is needed. Export manifest hashes describe files, not authorship or correctness.

The optional operator command `ci/self-hosted/run_once.py` runs one explicitly
reviewed queued GitHub workflow in a disposable container. See
`ci/self-hosted/README.ru.md`. Build with
`docker build -t geek-work-runner:20261029 ci/self-hosted`.
It creates no permanent service. Public PR workflows always use hosted runners;
manual self-hosted selection is restricted to the repository owner.

Run `python3 check.py` for the manifest and zero-skip synthetic suite.
See VAULT.ru.md and CONTEXT-PROFILE.ru.md for local data commands.

Offline review intake/council: see REVIEW.ru.md. Snapshot recovery and reference
queues: RECOVERY.ru.md and REFERENCES.ru.md. Real reviews and private corpora are
not distributed. Partial decisions remain unresolved, and agreement is not truth.
