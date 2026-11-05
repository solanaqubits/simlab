import base64
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
import geek_work_latex_verify as v


class LatexArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.bundle=self.root/'bundle';self.bundle.mkdir()
        self.runtime=v.c.profile();image=self.runtime['image_id']
        name='geek-work-latex-'+'a'*32;old='/unavailable/original/sources'
        source=b'\\documentclass{article}\\begin{document}Synthetic\\end{document}'
        req=dict(schema='geek-work-latex-compile-request-1',entry='main.tex',files=[dict(path='main.tex',sha256=v.m.sha(source))])
        self.artifacts={'document.pdf':b'%PDF-synthetic, not a rendered PDF','document.log':b'No diagnostics','document.aux':b'aux','document.fls':b'recorder','pass-1.log':b'pass one','pass-2.log':b'pass two'}
        b64=lambda b:base64.b64encode(b).decode()
        worker=dict(schema='geek-work-latex-worker-1',passes=[dict(exit_code=0,log_b64=b64(self.artifacts['pass-'+str(i)+'.log'])) for i in (1,2)],files={n:b64(self.artifacts[n]) for n in v.c.OUTPUTS})
        command=v.c.command_for_path(name,old,'main.tex',image)
        host=dict(Memory=536870912,MemorySwap=536870912,NanoCpus=2000000000,PidsLimit=64,NetworkMode='none',ReadonlyRootfs=True,Privileged=False,CapDrop=['ALL'],CapAdd=None,SecurityOpt=['no-new-privileges'],Tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=96m,mode=1777'},LogConfig={'Type':'none','Config':{}},PidMode='',IpcMode='private',UTSMode='',PublishAllPorts=False,Ulimits=[dict(Name='core',Soft=0,Hard=0),dict(Name='fsize',Soft=8388608,Hard=8388608)],Mounts=[dict(Type='bind',Source=old,Target='/src',ReadOnly=True)])
        args=['-B','/opt/worker.py','main.tex']
        container=dict(Name='/'+name,Image=image,Path='/usr/local/bin/python',Args=args,
            State=dict(Running=False,OOMKilled=False,Paused=False,Restarting=False,Dead=False,Status='exited',Error='',ExitCode=0),
            Config=dict(Image=image,Entrypoint=['/usr/local/bin/python'],Cmd=args,User='1000:1000',WorkingDir='/src',Tty=False,Volumes=None,Env=[k+'='+x for k,x in v.ENV.items()]),HostConfig=host,
            Mounts=[dict(Type='bind',Source=old,Destination='/src',Propagation='rprivate',RW=False)])
        self.data={'sources/main.tex':source,'request.json':v.m.encoded(req),'runtime.json':v.m.encoded(self.runtime),'worker.stdout':v.m.encoded(worker),'worker.stderr':b'',
                   'image.json':v.m.encoded([dict(Id=image,Os='linux',Architecture='amd64')]),'command.json':v.m.encoded(command),'container.json':v.m.encoded(container)}
        self.data.update({'artifacts/'+n:b for n,b in self.artifacts.items()})
        receipt=dict(schema='geek-work-latex-compile-receipt-1',request_sha256=v.m.sha(self.data['request.json']),status='compiled',image_id=image,container_name=name,container_removed=True,timed_out=False,oom_killed=False,worker_exit_code=0,client_exit_code=0,wall_time_ms=10,snapshot_unchanged_at_final_check=True,compile_timeout_seconds=30,shell_escape_enabled=False,scientific_verification=False,pdf_visual_review=False,limits='Synthetic archive only',engine_exit_codes=[0,0],diagnostics_review_required=False,pdf_sha256=v.m.sha(self.artifacts['document.pdf']))
        self.data['receipt.json']=v.m.encoded(receipt);self.seal()

    def seal(self):
        for name,raw in self.data.items():
            p=self.bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        manifest=v.m.encoded(dict(schema='geek-work-latex-compile-manifest-1',files={n:v.m.sha(b) for n,b in self.data.items()}))
        (self.bundle/'manifest.json').write_bytes(manifest);self.anchor=v.m.sha(manifest)

    def change(self,name,edit):
        x=json.loads(self.data[name]);edit(x);self.data[name]=v.m.encoded(x);self.seal()

    def check(self):return v.verify(self.bundle,self.anchor)

    def warning(self):
        log=b'LaTeX Warning: Reference missing undefined.'
        x=json.loads(self.data['worker.stdout']);x['passes'][1]['log_b64']=base64.b64encode(log).decode()
        self.data['worker.stdout']=v.m.encoded(x);self.data['artifacts/pass-2.log']=log
        self.change('receipt.json',lambda x:x.update(status='compiled_with_warnings',diagnostics_review_required=True))

    def test_success_without_process_or_historical_path_access(self):
        with patch('subprocess.run',side_effect=AssertionError('no execution')),patch.object(Path,'resolve',side_effect=AssertionError('no old path resolution')):
            r=self.check()
        self.assertEqual(r['status'],'compiled_bundle_consistent')
        self.assertTrue(r['compiled_profile_checked'])
        for k in ('compilation_replayed','live_cleanup_checked','artifact_authenticity_verified','pdf_conformance_verified','pdf_visual_review','scientific_verification'):self.assertFalse(r[k])

    def test_relocation_cli_without_path_tools(self):
        moved=self.root/'moved';shutil.copytree(self.bundle,moved);shutil.rmtree(self.bundle)
        r=json.loads(subprocess.check_output([sys.executable,v.__file__,'--bundle',str(moved),'--sha256',self.anchor],env={**os.environ,'PATH':''}))
        self.assertEqual(r['status'],'compiled_bundle_consistent')

    def test_warning_preserved_and_cli_non_success(self):
        self.warning();r=self.check();self.assertEqual(r['status'],'warning_bundle_consistent');self.assertTrue(r['compiled_profile_checked'])
        p=subprocess.run([sys.executable,v.__file__,'--bundle',str(self.bundle),'--sha256',self.anchor],capture_output=True)
        self.assertEqual(p.returncode,2)
        self.change('receipt.json',lambda x:x.update(status='compiled',diagnostics_review_required=False))
        with self.assertRaisesRegex(ValueError,'worker/receipt'):self.check()

    def test_failure_and_cleanup_failure_never_promote(self):
        original=self.data['receipt.json']
        for status in ('timeout','compiler_failed','worker_failed','cleanup_failed','snapshot_changed'):
            self.data['receipt.json']=original;self.change('receipt.json',lambda x:x.update(status=status))
            r=self.check();self.assertEqual(r['status'],'failure_archive_intact');self.assertFalse(r['compiled_profile_checked'])
        p=subprocess.run([sys.executable,v.__file__,'--bundle',str(self.bundle),'--sha256',self.anchor],capture_output=True)
        self.assertEqual(p.returncode,2)

    def test_anchor_and_unsealed_tampering(self):
        with self.assertRaisesRegex(ValueError,'anchor'):v.verify(self.bundle,'0'*64)
        (self.bundle/'artifacts/document.pdf').write_bytes(b'%PDF-changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.check()

    def test_resealed_artifact_binding_all_outputs(self):
        for name in self.artifacts:
            key='artifacts/'+name;original=self.data[key];self.data[key]+=b'changed';self.seal()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'artifact binding'):self.check()
            self.data[key]=original
        self.seal()

    def test_worker_passes_and_required_outputs(self):
        original=self.data['worker.stdout']
        edits=[lambda x:x['passes'].pop(),lambda x:x['passes'][0].update(exit_code=True),lambda x:x['passes'][1].update(exit_code=1),lambda x:x['files'].pop('document.aux'),lambda x:x['files'].update({'../escape':'eA=='}),lambda x:x['files'].update({'document.pdf':'%%%'}),lambda x:x.update(schema='wrong')]
        for edit in edits:
            self.data['worker.stdout']=original;self.change('worker.stdout',edit)
            with self.subTest(edit=edit),self.assertRaises(ValueError):self.check()

    def test_runtime_and_image_pins(self):
        for file,edit in [('runtime.json',lambda x:x.update(image_id='sha256:'+'0'*64)),('runtime.json',lambda x:x['files'].update({'worker.py':'0'*64})),('runtime.json',lambda x:x.update(packages_sha256='0'*64)),('image.json',lambda x:x[0].update(Architecture='arm64'))]:
            original=self.data[file];self.change(file,edit)
            with self.subTest(file=file),self.assertRaises(ValueError):self.check()
            self.data[file]=original

    def test_sources_selection_hash_and_text_bounds(self):
        original=self.data['sources/main.tex'];self.data['sources/main.tex']+=b'changed';self.seal()
        with self.assertRaisesRegex(ValueError,'source/request'):self.check()
        self.data['sources/main.tex']=b'\x00';self.seal()
        with self.assertRaises(ValueError):self.check()
        self.data['sources/main.tex']=original;self.data['sources/extra.txt']=b'not selected';self.seal()
        with self.assertRaisesRegex(ValueError,'selected source set'):self.check()

    def test_receipt_flags_codes_and_promotions(self):
        original=self.data['receipt.json']
        for key,value in [('container_removed',False),('client_exit_code',True),('worker_exit_code',1),('engine_exit_codes',[False,0]),('timed_out',True),('oom_killed',True),('compile_timeout_seconds',60),('shell_escape_enabled',True),('scientific_verification',True),('pdf_visual_review',True),('pdf_sha256','0'*64),('request_sha256','0'*64),('unexpected',True)]:
            self.data['receipt.json']=original;self.change('receipt.json',lambda x:x.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()

    def test_command_and_historical_path(self):
        original=self.data['command.json']
        for edit in [lambda x:x.append('injected'),lambda x:x.__setitem__(x.index('--network=none'),'--network=host'),lambda x:x.__setitem__(x.index('--mount')+1,'type=bind,src=/old/../sources,dst=/src,readonly')]:
            self.data['command.json']=original;self.change('command.json',edit)
            with self.assertRaises(ValueError):self.check()

    def test_container_profile_and_extra_mounts(self):
        original=self.data['container.json']
        edits=[lambda x:x['HostConfig'].update(NetworkMode='host'),lambda x:x['HostConfig'].update(Privileged=True),lambda x:x['HostConfig'].update(Memory=0),lambda x:x['HostConfig'].update(PidsLimit=True),lambda x:x['HostConfig'].update(Tmpfs={}),lambda x:x['Config']['Env'].append('LD_PRELOAD=/injected'),lambda x:x['Config'].update(Cmd=['-c','evil']),lambda x:x.update(Args=['bad']),lambda x:x['Mounts'].append(dict(Type='bind',Source='/secret',Destination='/secret',RW=False)),lambda x:x['State'].update(ExitCode=True)]
        for edit in edits:
            self.data['container.json']=original;self.change('container.json',edit)
            with self.subTest(edit=edit),self.assertRaises(ValueError):self.check()

    def test_partial_extra_and_special_files(self):
        p=self.bundle/'worker.stderr';p.unlink()
        with self.assertRaises(ValueError):self.check()
        self.seal();(self.bundle/'empty').mkdir()
        with self.assertRaises(ValueError):self.check()
        (self.bundle/'empty').rmdir();p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):self.check()
        p.unlink();os.mkfifo(p)
        with self.assertRaises(ValueError):self.check()
        p.unlink();self.seal();shutil.rmtree(self.bundle/'sources');(self.bundle/'sources').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.check()

    def test_manifest_paths_and_duplicate_keys(self):
        manifest=json.loads((self.bundle/'manifest.json').read_bytes());manifest['files']['sources/../escape']='0'*64
        raw=v.m.encoded(manifest);(self.bundle/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):v.verify(self.bundle,v.m.sha(raw))
        raw=b'{"schema":"x","schema":"y","files":{}}';(self.bundle/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):v.verify(self.bundle,v.m.sha(raw))

    def test_byte_limits_and_failure_snapshot_flag(self):
        with patch.object(v,'MAX_BUNDLE',1),self.assertRaisesRegex(ValueError,'bundle byte limit'):self.check()
        with patch.object(v.c,'CAPTURE',1),self.assertRaisesRegex(ValueError,'byte limit'):self.check()
        self.data['sources/main.tex']+=b'drift';self.change('receipt.json',lambda x:x.update(status='snapshot_changed',snapshot_unchanged_at_final_check=False))
        r=self.check();self.assertFalse(r['snapshot_matches_request']);self.assertEqual(r['status'],'failure_archive_intact')


if __name__=='__main__':unittest.main()
