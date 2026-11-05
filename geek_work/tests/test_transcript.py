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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import geek_work_transcript as t


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.vtt'; self.map = self.root / 'map.json'; self.out = self.root / 'out'
        self.raw = ('\ufeffWEBVTT\r\n\r\nspoken\r\n00:00.000 --> 00:03.500\r\n'
                    'Не доказано: α😀.\r\nПовтор.\r\n\r\nspoken\r\n00:02.000 --> 00:04.000\r\n'
                    'Повтор.\r\n').encode()
        self.source.write_bytes(self.raw)
        self.mapping = dict(schema='geek-work-transcript-map-1', source_sha256=t.m.sha(self.raw),
            title='Synthetic transcript', origin=dict(provider_label='synthetic test', media_reference='unavailable',
            language='ru', transcription_method='unknown'), notes=[dict(id='n1', text='Это не доказательство.',
            citations=[dict(cue='cue-0001', start=0, end=11, quote='Не доказано')])])
        self.save()

    def save(self):
        self.map.write_bytes(t.m.encoded(self.mapping))

    def prepare(self):
        return t.prepare(self.source, self.map, t.m.sha(self.source.read_bytes()), self.out)['manifest_sha256']

    def reseal(self):
        spec=json.loads((self.out/'manifest.json').read_text())
        spec['files']={n:t.m.sha((self.out/n).read_bytes()) for n in t.FILES}
        raw=t.m.encoded(spec); (self.out/'manifest.json').write_bytes(raw); return t.m.sha(raw)

    def test_original_bytes_and_mapping_preserved_without_promotions(self):
        anchor=self.prepare(); result=t.verify(self.out,anchor)
        self.assertEqual((self.out/'source.vtt').read_bytes(),self.raw)
        self.assertEqual((self.out/'map.json').read_bytes(),self.map.read_bytes())
        for key in ('origin_verified','media_alignment_verified','transcription_accuracy_verified','semantic_support_verified','publication_authorized'):
            self.assertIs(result[key],False)

    def test_original_unicode_offsets_bom_crlf_emoji_and_duplicate_labels(self):
        rows=t.cues(self.raw); text=self.raw.decode()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['label'],rows[1]['label'])
        self.assertNotEqual(rows[0]['id'],rows[1]['id'])
        for row in rows:self.assertEqual(text[row['source_start']:row['source_end']],row['text'])
        self.assertIn('α😀.\r\n',rows[0]['text'])

    def test_overlapping_cues_are_retained_and_not_mistaken_for_word_times(self):
        rows=t.cues(self.raw)
        self.assertLess(rows[1]['start_ms'],rows[0]['end_ms'])
        self.prepare(); notes=json.loads((self.out/'notes.json').read_text())
        c=notes['notes'][0]['citations'][0]
        self.assertEqual((c['cue_start_ms'],c['cue_end_ms']),(0,3500))
        self.assertEqual(self.raw.decode()[c['source_start']:c['source_end']],c['quote'])

    def test_repeated_quote_resolves_to_explicit_second_cue(self):
        self.mapping['notes'][0]['citations']=[dict(cue='cue-0002',start=0,end=7,quote='Повтор.')]
        self.save(); self.prepare()
        c=json.loads((self.out/'notes.json').read_text())['notes'][0]['citations'][0]
        self.assertEqual(c['source_start'],self.raw.decode().rindex('Повтор.'))

    def test_exact_quote_does_not_claim_note_entailment(self):
        self.mapping['notes'][0]['text']='Произвольная неподтверждённая интерпретация.'
        self.save(); anchor=self.prepare()
        self.assertFalse(t.verify(self.out,anchor)['semantic_support_verified'])

    def test_citation_errors_fail_before_output(self):
        for field,value in [('cue','absent'),('start',True),('end',1000),('quote','Доказано')]:
            with self.subTest(field=field):
                spec=copy.deepcopy(self.mapping); spec['notes'][0]['citations'][0][field]=value
                self.map.write_bytes(t.m.encoded(spec))
                with self.assertRaises(ValueError):self.prepare()
                self.assertFalse(self.out.exists())

    def test_every_note_requires_evidence_and_unique_id(self):
        for notes in ([dict(id='n1',text='x',citations=[])], self.mapping['notes']*2):
            self.mapping['notes']=notes; self.save()
            with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.out.exists())

    def test_empty_notes_are_valid_transcript_only_packet(self):
        self.mapping['notes']=[]; self.save(); anchor=self.prepare()
        self.assertEqual(t.verify(self.out,anchor)['status'],'transcript_evidence_reproduced')

    def test_timestamps_hour_form_and_no_final_newline(self):
        rows=t.cues(b'WEBVTT\n\n01:02:03.004 --> 01:02:04.005\ntext')
        self.assertEqual(rows[0]['start_ms'],3723004)
        self.assertEqual(rows[0]['end_ms'],3724005)

    def test_invalid_times_and_missing_separator_refused(self):
        for body in ['00:60.000 --> 01:00.000\nx','00:01.000 --> 00:01.000\nx',
                     '00:02.000 --> 00:01.000\nx','12:00:00.000 --> 12:00:00.001\nx',
                     '00:02.000 --> 00:03.000\nx\n\n00:01.000 --> 00:02.000\ny',
                     '00:01.000 --> 00:02.000\nx\n00:02.000 --> 00:03.000\ny']:
            with self.subTest(body=body),self.assertRaises(ValueError):t.cues(('WEBVTT\n\n'+body).encode())

    def test_unsupported_vtt_features_fail_explicitly(self):
        for raw in [b'WEBVTT extra\n\n',b'WEBVTT\n\nNOTE x\nx',b'WEBVTT\n\nSTYLE\nx',
                    b'WEBVTT\n\nREGION\nx',b'WEBVTT\n\n00:00.000 --> 00:01.000 align:start\nx',
                    b'WEBVTT\n\n',b'WEBVTT\n00:00.000 --> 00:01.000\nx',b'WEBVTT\r\rx']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):t.cues(raw)

    def test_markup_untrusted_notes_and_origin_escaped(self):
        self.source.write_bytes(b'WEBVTT\n\n00:00.000 --> 00:01.000\n<script>alert(1)</script>')
        self.mapping['source_sha256']=t.m.sha(self.source.read_bytes());self.mapping['notes']=[]
        self.mapping['origin']['media_reference']='https://example.invalid/<img src=x onerror=bad>'
        self.mapping['title']='<script>bad</script>';self.save();self.prepare()
        page=(self.out/'review.html').read_text()
        self.assertNotIn('<script>',page);self.assertNotIn('<img ',page)
        self.assertIn('&lt;script&gt;',page);self.assertIn("default-src 'none'",page)
        self.assertNotIn('href="https:',page)

    def test_wrong_source_and_manifest_anchors(self):
        with self.assertRaises(ValueError):t.prepare(self.source,self.map,'0'*64,self.out)
        self.mapping['source_sha256']='0'*64;self.save()
        with self.assertRaises(ValueError):self.prepare()
        self.mapping['source_sha256']=t.m.sha(self.raw);self.save();self.prepare()
        with self.assertRaises(ValueError):t.verify(self.out,'0'*64)

    def test_resealed_preview_and_index_tampering_rejected(self):
        for file in ('review.html','cues.json','notes.json'):
            with self.subTest(file=file):
                self.prepare();(self.out/file).write_bytes(b'{}');anchor=self.reseal()
                with self.assertRaises(ValueError):t.verify(self.out,anchor)
                shutil.rmtree(self.out)

    def test_manifest_cannot_promote_verification(self):
        self.prepare();spec=json.loads((self.out/'manifest.json').read_text());spec['origin_verified']=True
        raw=t.m.encoded(spec);(self.out/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):t.verify(self.out,t.m.sha(raw))

    def test_duplicate_keys_float_offsets_and_deep_json_refused(self):
        for raw in [b'{"schema":1,"schema":2}',b'['*40+b'0'+b']'*40,
                    t.m.encoded(self.mapping).replace(b'"start": 0',b'"start": 0.0')]:
            self.map.write_bytes(raw)
            with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.out.exists())

    def test_byte_cue_and_note_limits(self):
        with self.assertRaises(ValueError):t.cues(b'x'*(t.MAX_INPUT+1))
        with patch.object(t,'MAX_CUES',1),self.assertRaises(ValueError):t.cues(self.raw)
        self.mapping['notes']=self.mapping['notes']*129;self.save()
        with self.assertRaises(ValueError):self.prepare()

    def test_symlink_fifo_extra_file_and_archive_link_rejected(self):
        link=self.root/'link';link.symlink_to(self.source)
        with self.assertRaises(ValueError):t.prepare(link,self.map,t.m.sha(self.raw),self.out)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(ValueError):t.prepare(fifo,self.map,t.m.sha(self.raw),self.out)
        anchor=self.prepare();(self.out/'extra').write_text('x')
        with self.assertRaises(ValueError):t.verify(self.out,anchor)
        (self.out/'extra').unlink();(self.out/'source.vtt').unlink();(self.out/'source.vtt').symlink_to(self.source)
        with self.assertRaises(ValueError):t.verify(self.out,anchor)

    def test_output_existing_and_input_overlap_rejected(self):
        anchor=self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()
        with self.assertRaises(ValueError):t.prepare(self.source,self.map,t.m.sha(self.raw),self.root)
        self.assertEqual(t.verify(self.out,anchor)['manifest_sha256'],anchor)

    def test_relocation_without_inputs_or_path_executables(self):
        anchor=self.prepare();moved=self.root/'moved';shutil.move(self.out,moved)
        self.source.unlink();self.map.unlink()
        tool=Path(t.__file__)
        result=subprocess.run([sys.executable,'-B',str(tool),'verify','--bundle',str(moved),'--sha256',anchor],
                              env={**os.environ,'PATH':''},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'transcript_evidence_reproduced')


if __name__=='__main__':unittest.main()
