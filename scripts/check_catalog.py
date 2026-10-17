"""Check the registered standalone source scope and its import closure."""
from pathlib import Path
import json,re,hashlib
root=Path(__file__).resolve().parents[1]
c=json.loads((root/'docs/CATALOG.json').read_text())
actual={str(p.relative_to(root))for p in (root/'Verification').glob('*.lean')}
assert actual=={m['source']for m in c['modules']}
assert len({m['id']for m in c['modules']})==len(actual)
imports=set(re.findall(r'^import (Verification\.\w+)$',(root/'Verification.lean').read_text(),re.M))
assert imports=={p[:-5].replace('/','.')for p in actual}
for p in actual:
 for dep in re.findall(r'^import (Verification\.\w+)$',(root/p).read_text(),re.M):assert dep.replace('.','/')+'.lean'in actual
print(json.dumps({'modules':len(actual),'catalog_ok':True,'third_obligation':c['third_obligation']},sort_keys=True))
