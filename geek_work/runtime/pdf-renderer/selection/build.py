#!/usr/bin/env python3
"""Build from the exact already-installed base; never pull or install packages."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import geek_work_pdf_container as c


def main():
    runtime=c.selection_profile();folder=Path(__file__).resolve().parent
    c.m.require(c.m.sha((folder/'worker.py').read_bytes())==runtime['worker_sha256'],'worker source changed')
    base=runtime['base_image_id']
    observed=subprocess.check_output(['docker','image','inspect',base,'--format','{{.Id}}'],text=True,timeout=15).strip()
    c.m.require(observed==base,'local base image missing or changed')
    # Legacy Docker builder accepts a full local image ID as FROM. BuildKit
    # interprets sha256:... as a registry name; do not enable it for this recipe.
    subprocess.run(['docker','build','--network=none','--pull=false','--build-arg','BASE='+base,
                    '-t','geek-work-poppler-selection:1',str(folder)],check=True,timeout=120,
                   env={**os.environ,'DOCKER_BUILDKIT':'0'})
    actual=subprocess.check_output(['docker','image','inspect','geek-work-poppler-selection:1','--format','{{.Id}}'],text=True,timeout=15).strip()
    print(c.m.encoded(dict(image_id=actual,reviewed_image_id=runtime['image_id'],matches_reviewed_image=actual==runtime['image_id'],independent_build_attestation=False)).decode(),end='')
    # A different local build must be reviewed; never rewrite the runtime pin.
    if actual!=runtime['image_id']:raise SystemExit(2)


if __name__=='__main__':main()
