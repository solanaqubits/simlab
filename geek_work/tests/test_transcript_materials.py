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
import geek_work_transcript_materials as x


class MaterialBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.materials=self.root/'inputs';self.materials.mkdir()
        self.bundle=self.root/'transcript';self.output=self.root/'output';self.mapping=self.root/'map.json'
        source=self.root/'source.vtt';source.write_bytes('WEBVTT\n\n00:01.000 --> 00:03.000\nα😀 ≠ 0\n'.encode())
        tm=self.root/'transcript-map.json';tm.write_bytes(x.m.encoded(dict(schema='geek-work-transcript-map-1',
            source_sha256=x.m.sha(source.read_bytes()),title='Synthetic only',notes=[],origin=dict(
            provider_label='test',media_reference='not fetched',language='ru',transcription_method='unknown'))))
        self.anchor=x.t.prepare(source,tm,x.m.sha(source.read_bytes()),self.bundle)['manifest_sha256']
        rows=[]
        for ident,raw,kind in [('clip',b'\x00synthetic clip','media'),('slides',b'%PDF synthetic only','slides'),('ocr','α ≠ 0'.encode(),'ocr')]:
            (self.materials/ident).write_bytes(raw)
            rows.append(dict(id=ident,path=ident,sha256=x.m.sha(raw),kind=kind))
        self.spec=dict(schema=x.SCHEMA,transcript_sha256=self.anchor,materials=rows,bindings=[
            dict(id='b1',cue='cue-0001',material='clip',locator=dict(start_ms=5000,end_ms=7000),review_note='Different clip clock; alignment unverified.'),
            dict(id='b2',cue='cue-0001',material='slides',locator=dict(page=3),review_note='Check formula manually.'),
            dict(id='b3',cue='cue-0001',material='ocr',locator=dict(page=3,slides='slides'),review_note='OCR candidate only.')])
        self.save()

    def save(self):self.mapping.write_bytes(x.m.encoded(self.spec))
    def prepare(self):return x.prepare(self.bundle,self.anchor,self.mapping,self.materials,self.output)['manifest_sha256']

    def test_portable_replay_without_original_inputs(self):
        anchor=self.prepare();moved=self.root/'relocated';self.output.rename(moved)
        shutil.rmtree(self.materials);shutil.rmtree(self.bundle);self.mapping.unlink()
        self.assertEqual(x.verify(moved,anchor)['status'],'material_bindings_reproduced')

    def test_exact_unicode_cue_and_independent_media_clock(self):
        self.prepare();r=json.loads((self.output/'bindings.json').read_text())
        self.assertEqual(r['bindings'][0]['cue_evidence']['text'],'α😀 ≠ 0')
        self.assertEqual(r['bindings'][0]['cue_evidence']['start_ms'],1000)
        self.assertEqual(r['bindings'][0]['locator']['start_ms'],5000)
        self.assertEqual((self.output/'map.json').read_bytes(),self.mapping.read_bytes())

    def test_arbitrary_bytes_do_not_certify_formats_pages_or_alignment(self):
        anchor=self.prepare();result=x.verify(self.output,anchor)
        for flag in x.FLAGS:self.assertIs(result[flag],False)
        self.assertEqual((self.output/'materials/clip.bin').read_bytes(),b'\x00synthetic clip')

    def test_wrong_anchors_refused(self):
        with self.assertRaises(ValueError):x.prepare(self.bundle,'0'*64,self.mapping,self.materials,self.output)
        anchor=self.prepare()
        with self.assertRaises(ValueError):x.verify(self.output,'0'*64)
        self.assertNotEqual(anchor,'0'*64)

    def test_wrong_material_hash_before_output(self):
        (self.materials/'clip').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists())

    def test_invalid_references_and_unreferenced_materials(self):
        base=copy.deepcopy(self.spec)
        for mutation in ('cue','material','slides','unused'):
            self.spec=copy.deepcopy(base)
            if mutation=='unused':self.spec['bindings']=self.spec['bindings'][1:]
            elif mutation=='slides':self.spec['bindings'][2]['locator']['slides']='clip'
            else:self.spec['bindings'][0][mutation]='missing'
            self.save()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists())

    def test_invalid_locators_including_bool(self):
        for value in [dict(start_ms=True,end_ms=7000),dict(start_ms=0,end_ms=0),
                      dict(start_ms=-1,end_ms=1),dict(start_ms=0,end_ms=x.t.MAX_TIME+1),dict(page=1)]:
            self.spec['bindings'][0]['locator']=value;self.save()
            with self.subTest(value=value),self.assertRaises(ValueError):self.prepare()
        for value in (0,True,100001):
            with self.subTest(page=value),self.assertRaises(ValueError):x.integer(value,1,100000)

    def test_duplicate_ids_paths_and_bindings(self):
        base=copy.deepcopy(self.spec)
        for mutation in ('id','path','binding'):
            self.spec=copy.deepcopy(base)
            if mutation=='binding':self.spec['bindings'].append(self.spec['bindings'][0])
            else:self.spec['materials'][1][mutation]=self.spec['materials'][0][mutation]
            self.save()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.prepare()

    def test_safe_paths_and_leaf_directory_root_symlinks(self):
        for value in ('../clip','/clip','a/../clip'):
            self.spec['materials'][0]['path']=value;self.save()
            with self.assertRaises(ValueError):self.prepare()
        link=self.materials/'link';link.symlink_to(self.materials/'clip')
        with self.assertRaises(OSError):x.binary_source(self.materials,'link')
        folder=self.materials/'folder';folder.symlink_to(self.materials,target_is_directory=True)
        with self.assertRaises(OSError):x.binary_source(self.materials,'folder/clip')
        with self.assertRaises(OSError):x.binary_source(folder,'clip')

    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.materials/'pipe')
        with self.assertRaises(ValueError):x.binary_source(self.materials,'pipe')

    def test_file_total_and_empty_limits_before_output(self):
        with patch.object(x,'MAX_MATERIAL',3),self.assertRaises(ValueError):self.prepare()
        with patch.object(x,'MAX_TOTAL',3),self.assertRaises(ValueError):self.prepare()
        (self.materials/'clip').write_bytes(b'')
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists())

    def test_duplicate_json_and_unknown_fields_refused(self):
        self.mapping.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(ValueError):self.prepare()
        self.spec['verified']=True;self.save()
        with self.assertRaises(ValueError):self.prepare()

    def test_resealed_derived_binding_tampering_refused(self):
        self.prepare();p=self.output/'bindings.json';r=json.loads(p.read_text())
        r['bindings'][0]['cue_evidence']['text']='changed';p.write_bytes(x.m.encoded(r))
        manifest=json.loads((self.output/'manifest.json').read_text());manifest['files']['bindings.json']=x.m.sha(p.read_bytes())
        raw=x.m.encoded(manifest);(self.output/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):x.verify(self.output,x.m.sha(raw))

    def test_tampered_attachment_and_extra_file_refused(self):
        anchor=self.prepare();p=self.output/'materials/clip.bin';original=p.read_bytes();p.write_bytes(b'bad')
        with self.assertRaises(ValueError):x.verify(self.output,anchor)
        p.write_bytes(original);(self.output/'extra').write_bytes(b'bad')
        with self.assertRaises(ValueError):x.verify(self.output,anchor)

    def test_transcript_tampering_refused(self):
        (self.bundle/'cues.json').write_bytes(b'[]')
        with self.assertRaises(ValueError):self.prepare()

    def test_output_is_new_and_disjoint(self):
        with self.assertRaises(ValueError):x.prepare(self.bundle,self.anchor,self.mapping,self.materials,self.materials/'out')
        self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()

    def test_cli_prepare_verify_and_refusal(self):
        cmd=[sys.executable,'-B',x.__file__]
        result=subprocess.run(cmd+['prepare','--bundle',str(self.bundle),'--sha256',self.anchor,
            '--map',str(self.mapping),'--root',str(self.materials),'--output',str(self.output)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        anchor=json.loads(result.stdout)['manifest_sha256']
        result=subprocess.run(cmd+['verify','--bundle',str(self.output),'--sha256',anchor],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run(cmd+['verify','--bundle',str(self.output),'--sha256','0'*64],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual(json.loads(result.stdout)['status'],'refused')


if __name__=='__main__':unittest.main()
