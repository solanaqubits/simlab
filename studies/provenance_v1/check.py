"""Offline package consistency; not infrastructure acceptance."""
from pathlib import Path
import hashlib,json,re

def validate(m,root):
    assert m['schema']=='provenance-audit-package-v1'
    assert re.fullmatch('[0-9a-f]{40}',m['leanbook_commit'])
    assert m['leanbook_url']=='https://github.com/solanaqubits/leanbook/tree/'+m['leanbook_commit']
    for k in ['source_manifest_sha256','public_validation_sha256','setup_sha256']:
        assert re.fullmatch('[0-9a-f]{64}',m[k])
    assert m['setup_sha256']==hashlib.sha256((root/'test_setup.en.md').read_bytes()).hexdigest()
    assert m['native_target_acceptance']=='NOT_RUN'
    assert m['external_witness']=='NOT_CONNECTED' and m['independent_audit']=='PENDING'
    assert m['authorization']=='blocked' and m['third_obligation']=='OPEN'
    assert m['public_full_beta'] is False
    assert type(m['public_scoped_tests']) is int and m['public_scoped_tests']>0
    assert type(m['source_export_count']) is int and m['source_export_count']>0
    return dict(package_ok=True, independent_audit='PENDING', authorization='blocked')
if __name__=='__main__':
    r=Path(__file__).resolve().parent
    print(json.dumps(validate(json.loads((r/'manifest.json').read_text()),r),sort_keys=True))
