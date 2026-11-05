"""Fixed entrypoints for the isolated Poppler runtime; no host mounts required."""
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile

MAX_PDF=16*1024*1024
MAX_IMAGE=8*1024*1024


def limits():
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_IMAGE,MAX_IMAGE))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))


def run(argv,cwd=None,max_stdout=65536):
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        result=subprocess.run(argv,cwd=cwd,stdout=out,stderr=err,timeout=15,preexec_fn=limits,
                              env={'PATH':'/opt/poppler/bin:/usr/bin:/bin','HOME':'/tmp','LC_ALL':'C','FONTCONFIG_FILE':'/opt/poppler/etc/fonts/fonts.conf'})
        out.seek(0);stdout=out.read(max_stdout+1);err.seek(0);stderr=err.read(65537)
    if len(stdout)>max_stdout or len(stderr)>65536:raise ValueError('capture limit')
    if result.returncode:
        sys.stdout.buffer.write(stdout);sys.stderr.buffer.write(stderr)
        raise ValueError('Poppler process failed')
    return stdout,stderr


def main():
    if sys.argv[1:]==['profile']:
        tools={}
        for name in ('pdfinfo','pdftoppm'):
            path=Path('/opt/poppler/bin')/name;raw=path.read_bytes();out,err=run([str(path),'-v'])
            tools[name]=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),version=(out+err).decode('utf-8').strip())
        print(json.dumps(dict(schema='geek-work-poppler-container-observation-1',tools=tools,independent_build_attestation=False),sort_keys=True));return
    if sys.argv[1:]==['info']:page=None
    elif len(sys.argv)==3 and sys.argv[1]=='page' and sys.argv[2].isascii() and sys.argv[2].isdigit() and 1<=int(sys.argv[2])<=16:page=int(sys.argv[2])
    else:raise ValueError('expected profile, info, or page 1..16')
    raw=sys.stdin.buffer.read(MAX_PDF+1)
    if not 0<len(raw)<=MAX_PDF:raise ValueError('PDF input size limit')
    with tempfile.TemporaryDirectory(prefix='pdf-') as tmp:
        (Path(tmp)/'input.pdf').write_bytes(raw)
        argv=['/opt/poppler/bin/pdfinfo','input.pdf'] if page is None else ['/opt/poppler/bin/pdftoppm','-f',str(page),'-l',str(page),'-r','96','-png','-singlefile','input.pdf']
        out,err=run(argv,tmp,65536 if page is None else MAX_IMAGE)
    sys.stdout.buffer.write(out);sys.stderr.buffer.write(err)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError):
        sys.stderr.write('bounded Poppler worker failed\n');raise SystemExit(1)
