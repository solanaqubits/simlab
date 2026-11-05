import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_transcript_json as j


class TranscriptJSONTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'input.json';self.out=self.root/'converted'
        self.raw=b'[ {"start":0.1,"end":0.3,"text":"No proof.","words":[{"word":"No","start":0.1}]} ]\n'
        self.source.write_bytes(self.raw)

    def prepare(self,fmt='lecture-segments'):
        return j.prepare(self.source,j.m.sha(self.source.read_bytes()),fmt,self.out)['manifest_sha256']

    def convert(self,raw,fmt='lecture-segments'):
        return j.artifacts(raw.encode() if isinstance(raw,str) else raw,fmt)

    def test_exact_raw_bytes_and_extra_metadata_preserved(self):
        anchor=self.prepare();self.assertEqual((self.out/'source.json').read_bytes(),self.raw)
        report=json.loads((self.out/'conversion.json').read_text())
        self.assertEqual(report['segments'][0]['uninterpreted_keys'],['words'])
        self.assertEqual(report['segments'][0]['source_pointer'],'/0')
        self.assertFalse(report['origin_verified']);self.assertFalse(report['semantic_support_verified'])
        self.assertEqual(j.verify(self.out,anchor)['status'],'transcript_json_reproduced')

    def test_duration_addition_exact_point_one_plus_point_two(self):
        d=self.convert('{"video_id":"reported-id","language":"en","metadata":{"x":1},"transcript":[{"start":0.1,"duration":0.2,"text":"x"}]}','transcriptapi-json')
        report=json.loads(d['conversion.json']);s=report['segments'][0]
        self.assertEqual((s['start_ms'],s['end_ms']),(100,300))
        self.assertEqual(s['source_pointer'],'/transcript/0')
        self.assertEqual(report['uninterpreted_envelope_keys'],['language','metadata','video_id'])

    def test_decimal_exponent_and_long_exact_zeros(self):
        d=self.convert('[{"start":1e-3,"end":0.003000000000000000000000000000000000000,"text":"x"}]')
        self.assertIn(b'00:00:00.001 --> 00:00:00.003',d['source.vtt'])

    def test_long_precision_never_rounded_by_decimal_context(self):
        with self.assertRaisesRegex(ValueError,'sub-millisecond'):
            self.convert('[{"start":0,"end":0.003000000000000000000000000000000000001,"text":"x"}]')

    def test_submillisecond_start_end_and_duration_refused(self):
        for raw,fmt in [('[{"start":0.0001,"end":1,"text":"x"}]','lecture-segments'),
                        ('[{"start":0,"end":0.9999,"text":"x"}]','lecture-segments'),
                        ('{"transcript":[{"start":0,"duration":0.0001,"text":"x"}]}','transcriptapi-json')]:
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'sub-millisecond'):self.convert(raw,fmt)

    def test_time_not_bool_string_null_or_negative(self):
        for value in ('true','"0"','null','-1'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.convert('[{"start":'+value+',"end":1,"text":"x"}]')

    def test_nonfinite_duplicate_keys_and_extreme_exponents(self):
        for value in ('NaN','Infinity','-Infinity','1e1001','1e'+('9'*100)):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.convert('[{"start":0,"end":'+value+',"text":"x"}]')
        with self.assertRaises(ValueError):self.convert('[{"start":0,"start":1,"end":2,"text":"x"}]')

    def test_depth_token_byte_and_cue_limits(self):
        for raw in ('['*33+'0'+']'*33,'['+'9'*129+']', 'x'*(j.t.MAX_INPUT+1)):
            with self.assertRaises(ValueError):self.convert(raw)
        with patch.object(j.t,'MAX_CUES',0),self.assertRaises(ValueError):self.convert(self.raw)

    def test_explicit_format_and_required_shapes(self):
        for raw,fmt in [('{}','lecture-segments'),('[]','lecture-segments'),('[]','transcriptapi-json'),
                        ('{"transcript":"text"}','transcriptapi-json'),('[{"start":0}]','lecture-segments'),
                        ('[]','auto')]:
            with self.subTest(raw=raw,fmt=fmt),self.assertRaises(ValueError):self.convert(raw,fmt)

    def test_zero_negative_unsorted_and_overlong_intervals(self):
        for rows in [[dict(start=1,end=1,text='x')],[dict(start=2,end=1,text='x')],
                     [dict(start=0,end=43201,text='x')],
                     [dict(start=2,end=3,text='x'),dict(start=0,end=1,text='y')]]:
            with self.assertRaises(ValueError):self.convert(json.dumps(rows))
        with self.assertRaises(ValueError):self.convert('{"transcript":[{"start":43200,"duration":1,"text":"x"}]}','transcriptapi-json')

    def test_overlaps_and_repeated_text_kept(self):
        rows=[dict(start=0,end=3,text='repeat'),dict(start=1,end=2,text='repeat')]
        d=self.convert(json.dumps(rows));r=json.loads(d['conversion.json'])['segments']
        self.assertEqual(len(r),2);self.assertNotEqual(r[0]['source_pointer'],r[1]['source_pointer'])

    def test_unicode_crlf_leading_space_and_literal_markup_kept(self):
        text=' α😀\r\n<script>x</script>'
        d=self.convert(json.dumps([dict(start=0,end=1,text=text)],ensure_ascii=False))
        self.assertEqual(j.t.cues(d['source.vtt'])[0]['text'],text)

    def test_unrepresentable_payloads_refused_not_silently_trimmed(self):
        for text in ('x\n','\nx','x\n\ny','a\rb','x --> y','\x00x','   '):
            with self.subTest(text=text),self.assertRaises(ValueError):
                self.convert(json.dumps([dict(start=0,end=1,text=text)]))

    def test_original_source_hash_required(self):
        with self.assertRaises(ValueError):j.prepare(self.source,'0'*64,'lecture-segments',self.out)
        self.assertFalse(self.out.exists())

    def test_tampering_rejected_even_after_resealing_artifact_hashes(self):
        self.prepare();(self.out/'source.vtt').write_bytes(b'WEBVTT\n\n')
        spec=json.loads((self.out/'manifest.json').read_text());spec['files']['source.vtt']=j.m.sha((self.out/'source.vtt').read_bytes())
        raw=j.m.encoded(spec);(self.out/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):j.verify(self.out,j.m.sha(raw))

    def test_schema_and_unknown_manifest_fields_not_accepted(self):
        self.prepare();spec=json.loads((self.out/'manifest.json').read_text());spec['origin_verified']=True
        raw=j.m.encoded(spec);(self.out/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):j.verify(self.out,j.m.sha(raw))

    def test_existing_output_symlink_fifo_and_extra_file_rejected(self):
        link=self.root/'link';link.symlink_to(self.source)
        with self.assertRaises(ValueError):j.prepare(link,j.m.sha(self.raw),'lecture-segments',self.out)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(ValueError):j.prepare(fifo,j.m.sha(self.raw),'lecture-segments',self.out)
        anchor=self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()
        (self.out/'extra').write_text('x')
        with self.assertRaises(ValueError):j.verify(self.out,anchor)

    def test_output_overlap_refused(self):
        with self.assertRaises(ValueError):j.prepare(self.source,j.m.sha(self.raw),'lecture-segments',self.root)

    def test_end_to_end_note_map_uses_converted_exact_text(self):
        self.prepare();vtt=self.out/'source.vtt';mp=self.root/'notes.json'
        mp.write_bytes(j.m.encoded(dict(schema='geek-work-transcript-map-1',source_sha256=j.m.sha(vtt.read_bytes()),title='Synthetic',origin=dict(provider_label='reported',media_reference='unavailable',language='en',transcription_method='unknown'),notes=[dict(id='n1',text='A note',citations=[dict(cue='cue-0001',start=0,end=9,quote='No proof.')])])))
        review=self.root/'review';r=j.t.prepare(vtt,mp,j.m.sha(vtt.read_bytes()),review)
        self.assertFalse(j.t.verify(review,r['manifest_sha256'])['semantic_support_verified'])

    def review_packet(self, text='No proof.'):
        source=self.root/'review-source.vtt'
        source.write_text('WEBVTT\n\n00:00:00.100 --> 00:00:00.300\n'+text+'\n')
        mp=self.root/'review-map.json'
        mp.write_bytes(j.m.encoded(dict(schema='geek-work-transcript-map-1',source_sha256=j.m.sha(source.read_bytes()),title='Synthetic',origin=dict(provider_label='reported',media_reference='unavailable',language='en',transcription_method='unknown'),notes=[])))
        review=self.root/'review'
        anchor=j.t.prepare(source,mp,j.m.sha(source.read_bytes()),review)['manifest_sha256']
        return review,anchor

    def test_link_checks_both_archives_and_exact_converted_bytes(self):
        anchor=self.prepare();review,review_anchor=self.review_packet()
        result=j.verify_review(self.out,anchor,review,review_anchor)
        self.assertEqual(result['status'],'transcript_json_review_link_reproduced')
        self.assertFalse(result['semantic_support_verified'])

    def test_valid_unrelated_review_refused(self):
        anchor=self.prepare();review,review_anchor=self.review_packet('Different text')
        with self.assertRaisesRegex(ValueError,'different converted transcript'):
            j.verify_review(self.out,anchor,review,review_anchor)

    def test_link_rejects_corrupt_review_and_wrong_parent_anchor(self):
        anchor=self.prepare();review,review_anchor=self.review_packet()
        with self.assertRaises(ValueError):j.verify_review(self.out,'0'*64,review,review_anchor)
        (review/'notes.json').write_text('{}')
        with self.assertRaises(ValueError):j.verify_review(self.out,anchor,review,review_anchor)

    def test_relocation_without_source_or_executables(self):
        anchor=self.prepare();new=self.root/'relocated';shutil.move(self.out,new);self.source.unlink()
        r=subprocess.run([sys.executable,'-B',j.__file__,'verify','--bundle',str(new),'--sha256',anchor],env={**os.environ,'PATH':''},capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(json.loads(r.stdout)['status'],'transcript_json_reproduced')


if __name__=='__main__':unittest.main()
