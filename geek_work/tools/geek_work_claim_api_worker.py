#!/usr/bin/env python3
"""Resource guard for fixed trusted Python CLI entrypoints; not a hostile-code sandbox.

Only the server creates this private configuration. No HTTP-supplied entrypoint.
Writes by the supported Python file APIs are charged BEFORE being performed.
"""
import builtins
import errno
import io
import json
import os
from pathlib import Path
import resource
import runpy
import sys


class QuotaExceeded(BaseException):
    pass


def run(config):
    root=Path(config['root']).resolve()
    remaining=config['write_budget'];per_file=config['file_limit']
    original_open=builtins.open;original_io=io.open;original_fdopen=os.fdopen;original_write=os.write
    resource.setrlimit(resource.RLIMIT_FSIZE,(per_file,per_file))
    sizes={}

    def path_for(fd):
        p=Path(os.readlink('/proc/self/fd/'+str(fd))).resolve()
        if root not in p.parents:raise QuotaExceeded()
        return str(p)

    def charge(fd,size):
        nonlocal remaining
        if fd in (1,2):return  # parent drains and bounds both pipes
        name=path_for(fd)
        initial=sizes.get(name,os.fstat(fd).st_size)
        if size>remaining or initial+size>per_file:raise QuotaExceeded()
        remaining-=size;sizes[name]=initial+size

    class Writer:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):return self
        def __exit__(self,*args):return self.stream.__exit__(*args)
        def write(self,value):
            raw=value.encode(self.stream.encoding or 'utf-8') if isinstance(value,str) else value
            charge(self.stream.fileno(),len(raw))
            return self.stream.write(value)
        def writelines(self,values):
            for value in values:self.write(value)
        def truncate(self,*args):raise QuotaExceeded()
        def seek(self,*args):raise QuotaExceeded()
        def __getattr__(self,key):
            if key in ('buffer','raw'):raise QuotaExceeded()
            return getattr(self.stream,key)

    def guarded(factory):
        def opening(file,mode='r',*args,**kwargs):
            writing=any(c in mode for c in 'wax+')
            if writing and not isinstance(file,int):
                p=Path(file).resolve()
                if root not in p.parents:raise QuotaExceeded()
            stream=factory(file,mode,*args,**kwargs)
            if writing:
                path_for(stream.fileno())
                return stream if isinstance(stream,Writer) else Writer(stream)
            return stream
        return opening

    def write(fd,raw):
        charge(fd,len(raw));return original_write(fd,raw)

    builtins.open=guarded(original_open);io.open=guarded(original_io);os.fdopen=guarded(original_fdopen);os.write=write
    def forbidden(*args,**kwargs):raise QuotaExceeded()
    os.truncate=forbidden;os.ftruncate=forbidden
    # Trusted CLI dependencies use only the guarded APIs; deny unused bulk write APIs.
    for name in ('sendfile','copy_file_range'):
        if hasattr(os,name):setattr(os,name,forbidden)
    sys.argv=[config['script'],*config['args']]
    sys.path.insert(0,str(Path(config['script']).parent))
    runpy.run_path(config['script'],run_name='__main__')


def main():
    with open(sys.argv[1],'rb') as stream:config=json.load(stream)
    try:
        run(config)
    except QuotaExceeded:
        return 75
    except OSError as error:
        if error.errno==errno.EFBIG:return 75
        raise
    return 0


if __name__=='__main__':raise SystemExit(main())
