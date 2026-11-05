"""Fixed two-pass pdfLaTeX worker; output is a bounded JSON envelope, not shell code."""
import base64
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

MAX = 8 * 1024 * 1024
work = Path('/tmp/work')
work.mkdir()
env = {'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','LANG':'C.UTF-8',
       'SOURCE_DATE_EPOCH':'0','FORCE_SOURCE_DATE':'1','TZ':'UTC',
       'openin_any':'p','openout_any':'p','shell_escape':'f',
       'TEXMFOUTPUT':str(work),'TEXINPUTS':'/src//:',
       'TEXMFVAR':'/tmp/texmf-var','TEXMFCONFIG':'/tmp/texmf-config'}
command = ['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',
           '-file-line-error','-recorder','-jobname=document','-output-directory='+str(work),sys.argv[1]]
passes=[]
resource.setrlimit(resource.RLIMIT_FSIZE,(MAX,MAX))
for index in range(2):
    with (work/('pass-'+str(index)+'.txt')).open('xb') as log:
        result = subprocess.run(command,cwd='/src',env=env,stdout=log,stderr=subprocess.STDOUT)
    raw=(work/('pass-'+str(index)+'.txt')).read_bytes()
    passes.append(dict(exit_code=result.returncode,log_b64=base64.b64encode(raw).decode()))
    if result.returncode: break
files={}
for name in ('document.pdf','document.log','document.aux','document.fls'):
    p=work/name
    if p.is_file() and not p.is_symlink():
        raw=p.read_bytes()
        if len(raw)>MAX:raise ValueError('worker output limit')
        files[name]=base64.b64encode(raw).decode()
print(json.dumps(dict(schema='geek-work-latex-worker-1',passes=passes,files=files),sort_keys=True))
