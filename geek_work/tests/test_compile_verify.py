import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_compile_verify as v


class ArchiveVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.bundle=self.root/'bundle';self.bundle.mkdir();(self.bundle/'sources').mkdir()
        name='geek-work-typeset-'+'a'*32;old='/unavailable/old/project/sources'
        self.input=b'= Synthetic source\n';self.pdf=b'%PDF-synthetic bytes; not a rendered PDF'
        req=dict(schema='geek-work-manuscript-compile-request-1',entry='main.typ',files=[dict(path='main.typ',sha256=v.m.sha(self.input))])
        command=v.c.command_for_path(name,old,'main.typ')
        host=dict(Memory=536870912,MemorySwap=536870912,NanoCpus=2000000000,PidsLimit=64,NetworkMode='none',ReadonlyRootfs=True,Privileged=False,CapDrop=['ALL'],CapAdd=None,SecurityOpt=['no-new-privileges'],Tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=64m,mode=1777'},LogConfig={'Type':'none','Config':{}},PidMode='',IpcMode='private',UTSMode='',PublishAllPorts=False,Ulimits=[dict(Name='core',Soft=0,Hard=0),dict(Name='fsize',Soft=16777216,Hard=16777216)],Mounts=[dict(Type='bind',Source=old,Target='/src',ReadOnly=True)])
        container=dict(Name='/'+name,Image=v.c.IMAGE_ID,
            State=dict(Running=False,OOMKilled=False,Paused=False,Restarting=False,Dead=False,Status='exited',Error='',ExitCode=0),
            Config=dict(Image=v.c.IMAGE,Entrypoint=['/bin/typst'],Cmd=command[command.index(v.c.IMAGE)+1:],User='1000:1000',WorkingDir='/src',Tty=False,Volumes=None,Env=['HOME=/tmp','TZ=UTC','SOURCE_DATE_EPOCH=0','PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin']),
            HostConfig=host,Mounts=[dict(Type='bind',Source=old,Destination='/src',Propagation='rprivate',RW=False)])
        self.data={'sources/main.typ':self.input,'request.json':v.m.encoded(req),'document.pdf':self.pdf,'compiler.stdout':self.pdf,'compiler.log':b'',
                   'image.json':v.m.encoded([dict(Id=v.c.IMAGE_ID,Os='linux',Architecture='amd64')]),'command.json':v.m.encoded(command),'container.json':v.m.encoded(container)}
        receipt=dict(schema='geek-work-manuscript-compile-receipt-1',request_sha256=v.m.sha(self.data['request.json']),status='compiled',container_name=name,image=v.c.IMAGE,image_id=v.c.IMAGE_ID,exit_code=0,client_exit_code=0,oom_killed=False,timed_out=False,container_removed=True,wall_time_ms=10,snapshot_unchanged_at_final_check=True,scientific_verification=False,semantic_claim_check=False,pdf_visual_review=False,limits='Synthetic evidence only',compile_timeout_seconds=30,capture_limit_bytes=v.c.MAX_PDF,pdf_sha256=v.m.sha(self.pdf))
        self.data['receipt.json']=v.m.encoded(receipt);self.seal()

    def seal(self):
        for name,raw in self.data.items():
            p=self.bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        manifest=v.m.encoded(dict(schema='geek-work-manuscript-compile-manifest-1',files={n:v.m.sha(b) for n,b in self.data.items()}))
        (self.bundle/'manifest.json').write_bytes(manifest);self.anchor=v.m.sha(manifest)

    def change(self,name,edit):
        value=json.loads(self.data[name]);edit(value);self.data[name]=v.m.encoded(value);self.seal()

    def test_compiled_consistency_without_execution_or_old_root(self):
        with patch('subprocess.run',side_effect=AssertionError('no process execution')),patch.object(Path,'resolve',side_effect=AssertionError('no path resolution')):
            result=v.verify(self.bundle,self.anchor)
        self.assertEqual(result['status'],'compiled_bundle_consistent')
        for key in ('compilation_replayed','live_cleanup_checked','artifact_authenticity_verified','pdf_conformance_verified','scientific_verification'):self.assertFalse(result[key])

    def test_relocation_and_cli(self):
        moved=self.root/'moved';shutil.copytree(self.bundle,moved);shutil.rmtree(self.bundle)
        r=json.loads(subprocess.check_output([sys.executable,v.__file__,'--bundle',str(moved),'--sha256',self.anchor],env={**os.environ,'PATH':''}))
        self.assertEqual(r['status'],'compiled_bundle_consistent')

    def test_anchor_and_unsealed_pdf_tamper(self):
        with self.assertRaisesRegex(ValueError,'anchor'):v.verify(self.bundle,'0'*64)
        (self.bundle/'document.pdf').write_bytes(b'%PDF-altered')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):v.verify(self.bundle,self.anchor)

    def test_resealed_pdf_cannot_disagree_with_capture(self):
        self.data['document.pdf']=b'%PDF-other';self.seal()
        with self.assertRaisesRegex(ValueError,'PDF/capture'):v.verify(self.bundle,self.anchor)

    def test_source_drift_and_wrong_source_selection(self):
        self.data['sources/main.typ']+=b'drift';self.seal()
        with self.assertRaisesRegex(ValueError,'source/request'):v.verify(self.bundle,self.anchor)
        self.data['sources/main.typ']=self.input;self.data['sources/unselected.txt']=b'unselected';self.seal()
        with self.assertRaisesRegex(ValueError,'selected source set'):v.verify(self.bundle,self.anchor)

    def test_resealed_network_and_extra_mount_and_environment(self):
        original=self.data['container.json']
        edits=[lambda x:x['HostConfig'].update(NetworkMode='host'),lambda x:x['Mounts'].append(dict(Type='bind',Source='/secret',Destination='/secret',RW=False)),lambda x:x['Config']['Env'].append('LD_PRELOAD=/injected')]
        for edit in edits:
            self.data['container.json']=original;self.change('container.json',edit)
            with self.subTest(edit=edit),self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)

    def test_resealed_privilege_and_limits(self):
        original=self.data['container.json']
        for key,value in [('Memory',0),('PidsLimit',True),('Privileged',True),('CapAdd',['SYS_ADMIN']),('SecurityOpt',[])]:
            self.data['container.json']=original;self.change('container.json',lambda x:x['HostConfig'].update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)

    def test_command_change_and_fake_image(self):
        original=self.data['command.json'];self.change('command.json',lambda x:x.append('--new-flag'))
        with self.assertRaisesRegex(ValueError,'command/profile'):v.verify(self.bundle,self.anchor)
        self.data['command.json']=original;self.change('image.json',lambda x:x[0].update(Id='sha256:'+'0'*64))
        with self.assertRaisesRegex(ValueError,'image identity'):v.verify(self.bundle,self.anchor)

    def test_receipt_cleanup_failure_exit_and_promotions(self):
        original=self.data['receipt.json']
        for key,value in [('container_removed',False),('exit_code',True),('client_exit_code',1),('timed_out',True),('pdf_visual_review',True),('scientific_verification',True),('unrecognized','value')]:
            self.data['receipt.json']=original;self.change('receipt.json',lambda x:x.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)

    def test_failed_archive_is_not_compiled_or_cli_success(self):
        self.change('receipt.json',lambda x:x.update(status='compiler_failed',exit_code=1))
        r=v.verify(self.bundle,self.anchor);self.assertEqual(r['status'],'failure_archive_intact');self.assertFalse(r['compiled_profile_checked'])
        p=subprocess.run([sys.executable,v.__file__,'--bundle',str(self.bundle),'--sha256',self.anchor],stdout=subprocess.PIPE)
        self.assertEqual(p.returncode,2)

    def test_partial_and_extra_directory(self):
        (self.bundle/'receipt.json').unlink()
        with self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)
        self.seal();(self.bundle/'extra').mkdir()
        with self.assertRaisesRegex(ValueError,'unexpected archive directory'):v.verify(self.bundle,self.anchor)

    def test_symlink_file_directory_and_fifo(self):
        (self.bundle/'compiler.log').unlink();(self.bundle/'compiler.log').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)
        (self.bundle/'compiler.log').unlink();os.mkfifo(self.bundle/'compiler.log')
        with self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)
        (self.bundle/'compiler.log').unlink();self.seal();shutil.rmtree(self.bundle/'sources');(self.bundle/'sources').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):v.verify(self.bundle,self.anchor)

    def test_manifest_traversal_and_duplicate_json_keys(self):
        manifest=json.loads((self.bundle/'manifest.json').read_bytes());manifest['files']['sources/../escape']='0'*64
        raw=v.m.encoded(manifest);(self.bundle/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):v.verify(self.bundle,v.m.sha(raw))
        raw=b'{"schema":"x","schema":"x","files":{}}';(self.bundle/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):v.verify(self.bundle,v.m.sha(raw))

    def test_archive_byte_budget(self):
        with patch.object(v,'MAX_BUNDLE',1),self.assertRaisesRegex(ValueError,'bundle byte limit'):v.verify(self.bundle,self.anchor)
