import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_numeric_history as h


class NumericHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.inputs=self.root/'inputs';self.inputs.mkdir();self.out=self.root/'history'
        self.spec_path=self.root/'history.json'
        self.before=self.numeric('before',4,'4');self.after=self.numeric('after',5,'5')
        self.manuscript=self.document('manuscript','5',self.inputs/'after/report.json')
        self.spec=dict(schema=h.SCHEMA,before=dict(path='before',sha256=self.before),after=dict(path='after',sha256=self.after),
            manuscript=dict(path='manuscript',sha256=self.manuscript),revisions=[dict(id='revision-1',numeric_claim='count',
                reason='Corrected the selected fixture input; not an experiment.',manuscript_claim='count-text',report_material='numbers',
                value_span=dict(document='note',start=22,end=23,quote='5'))])
        self.save()

    def numeric(self,name,actual,expected):
        source=self.root/(name+'-source');source.mkdir();raw=h.m.encoded(dict(count=actual));(source/'data.json').write_bytes(raw)
        spec=dict(schema='geek-work-numeric-claims-1',id='fixture-map',sources=[dict(id='data',path='data.json',sha256=h.m.sha(raw),role='data')],
            claims=[dict(id='count',statement='Selected fixture count',value=expected,unit='declared count',uncertainty=None,
                         operation='identity',operands=[dict(source_id='data',selector=dict(json_pointer='/count'))])])
        path=self.root/(name+'-spec.json');blob=h.m.encoded(spec);path.write_bytes(blob)
        return h.numeric.capture('claims',path,h.m.sha(blob),source,self.inputs/name)['manifest_sha256']

    def document(self,name,value,report):
        root=self.root/(name+'-source');root.mkdir();text='The measured count is '+value+'.';(root/'note.md').write_text(text)
        report_raw=report.read_bytes();(root/'numbers.json').write_bytes(report_raw)
        mapping=dict(schema='geek-work-manuscript-claims-1',documents=[dict(id='note',path='note.md',sha256=h.m.sha(text.encode()))],
            materials=[dict(id='numbers',path='numbers.json',sha256=h.m.sha(report_raw),kind='measurement_report',origin=dict(repository='synthetic-unverified',commit='0'*40))],
            claims=[dict(id='count-text',statement=dict(document='note',start=0,end=len(text),quote=text),reported_evidence_state='empirical_reported',
              scope='Synthetic only',assumptions=['Fixture data supplied'],non_claims=['No scientific validity or execution claim'],open_obligations=['Independent review'],
              evidence=[dict(citation=dict(material='numbers',start=0,end=1,quote='{'),declaration=None)])])
        # Existing protocol deliberately permits a short literal citation. The history
        # binds the full material bytes and claim ID, not semantic citation adequacy.
        mapping['schema']='geek-work-manuscript-claim-map-1'
        path=self.root/(name+'-map.json');raw=h.m.encoded(mapping);path.write_bytes(raw)
        return h.claims.prepare(path,h.m.sha(raw),root,root,self.inputs/name)['manifest_sha256']

    def save(self):self.spec_path.write_bytes(h.m.encoded(self.spec))
    def build(self):return h.build(self.spec_path,h.m.sha(self.spec_path.read_bytes()),self.inputs,self.out)['manifest_sha256']
    def report(self):return json.loads((self.out/'report.json').read_text())

    def test_history_retains_both_values_reasons_and_scope(self):
        self.build();r=self.report();row=r['revisions'][0]
        self.assertEqual(row['before']['claim']['value'],'4');self.assertEqual(row['after']['claim']['value'],'5')
        self.assertEqual(row['before']['history_role'],'superseded_in_this_history')
        self.assertEqual(row['changed_claim_fields'],['value']);self.assertTrue(r['source_inventory_changed'])
        self.assertTrue(row['document_matches_declared']);self.assertTrue(row['document_matches_recomputed'])
        self.assertEqual(row['manuscript_claim']['non_claims'],['No scientific validity or execution claim'])
        for flag in h.FLAGS:self.assertFalse(r[flag])

    def test_relocation_without_sources_or_inputs(self):
        anchor=self.build();moved=self.root/'moved';self.out.rename(moved);shutil.rmtree(self.inputs);self.spec_path.unlink()
        self.assertTrue(h.verify(moved,anchor)['integrity_reproduced'])

    def test_no_nested_archive_is_modified(self):
        before={str(p.relative_to(self.inputs)):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()}
        self.build();self.assertEqual(before,{str(p.relative_to(self.inputs)):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()})

    def test_numeric_mismatch_survives_history(self):
        anchor=self.numeric('mismatch',6,'5');doc=self.document('mismatch-doc','5',self.inputs/'mismatch/report.json')
        self.spec['after']=dict(path='mismatch',sha256=anchor);self.spec['manuscript']=dict(path='mismatch-doc',sha256=doc);self.save();a=self.build()
        row=self.report()['revisions'][0];self.assertEqual(row['after']['result']['status'],'value_mismatch')
        self.assertTrue(row['document_matches_declared']);self.assertFalse(row['document_matches_recomputed']);h.verify(self.out,a)

    def test_stale_document_number_visible_without_rewriting(self):
        doc=self.document('stale-doc','4',self.inputs/'after/report.json');self.spec['manuscript']=dict(path='stale-doc',sha256=doc)
        self.spec['revisions'][0]['value_span']['quote']='4';self.save();self.build();row=self.report()['revisions'][0]
        self.assertFalse(row['document_matches_declared']);self.assertFalse(row['document_matches_recomputed'])
        self.assertEqual(row['value_span']['quote'],'4')

    def test_different_report_cannot_back_current_document(self):
        doc=self.document('wrong-report','5',self.inputs/'before/report.json');self.spec['manuscript']=dict(path='wrong-report',sha256=doc);self.save()
        with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())

    def test_missing_claim_or_material_refused(self):
        base=copy.deepcopy(self.spec)
        for key in ('numeric_claim','manuscript_claim','report_material'):
            self.spec=copy.deepcopy(base);self.spec['revisions'][0][key]='absent';self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):self.build()

    def test_bad_numeric_span_and_non_numeric_text_refused(self):
        base=copy.deepcopy(self.spec)
        for span in (dict(document='note',start=True,end=23,quote='5'),dict(document='note',start=0,end=3,quote='The'),dict(document='note',start=22,end=23,quote='6')):
            self.spec=copy.deepcopy(base);self.spec['revisions'][0]['value_span']=span;self.save()
            with self.subTest(span=span),self.assertRaises(ValueError):self.build()

    def test_duplicate_identity_and_overlapping_archives_refused(self):
        self.spec['revisions']*=2;self.save()
        with self.assertRaises(ValueError):self.build()
        self.spec['revisions']=self.spec['revisions'][:1];self.spec['after']['path']='before/child';self.save()
        with self.assertRaises(ValueError):self.build()

    def test_same_revision_is_not_a_history(self):
        self.spec['after']['sha256']=self.before;self.save()
        with self.assertRaises(ValueError):self.build()

    def test_archived_input_tampering_and_wrong_anchor(self):
        anchor=self.build()
        with self.assertRaises(ValueError):h.verify(self.out,'0'*64)
        (self.out/'inputs/after/report.json').write_text('{}')
        with self.assertRaises(ValueError):h.verify(self.out,anchor)

    def test_resealed_derived_report_tampering_refused(self):
        self.build();p=self.out/'report.json';r=json.loads(p.read_text());r['revisions'][0]['before']['claim']['value']='0';p.write_bytes(h.m.encoded(r))
        meta=json.loads((self.out/'manifest.json').read_text());meta['files']['report.json']=h.m.sha(p.read_bytes());raw=h.m.encoded(meta);(self.out/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):h.verify(self.out,h.m.sha(raw))

    def test_bounds_new_output_and_symlink_inputs(self):
        with patch.object(h,'MAX_TOTAL',1),self.assertRaises(ValueError):self.build()
        link=self.inputs/'link';link.symlink_to(self.inputs/'before',target_is_directory=True);self.spec['before']['path']='link';self.save()
        with self.assertRaises(ValueError):self.build()
        self.spec['before']['path']='before';self.save();self.build()
        with self.assertRaises(FileExistsError):self.build()

    def test_cli_build_verify_and_refusal(self):
        cmd=[sys.executable,'-B',h.__file__];a=['build','--spec',str(self.spec_path),'--sha256',h.m.sha(self.spec_path.read_bytes()),'--root',str(self.inputs),'--output',str(self.out)]
        r=subprocess.run(cmd+a,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);anchor=json.loads(r.stdout)['manifest_sha256']
        r=subprocess.run(cmd+['verify','--bundle',str(self.out),'--sha256',anchor],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        r=subprocess.run(cmd+['verify','--bundle',str(self.out),'--sha256','0'*64],capture_output=True,text=True);self.assertEqual(r.returncode,2)


if __name__=='__main__':unittest.main()
