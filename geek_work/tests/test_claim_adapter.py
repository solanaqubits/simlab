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
import geek_work_claim_adapter as a

ROOT=Path(__file__).resolve().parents[2]
READY=ROOT/'geek_work/examples/claim-adapter-ready'
ORBIT=ROOT/'geek_work/examples/claim-extraction-orbit'


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=(READY/'source.txt').read_bytes()
        self.record=json.loads((READY/'record.json').read_bytes())
        self.expected_raw=(READY/'expectations.json').read_bytes()
        self.pins=json.loads((READY/'pins.json').read_bytes())
        self.bundle=READY/'source-bundle'

    def build(self, **kw):
        artifacts=a.build(kw.get('source',self.source),kw.get('source_sha',self.pins['source_sha256']),
            kw.get('expected_raw',self.expected_raw),kw.get('expected_sha',self.pins['expectations_sha256']),
            kw.get('record_raw',a.m.encoded(self.record)),kw.get('bundle',self.bundle),
            kw.get('bundle_sha',self.pins['claim_map_bundle_sha256']),kw.get('claim_id','synthetic-balance'),kw.get('revision',1))
        for name,raw in artifacts.items():
            if name.endswith('report.json'):
                value=json.loads(raw)
                for flag in a.FLAGS:self.assertIs(value[flag],False)
        r=json.loads(artifacts['adapter-report.json'])
        if r['status']!='built':
            self.assertNotIn('plan.json',artifacts);self.assertNotIn('candidate.json',artifacts)
        return r,artifacts

    def repin_editorial(self):
        expected={k:copy.deepcopy(self.record[k]) for k in a.extraction.COMMON.split()}
        expected['schema']='geek-work-claim-extraction-expectations-1'
        self.expected_raw=a.m.encoded(expected)
        self.pins['expectations_sha256']=a.m.sha(self.expected_raw)

    def changed_bundle(self, change):
        mapping=json.loads((READY/'source-bundle/map.json').read_bytes())
        change(mapping)
        path=self.root/'map.json';path.write_bytes(a.m.encoded(mapping))
        target=self.root/'bundle'
        receipt=a.c.prepare(path,a.m.sha(path.read_bytes()),READY,READY,target)
        self.bundle=target;self.pins['claim_map_bundle_sha256']=receipt['manifest_sha256']
        return mapping

    def test_adapter_success_ready_fixture(self):
        r,files=self.build();self.assertEqual(r['status'],'built',r)
        self.assertEqual(r['transport_status'],'contract_preserved')
        for name,raw in files.items():self.assertEqual(raw,(READY/'expected-package'/name).read_bytes())
        candidate=json.loads(files['candidate.json'])['cards'][0]['contract']
        for role in a.transport.ROLES:
            self.assertEqual(len(candidate[role]),len(self.record['contract'][role]))
        self.assertEqual(candidate['quantities'][0]['unit'],'credits')
        self.assertEqual(candidate['open_obligations'],self.record['contract']['open_obligations'])
        replay=a.transport.check(self.bundle,self.pins['claim_map_bundle_sha256'],files['plan.json'],r['plan_sha256'],files['candidate.json'])
        self.assertEqual(replay['status'],'contract_preserved')

    def test_adapter_reject_orbit_needs_context(self):
        pins=json.loads((ORBIT/'pins.json').read_bytes())
        r,files=self.build(source=(ROOT/pins['source_path'].replace('digital-brain/', 'geek_work/')).read_bytes(),source_sha=pins['source_sha256'],
            expected_raw=(ORBIT/'expectations.json').read_bytes(),expected_sha=pins['expectations_sha256'],
            record_raw=(ORBIT/'orbit-needs-context.json').read_bytes(),claim_id='subcritical-orbit-limit',
            bundle=ROOT/'geek_work/examples/claim-transport-orbit/source-bundle',
            bundle_sha='022bbbc4659daa6cb249aed9bdb8dc8a90c85f7fb9bd828ab53964458398281b')
        self.assertEqual(r['status'],'build_blocked');self.assertEqual(r['extraction_status'],'needs_context')
        self.assertEqual(json.loads(files['extraction-report.json'])['atom_binding_count'],8)

    def test_adapter_reject_stale_or_bypassed_report(self):
        saved=(READY/'expected-package/extraction-report.json').read_bytes()
        self.record['contract']['premise_atoms'][0]['text_raw']='Changed text'
        r,_=self.build();self.assertEqual(r['status'],'invalid_input')
        r,_=self.build(record_raw=saved);self.assertEqual(r['status'],'invalid_input')
        self.assertNotIn('saved_report',__import__('inspect').signature(a.build).parameters)

    def test_adapter_reject_ledger_hash_mismatch(self):
        r,_=self.build(expected_raw=self.expected_raw+b' ')
        self.assertEqual(r['status'],'invalid_input')
        self.assertEqual(r['extraction_reason'],'external_expectations_hash_mismatch')

    def test_adapter_reject_atom_loss_or_unmapped(self):
        self.record['contract']['premise_atoms']=[]
        self.record['coverage_checks']=[r for r in self.record['coverage_checks'] if r['expected_role']!='premise_atoms']
        r,_=self.build();self.assertEqual(r['status'],'build_blocked')
        self.assertEqual(r['extraction_status'],'review_required')

    def test_adapter_reject_claim_map_inconsistency(self):
        self.changed_bundle(lambda m:m['claims'][0].update(scope='A different scope'))
        r,_=self.build();self.assertEqual(r['status'],'build_blocked')
        self.assertIn('claim_map_inconsistent',r['reason'])

    def test_wrong_role_does_not_disappear(self):
        self.record['contract']['negation_atoms']=[]
        self.record['coverage_checks']=[r for r in self.record['coverage_checks'] if r['expected_role']!='negation_atoms']
        r,_=self.build();self.assertEqual(r['status'],'build_blocked')

    def test_same_id_rebinding_invalid(self):
        row=copy.deepcopy(self.record['contract']['conclusion_atoms'][0]);row['atom_id']='nonnegative-index'
        self.record['contract']['premise_atoms']=[row]
        r,_=self.build();self.assertEqual(r['status'],'invalid_input');self.assertEqual(r['extraction_reason'],'atom_id_rebinding')

    def test_draft_consistent_is_not_admitted(self):
        self.record['editorial_state']='draft'
        r,_=self.build();self.assertEqual(r['reason'],'editorial_state_not_ready')

    def test_closed_questions_still_block_adapter(self):
        self.record['unresolved_questions']=[dict(item_id='old-question',description='Previously resolved fixture question',required_before_transport=True,resolution='Resolved in a prior editorial review.')]
        self.repin_editorial()
        r,files=self.build();self.assertEqual(json.loads(files['extraction-report.json'])['status'],'record_consistent')
        self.assertEqual(r['reason'],'unresolved_questions_not_empty')

    def test_optional_questions_still_block_adapter(self):
        self.record['unresolved_questions']=[dict(item_id='optional-question',description='Optional pending question',required_before_transport=False,resolution=None)]
        self.repin_editorial();r,_=self.build();self.assertEqual(r['reason'],'unresolved_questions_not_empty')

    def test_unknown_remains_unknown_with_independently_ready_fixture(self):
        q=self.record['contract']['quantities'][0]
        q.update(unit_raw=None,unit_span=None,unit_interpretation='unknown')
        self.repin_editorial();r,files=self.build();self.assertEqual(r['status'],'built')
        self.assertEqual(json.loads(files['candidate.json'])['cards'][0]['contract']['quantities'][0]['unit'],'unknown')

    def test_ambiguous_unit_mapping_blocks(self):
        self.record['contract']['quantities'][0]['unit_canonical']='seconds'
        self.repin_editorial();r,_=self.build();self.assertEqual(r['reason'],'unit_mapping_ambiguous')

    def test_mapped_unit_requires_explicit_canonical_value(self):
        q=self.record['contract']['quantities'][0]
        q.update(unit_interpretation='mapped',unit_mapping_basis='Synthetic editor mapping declaration; no physical equivalence proof.')
        self.repin_editorial();r,_=self.build();self.assertEqual(r['reason'],'unit_mapping_ambiguous')
        q['unit_canonical']='compute_credit';self.repin_editorial()
        r,files=self.build();self.assertEqual(r['status'],'built')
        self.assertEqual(json.loads(files['candidate.json'])['cards'][0]['contract']['quantities'][0]['unit'],'compute_credit')

    def test_dimensionless_is_never_inferred(self):
        q=self.record['contract']['quantities'][0]
        q.update(unit_raw=None,unit_span=None,unit_interpretation='dimensionless',unit_mapping_basis='Explicit pinned synthetic editorial annotation.')
        self.repin_editorial();r,files=self.build();self.assertEqual(r['status'],'built')
        self.assertEqual(json.loads(files['candidate.json'])['cards'][0]['contract']['quantities'][0]['unit'],'dimensionless')

    def test_bundle_pin_mismatch(self):
        r,_=self.build(bundle_sha='0'*64);self.assertEqual(r['status'],'invalid_input')

    def test_bundle_tampering_rejected(self):
        target=self.root/'corrupt';shutil.copytree(self.bundle,target)
        with (target/'document-source.txt').open('ab') as f:f.write(b' ')
        r,_=self.build(bundle=target);self.assertEqual(r['status'],'invalid_input')

    def test_source_pin_mismatch(self):
        r,_=self.build(source=self.source+b' ');self.assertEqual(r['extraction_reason'],'external_source_hash_mismatch')

    def test_unrelated_source_with_same_quote_is_not_bound(self):
        changed=self.source+b'additional unrelated context'
        self.record['source_snapshot']['sha256']=a.m.sha(changed);self.repin_editorial()
        r,_=self.build(source=changed,source_sha=a.m.sha(changed))
        self.assertEqual(r['reason'],'source_not_bound_to_selected_claim')

    def test_wrong_claim_selection(self):
        r,_=self.build(claim_id='missing-claim');self.assertEqual(r['reason'],'source_claim_not_found')

    def test_source_revision_rejects_boolean_and_zero(self):
        for revision in (True,0,-1):
            with self.subTest(revision=revision):
                r,_=self.build(revision=revision);self.assertEqual(r['status'],'invalid_input')

    def test_pinned_nonclaims_mismatch_not_silently_replaced(self):
        self.record['contract']['non_claims']=[];self.repin_editorial()
        r,_=self.build();self.assertIn('non_claim',r['reason'])

    def test_pinned_evidence_state_mismatch_not_silently_replaced(self):
        self.record['reported_evidence_state']='source_only';self.repin_editorial()
        r,_=self.build();self.assertIn('evidence_state_changed',r['reason'])

    def test_pinned_premise_loss_rejected_by_claim_map(self):
        self.record['contract']['premise_atoms']=[]
        self.record['coverage_checks']=[r for r in self.record['coverage_checks'] if r['expected_role']!='premise_atoms']
        self.repin_editorial();r,_=self.build();self.assertIn('claim_map_inconsistent',r['reason'])

    def test_oversized_inputs_do_not_produce_plan(self):
        r,_=self.build(record_raw=b' '*(a.MAX_BYTES+1));self.assertEqual(r['status'],'invalid_input')

    def test_extra_fields_and_assurance_promotion(self):
        self.record['prechecked_report']={'status':'record_consistent'}
        r,_=self.build();self.assertEqual(r['status'],'invalid_input')
        del self.record['prechecked_report'];self.record['assurances']['kernel_replayed']=True
        r,_=self.build();self.assertEqual(r['status'],'invalid_input')

    def test_transport_failure_no_build_artifacts(self):
        with patch.object(a.transport,'check',return_value=a.transport.report('review_required')) as check:
            r,files=self.build();self.assertEqual(r['reason'],'transport_did_not_preserve_contract')
            check.assert_called_once();self.assertIn('transport-report.json',files)

    def test_material_bridge(self):
        # Use a pinned evidence material as source, with a separate signature document.
        source_path=self.root/'source.txt';source_path.write_bytes(self.source)
        selected=self.record['selected_span'];(self.root/'signature.txt').write_bytes(selected['quote'].encode())
        material=dict(id='original',path='source.txt',sha256=a.m.sha(self.source),kind='reference_material',origin=dict(repository='Synthetic fixture',commit='0'*40))
        evidence=dict(citation=dict(material='original',start=selected['start_char'],end=selected['end_char'],quote=selected['quote']),declaration=None)
        mapping=json.loads((self.bundle/'map.json').read_bytes())
        mapping['documents']=[dict(id='signature',path='signature.txt',sha256=a.m.sha(selected['quote'].encode()))]
        mapping['materials']=[material]
        mapping['claims'][0]['statement']=dict(document='signature',start=0,end=len(selected['quote']),quote=selected['quote'])
        mapping['claims'][0]['evidence']=[evidence]
        self.record['contract']['evidence_ids']=[a.m.sha(a.m.encoded(dict(binding=evidence,material=material)))];self.repin_editorial()
        mp=self.root/'map.json';mp.write_bytes(a.m.encoded(mapping));self.bundle=self.root/'material-bundle'
        self.pins['claim_map_bundle_sha256']=a.c.prepare(mp,a.m.sha(mp.read_bytes()),self.root,self.root,self.bundle)['manifest_sha256']
        r,_=self.build();self.assertEqual(r['status'],'built');self.assertEqual(r['source_binding']['kind'],'material')
        self.record['source_snapshot']['commit']='1'*40;self.repin_editorial()
        r,_=self.build();self.assertEqual(r['reason'],'source_not_bound_to_selected_claim')

    def cli(self, output):
        return [sys.executable,'-B',str(ROOT/'geek_work/tools/geek_work_claim_adapter.py'),
            '--source-snapshot',str(READY/'source.txt'),'--source-sha256',self.pins['source_sha256'],
            '--expectations',str(READY/'expectations.json'),'--expectations-sha256',self.pins['expectations_sha256'],
            '--record',str(READY/'record.json'),'--claim-map-bundle',str(self.bundle),
            '--claim-map-bundle-sha256',self.pins['claim_map_bundle_sha256'],
            '--source-claim-id','synthetic-balance','--source-revision','1','--output',str(output)]

    def test_cli_package_byte_replay_and_exclusive_output(self):
        out=self.root/'output';cmd=self.cli(out)
        result=subprocess.run(cmd,capture_output=True,timeout=10);self.assertEqual(result.returncode,0,result.stderr)
        for path in (READY/'expected-package').iterdir():self.assertEqual(path.read_bytes(),(out/path.name).read_bytes())
        manifest=(out/'manifest.json').read_bytes()
        again=subprocess.run(cmd,capture_output=True,timeout=10);self.assertNotEqual(again.returncode,0)
        self.assertEqual((out/'manifest.json').read_bytes(),manifest)

    def test_cli_does_not_accept_saved_report_argument(self):
        out=self.root/'out';cmd=self.cli(out)+['--extraction-report','fake.json']
        result=subprocess.run(cmd,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertFalse(out.exists())

    def test_cli_unsafe_file_and_invalid_pins_emit_false_receipt(self):
        for name in ('symlink','fifo','bad-pin'):
            cmd=self.cli(self.root/(name+'-out'))
            if name=='bad-pin':cmd[cmd.index('--source-sha256')+1]='0'*64
            else:
                p=self.root/name
                if name=='symlink':p.symlink_to(READY/'record.json')
                else:os.mkfifo(p)
                cmd[cmd.index('--record')+1]=str(p)
            result=subprocess.run(cmd,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,2,result.stderr)
            body=json.loads((Path(cmd[-1])/'adapter-report.json').read_bytes())
            self.assertTrue(all(body[f] is False for f in a.FLAGS));self.assertEqual(body['status'],'invalid_input')


if __name__=='__main__':unittest.main()
