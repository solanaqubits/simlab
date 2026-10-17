"""Strict full audit of the explicitly registered standalone Lean source scope."""
from pathlib import Path
import subprocess,json,tempfile,sys
root=Path(__file__).resolve().parents[1]
modules=sorted('Verification.'+p.stem for p in (root/'Verification').glob('*.lean'))
subprocess.run(['lake','build','--wfail',*modules],cwd=root,check=True)
text=(root/'tools/audit_template.lean').read_text().replace('-- IMPORTS','\n'.join('import '+m for m in modules))
(root/'.local/tmp').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=root/'.local/tmp') as tmp:
 p=Path(tmp)/'Audit.lean';p.write_text(text)
 result=subprocess.run(['lake','env','lean','-DwarningAsError=true',str(p)],cwd=root,capture_output=True,text=True)
 print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr);sys.exit(result.returncode)
