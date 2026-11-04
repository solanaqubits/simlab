import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_pdf_container as c
import geek_work_pdf_review as review
import test_pdf_pages as fixtures
import test_typst_review_chain as typst_fixture


class DockerFixture:
    def __init__(self,fault=None,runtime=None):self.runtime=c.profile() if runtime is None else runtime;self.fault=fault;self.commands=[];self.states={};self.info=b'Pages: 1\nEncrypted: no\n'
    def inspect(self,name):
        state=self.states[name]
        result=dict(Id='a'*64,Name='/'+name,Image=self.runtime['image_id'],Config=dict(User='1000:1000',Entrypoint=['python3','-I','/opt/geek-work/worker.py']),Mounts=[],State=dict(Running=False,ExitCode=0,OOMKilled=False),HostConfig=dict(NetworkMode='none',ReadonlyRootfs=True,Memory=536870912,MemorySwap=536870912,NanoCpus=1000000000,PidsLimit=64,Privileged=False,PidMode='',IpcMode='private',Binds=None,Devices=[],DeviceRequests=None,PortBindings={},PublishAllPorts=False,CapDrop=['ALL'],CapAdd=None,SecurityOpt=['no-new-privileges'],Tmpfs={'/tmp':'rw,noexec,nosuid,size=67108864,mode=1777'},Ulimits=[dict(Name=n,Soft=v,Hard=v) for n,v in [('cpu',15),('fsize',8388608),('nofile',64)]]))
        if self.fault=='network':result['HostConfig']['NetworkMode']='host'
        if self.fault=='readonly_type':result['HostConfig']['ReadonlyRootfs']=1
        if self.fault=='host_mount':result['Mounts']=[{'Source':'/host'}]
        if self.fault=='exit_state' and state.get('started'):result['State']['ExitCode']=2
        return result
    def capture(self,args,data=b'',timeout=15,limit=c.CONTROL_LIMIT):
        self.commands.append((args,data,timeout,limit));out=b'';err=b'';code=0;error=None;overflow=False
        if args[:3]==['docker','image','inspect']:
            out=c.m.encoded([dict(Id='sha256:'+'0'*64 if self.fault=='image' else self.runtime['image_id'],Os='linux',Architecture='amd64')])
        elif args[:2]==['docker','create']:
            name=args[args.index('--name')+1];tail=args[args.index(self.runtime['image_id'])+1:];self.states[name]=dict(mode=tail[0],removed=False)
            out=b'a'*64+b'\n'
            if self.fault=='create_timeout':code=None;error='TimeoutExpired'
        elif args[:2]==['docker','inspect']:out=c.m.encoded([self.inspect(args[-1])])
        elif args[:2]==['docker','start']:
            state=self.states[args[-1]];state['started']=True;mode=state['mode']
            out=c.m.encoded(self.runtime['worker_observation']) if mode=='profile' else self.info if mode=='info' else fixtures.png()
            if self.fault=='profile' and mode=='profile':out=b'{}'
            if self.fault=='bad_png' and mode=='page':out=b'not PNG'
            if self.fault=='process' and mode=='page':code=1;err=b'Fixture Poppler error'
            if self.fault=='overflow' and mode=='page':overflow=True
            if self.fault=='diagnostic' and mode=='page':err=b'Fixture renderer warning'
        elif args[:3]==['docker','rm','-f']:
            if self.fault=='cleanup':code=1
            else:
                if args[-1] in self.states:self.states[args[-1]]['removed']=True
                out=(args[-1]+'\n').encode()
        elif args[:3]==['docker','ps','-a']:
            name=args[args.index('--filter')+1].removeprefix('name=^').removesuffix('$')
            out=b'a'*64+b'\n' if name in self.states and not self.states[name]['removed'] else b''
        else:raise AssertionError(args)
        return out,err,dict(returncode=code,error_class=error,capture_overflow=overflow)


class ContainerPagesTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PdfPageTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root;self.output=self.root/'container-pages';self.fake=DockerFixture();self.pin=c.m.sha(c.m.encoded(c.profile()))
    def render(self):
        with patch.object(c,'capture',side_effect=self.fake.capture):return c.render(self.f.binding,self.f.anchor,self.pin,self.output)
    def test_source_bound_pages_and_no_host_input_mount(self):
        result=self.render();report,archive=c.p.verified(self.output,result['manifest_sha256']);self.assertEqual(report['renderer_backend'],'docker');self.assertEqual(report['page_count'],1)
        self.assertEqual(archive['pages/0001.png'],fixtures.png());self.assertEqual(report['pdf']['sha256'],c.p.pdf_input.verified(self.f.binding,self.f.anchor)[0]['pdf']['sha256'])
        self.assertTrue(all(x['container_removed'] for x in report['container_operations']));self.assertFalse(report['container_escape_protection_verified'])
        for args,data,timeout,limit in self.fake.commands:
            if args[:2]==['docker','create']:self.assertNotIn('--mount',args);self.assertNotIn('-v',args);self.assertIn('--pull=never',args)
    def test_profile_pin_refused_before_docker_or_output(self):
        with patch.object(c,'capture',side_effect=AssertionError('no Docker')),self.assertRaisesRegex(ValueError,'anchor mismatch'):c.render(self.f.binding,self.f.anchor,'0'*64,self.output)
        self.assertFalse(self.output.exists())
    def test_oversize_pdf_refused_before_docker(self):
        original=c.profile()
        with patch.object(c,'profile',return_value=dict(original,max_pdf_bytes=1)),patch.object(c,'capture',side_effect=AssertionError('no Docker')),self.assertRaisesRegex(ValueError,'byte limit'):c.render(self.f.binding,self.f.anchor,self.pin,self.output)
    def test_missing_or_wrong_image_fails_before_create_and_archives_failure(self):
        self.fake.fault='image';result=self.render();self.assertEqual(result['status'],'container_render_failed');self.assertFalse(any(a[:2]==['docker','create'] for a,_,_,_ in self.fake.commands));self.assert_failure(result)
    def assert_failure(self,result):
        self.assertEqual(c.verify(self.output,result['manifest_sha256'])['status'],'failure_archive_intact')
        with self.assertRaisesRegex(ValueError,'successful container pages'):c.p.verified(self.output,result['manifest_sha256'])
    def test_create_timeout_still_removes_created_container(self):
        self.fake.fault='create_timeout';result=self.render();self.assert_failure(result);self.assertTrue(all(s['removed'] for s in self.fake.states.values()))
    def test_wrong_network_or_exposure_blocks_start(self):
        self.fake.fault='network';result=self.render();self.assert_failure(result);self.assertFalse(any(a[:2]==['docker','start'] for a,_,_,_ in self.fake.commands))
    def test_host_mount_blocks_start(self):
        self.fake.fault='host_mount';self.assert_failure(self.render());self.assertFalse(any(a[:2]==['docker','start'] for a,_,_,_ in self.fake.commands))
    def test_boolean_configuration_is_strict(self):
        self.fake.fault='readonly_type';self.assert_failure(self.render())
    def test_worker_profile_mismatch_is_failure(self):
        self.fake.fault='profile';self.assert_failure(self.render())
    def test_poppler_failure_preserves_raw_diagnostic(self):
        self.fake.fault='process';result=self.render();self.assert_failure(result);self.assertEqual((self.output/'operations/0002/start.stderr').read_bytes(),b'Fixture Poppler error')
    def test_cleanup_failure_cannot_enter_review(self):
        self.fake.fault='cleanup';result=self.render();self.assertEqual(result['status'],'cleanup_failed');self.assert_failure(result)
    def test_exit_state_failure_cannot_promote_client_success(self):
        self.fake.fault='exit_state';self.assert_failure(self.render())
    def test_invalid_png_and_capture_overflow_are_archived(self):
        self.fake.fault='bad_png';result=self.render();self.assert_failure(result);self.assertFalse((self.output/'pages').exists())
    def test_capture_overflow_rejects_page(self):
        self.fake.fault='overflow';self.assert_failure(self.render())
    def test_encryption_and_page_bounds_are_failure_archives(self):
        self.fake.info=b'Pages: 17\nEncrypted: no\n';result=self.render();self.assert_failure(result);self.assertFalse(any(s['mode']=='page' for s in self.fake.states.values()))
    def test_renderer_warnings_survive_review(self):
        self.fake.fault='diagnostic';result=self.render();report,_=c.p.verified(self.output,result['manifest_sha256']);self.assertTrue(report['renderer_diagnostics_present']);spec=review.template(result['manifest_sha256'],report)
        spec['reviewer']=dict(id='Fixture',role='implementer',prior_exposure='Protocol fixture');spec['diagnostics']=dict(status='reviewed',note='Recorded')
        for row in spec['pages']:
            for check in row['checks'].values():check.update(status='pass',note='Fixture')
        self.assertEqual(review.assess(c.m.encoded(spec),result['manifest_sha256'],report)['status'],'visual_review_reported_with_diagnostics')
    def test_relocation_and_offline_review_without_docker(self):
        result=self.render();moved=self.root/'moved';shutil.copytree(self.output,moved);shutil.rmtree(self.output);shutil.rmtree(self.f.binding)
        with patch.object(c,'capture',side_effect=AssertionError('offline')):
            report,archive=c.p.verified(moved,result['manifest_sha256']);self.assertEqual(c.verify(moved,result['manifest_sha256'])['status'],'page_packet_consistent');self.assertEqual(review.template(result['manifest_sha256'],report)['page_packet_sha256'],result['manifest_sha256'])
    def test_report_promotion_and_operation_command_tamper_refused(self):
        result=self.render();path=self.output/'report.json';raw=path.read_bytes();report=json.loads(raw);report['pdf_conformance_verified']=True;path.write_bytes(c.m.encoded(report));pin=self.reseal()
        with self.assertRaises(ValueError):c.verify(self.output,pin)
        path.write_bytes(raw);meta=self.output/'operations/0000/create.json';value=json.loads(meta.read_bytes());value['argv'][value['argv'].index('none')]='host';meta.write_bytes(c.m.encoded(value));pin=self.reseal()
        with self.assertRaises(ValueError):c.verify(self.output,pin)
    def reseal(self):
        path=self.output/'manifest.json';value=json.loads(path.read_bytes());value['files']={name:c.m.sha((self.output/name).read_bytes()) for name in value['files']};path.write_bytes(c.m.encoded(value));return c.m.sha(path.read_bytes())
    def test_extra_file_or_operation_order_refused(self):
        result=self.render();(self.output/'extra').mkdir()
        with self.assertRaises(ValueError):c.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').rmdir();path=self.output/'manifest.json';value=json.loads(path.read_bytes());value['operations'][0]['mode']='info';path.write_bytes(c.m.encoded(value))
        with self.assertRaises(ValueError):c.verify(self.output,c.m.sha(path.read_bytes()))
    def test_aggregate_image_bounds_are_failure_not_acceptance(self):
        with patch.object(c.p,'MAX_IMAGES',1):result=self.render();self.assert_failure(result)
    def test_deadline_preserves_prefix_as_failure(self):
        with patch.object(c,'TOTAL_TIMEOUT',0):result=self.render();self.assert_failure(result)
    def test_control_capture_overflow_timeout_and_missing_client(self):
        out,err,row=c.capture([sys.executable,'-c','print("x"*100)'],limit=16)
        self.assertEqual(len(out),16);self.assertTrue(row['capture_overflow'])
        out,err,row=c.capture([sys.executable,'-c','import time;time.sleep(1)'],timeout=.01)
        self.assertEqual(row['error_class'],'TimeoutExpired');self.assertIsNone(row['returncode'])
        out,err,row=c.capture(['/nonexistent/geek-work-docker'])
        self.assertEqual(row['error_class'],'FileNotFoundError')

    def test_interruption_after_all_working_captures_stops_pipeline(self):
        original=c.m.require;calls=0
        def require(ok,message):
            nonlocal calls
            if message=='operation process failure':
                calls+=1
                if calls==5:raise InterruptedError('synthetic SIGTERM boundary')
            return original(ok,message)
        with patch.object(c.m,'require',side_effect=require):result=self.render()
        self.assertEqual(result['status'],'container_render_failed');self.assertEqual(len(self.fake.states),1)
        self.assertTrue(all(state['removed'] for state in self.fake.states.values()))
        self.assertTrue((self.output/'operations/0000/interrupted.json').exists());self.assert_failure(result)
        report,_=c.verified(self.output,result['manifest_sha256']);self.assertEqual(report['operations'][0]['error_class'],'InterruptedError')

    def test_explicit_fixed_modes_and_output_separation(self):
        with self.assertRaises(ValueError):c.execute(self.root/'bad','page',b'',17)
        with self.assertRaises(ValueError):c.render(self.f.binding,self.f.anchor,self.pin,self.f.binding/'inside')
        self.output.mkdir()
        with self.assertRaises(ValueError):self.render()


class TypstContainerChainTests(unittest.TestCase):
    def test_container_pages_review_and_status_preserve_v2_binding(self):
        f=typst_fixture.TypstReviewChainTests();f.setUp();self.addCleanup(f.doCleanups);out=f.root/'docker-pages';fake=DockerFixture();pin=c.m.sha(c.m.encoded(c.profile()))
        with patch.object(c,'capture',side_effect=fake.capture):result=c.render(f.gate,f.gate_pin,pin,out)
        review_out=f.root/'docker-review';review_pin=f.record_review(out,result['manifest_sha256'],review_out)
        f.spec['page_packet']=dict(path=out.name,sha256=result['manifest_sha256']);f.spec['visual_review']=dict(path=review_out.name,sha256=review_pin)
        with patch.object(c,'capture',side_effect=AssertionError('offline')):report=f.assess()
        self.assertEqual(report['status'],'local_chain_consistent_review_reported');self.assertFalse(report['publication_authorized'])


if __name__=='__main__':unittest.main()
