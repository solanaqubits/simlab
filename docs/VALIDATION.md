# Migration validation (δ1)

This public export is an independently created source history. It includes the 20
registered inherited formal modules, their 15 native support/entry-point sources,
and selected synthetic regressions. The allowlist is in EXPORT.json. Shared files
are byte-identical to the reviewed private snapshot at export time; private logs,
Russian cards, archival inputs and history are deliberately absent.

New checks in this public tree:

- `sh scripts/build-native.sh`: exit 0, strict native build with retained dependency cache.
- `LEAN_VERIFIER_LIVE_TESTS=1 python3 -B -m unittest discover -s tests -v`:
  13 tests passed, 0 failures, 0 skips (10 kernel-regression invocations and 3 runtime smoke tests).
- The runtime smoke tests start binaries with an unrelated current directory.
- The export scans explicit allowed text files for private paths, credential patterns
  and Cyrillic content; this is a finite review, not proof of universal sanitization.

The private source relocation exposed missing legacy Lean header comments. Only
header/doc comments were repaired in the new trees; checks were not disabled.
Neither historical numerical counts nor the larger Leanbook audit are recounted as
fresh public evidence. A full standalone β baseline has not yet been accepted.
No release tag is created. See BOUNDARIES.md: the third obligation remains OPEN.
