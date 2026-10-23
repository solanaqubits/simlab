# Provenance v1 audit preparation

Reviewed source and test setup; no new simulation, physical result or industrial acceptance.
The executable/reference sources live in [Leanbook at 2939f0c](https://github.com/solanaqubits/leanbook/tree/2939f0c672e181be11c6ccbe8001f517452b0c8c).
[Manifest](manifest.json) pins that public commit and two source/validation file hashes.
[Test setup and auditor checklist](test_setup.en.md) specify the three-role topology,
required credentials, fault matrix, evidence and open assumptions.

The source export separates pure formal checks from opt-in target-qualified native tests.
Generic hosted CI does not qualify the example runtime profile or external Witness.
This repository adds no copied private evidence/history, credentials or grant material.
Independent audit PENDING, external Witness NOT_CONNECTED, authorization blocked,
C0–C6 indeterminate, Third Obligation OPEN. Existing published studies are preserved.

```sh
python3 studies/provenance_v1/check.py
python3 -m unittest discover -s studies/provenance_v1 -p 'test_*.py' -v
```

Checks below validate packaging consistency and reject false acceptance flags; they do
not authenticate the remote commit or prove the scientific/operational claims.
