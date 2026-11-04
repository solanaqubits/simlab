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
import geek_work_claim_audit as a


class ClaimAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.mkdir();self.parent=self.root/'claims';self.out=self.root/'audit'
        self.doc='Проверка успешна.\r\nУскорение не измерено.'
        self.material='def check(x): return x == 0\r\nresult: FAIL\nvalue = 3\n<script>alert(1)</script>'
        (self.source/'paper.txt').write_bytes(self.doc.encode());(self.source/'code.txt').write_bytes(self.material.encode())
        def claim(i,q):return dict(id=i,statement=self.span('document','paper',self.doc,q),reported_evidence_state='hypothesis',scope='Toy statement',assumptions=['Exact inputs'],non_claims=['Not a scientific result'],open_obligations=['Independent review'],evidence=[])
        self.mapping=dict(schema='geek-work-manuscript-claim-map-1',documents=[dict(id='paper',path='paper.txt',sha256=a.m.sha(self.doc.encode()))],materials=[dict(id='code',path='code.txt',sha256=a.m.sha(self.material.encode()),kind='reference_material',origin=dict(repository='fixture',commit='a'*40))],claims=[claim('one','Проверка успешна.'),claim('two','Ускорение не измерено.')])
        p=self.root/'map.json';p.write_bytes(a.m.encoded(self.mapping));self.anchor=a.k.prepare(p,a.m.sha(p.read_bytes()),self.source,self.source,self.parent)['manifest_sha256']
        self.review=a.template(self.mapping,self.anchor,'fixture-reviewer');self.review['reviewer']['prior_exposure']='Synthetic test fixture.'
    @staticmethod
    def span(key,ident,text,q):
        start=text.index(q);return {key:ident,'start':start,'end':start+len(q),'quote':q}
    def comparison(self,role='check_result',q='result: FAIL'):
        return dict(role=role,citation=self.span('material','code',self.material,q),observation='Reported failure, not executed here.')
    def assessed(self):
        self.review['claims'][0].update(conclusion='contradicts',rationale='The supplied report says FAIL.',comparisons=[self.comparison()])
    def build(self):
        p=self.root/'review.json';p.write_bytes(a.m.encoded(self.review));return a.build(self.parent,self.anchor,p,a.m.sha(p.read_bytes()),self.out)
    def reseal(self):
        files={str(p.relative_to(self.out)):p.read_bytes() for p in self.out.rglob('*') if p.is_file() and p!=self.out/'manifest.json'}
        meta=a.manifest(files);(self.out/'manifest.json').write_bytes(meta);return a.m.sha(meta)
    def test_template_covers_every_claim_without_judgment(self):
        result=self.build();report=json.loads((self.out/'report.json').read_bytes())
        self.assertEqual(report['reported_conclusions'],{'not_checked':2});self.assertEqual(report['citation_count'],0)
        self.assertFalse(report['accepted_as_gold']);a.verify(self.out,result['manifest_sha256'])
    def test_conflict_and_unchecked_remain_separate(self):
        self.assessed();self.build();matrix=json.loads((self.out/'matrix.json').read_bytes())
        self.assertEqual([r['conclusion'] for r in matrix['rows']],['contradicts','not_checked'])
        row=matrix['rows'][0];self.assertEqual(row['statement'],self.mapping['claims'][0]['statement']);self.assertEqual(row['assumptions'],['Exact inputs'])
        self.assertEqual(row['comparisons_with_provenance'][0]['material_metadata'],self.mapping['materials'][0])
        self.assertEqual(row['roles_without_citations'],['reference','code','data'])
        for key in ('code_executed','semantic_correspondence_verified','independence_verified','accepted_as_gold','origin_commits_verified'):
            self.assertIs(matrix['report'][key],False)
    def test_all_conclusions_are_reported_not_inferred(self):
        for conclusion in a.CONCLUSIONS:
            with self.subTest(conclusion=conclusion):
                self.assessed();self.review['claims'][0]['conclusion']=conclusion
                if conclusion=='not_checked':self.review['claims'][0]['rationale']=None
                mapping,parent=a.parent_bytes(self.parent,self.anchor)
                files=a.derive(a.m.encoded(self.review),mapping,parent)
                self.assertFalse(json.loads(files['report.json'])['scientific_verification'])
    def test_missing_duplicate_unknown_claims_rejected(self):
        base=copy.deepcopy(self.review)
        variants=[base['claims'][:1],base['claims']+[base['claims'][0]], [{**base['claims'][0],'claim_id':'unknown'},base['claims'][1]]]
        for rows in variants:
            self.review={**base,'claims':rows}
            with self.assertRaises(ValueError):self.build()
            self.assertFalse(self.out.exists())
    def test_assessed_needs_rationale_and_citation(self):
        for rationale,comparisons in [(None,[self.comparison()]),('Reason',[]),('',[self.comparison()])]:
            self.review['claims'][0].update(conclusion='supports',rationale=rationale,comparisons=comparisons)
            with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())
    def test_not_checked_cannot_carry_hidden_verdict(self):
        self.review['claims'][0]['rationale']='It passed.'
        with self.assertRaises(ValueError):self.build()
    def test_unknown_role_and_conclusion_rejected(self):
        self.assessed();self.review['claims'][0]['comparisons'][0]['role']='verified'
        with self.assertRaises(ValueError):self.build()
        self.assessed();self.review['claims'][0]['conclusion']='accepted_as_gold'
        with self.assertRaises(ValueError):self.build()
    def test_unicode_crlf_quotes_and_boolean_offsets(self):
        self.assessed();self.review['claims'][0]['comparisons']=[self.comparison('code','def check(x): return x == 0\r\n')]
        result=self.build();a.verify(self.out,result['manifest_sha256']);shutil.rmtree(self.out)
        self.review['claims'][0]['comparisons'][0]['citation']['start']=False
        with self.assertRaises(ValueError):self.build()
    def test_bad_quote_unknown_material_and_duplicate_comparison(self):
        for change in ('quote','material','duplicate'):
            self.assessed();c=self.review['claims'][0]['comparisons'][0]
            if change=='duplicate':self.review['claims'][0]['comparisons'].append(copy.deepcopy(c))
            else:c['citation'][change]='incorrect'
            with self.assertRaises(ValueError):self.build()
    def test_html_is_escaped_and_has_no_executable_source(self):
        self.assessed();self.review['claims'][0]['comparisons']=[self.comparison('code','<script>alert(1)</script>')]
        self.review['claims'][0]['rationale']='<img src=x onerror=alert(1)>'
        self.build();page=(self.out/'index.html').read_text()
        self.assertNotIn('<script>',page);self.assertNotIn('<img',page);self.assertIn('&lt;script&gt;',page)
        self.assertIn("default-src 'none'",page);self.assertIn('<caption>',page)
    def test_independence_promotion_and_extra_fields_rejected(self):
        self.review['reviewer']['independence_verified']=True
        with self.assertRaises(ValueError):self.build()
        self.review['reviewer']['independence_verified']=False;self.review['accepted_as_gold']=True
        with self.assertRaises(ValueError):self.build()
    def test_relocation_offline_without_original(self):
        self.assessed();result=self.build();moved=self.root/'moved';shutil.move(self.out,moved);shutil.rmtree(self.source);shutil.rmtree(self.parent)
        with patch.object(subprocess,'run',side_effect=AssertionError('No executor/network')):a.verify(moved,result['manifest_sha256'])
    def test_parent_and_review_anchors_required(self):
        self.review['claim_bundle_sha256']='0'*64
        with self.assertRaises(ValueError):self.build()
        with self.assertRaises(ValueError):a.parent_bytes(self.parent,'0'*64)
        p=self.root/'review.json';p.write_bytes(a.m.encoded(self.review))
        with self.assertRaises(ValueError):a.build(self.parent,self.anchor,p,'0'*64,self.out)
    def test_resealed_matrix_status_or_html_edits_rejected(self):
        for name in ('matrix.json','report.json','index.html'):
            result=self.build();path=self.out/name;path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaises(ValueError):a.verify(self.out,self.reseal())
            shutil.rmtree(self.out)
    def test_tampered_parent_and_extra_files_rejected(self):
        result=self.build();(self.out/'claims'/'material-code.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError):a.verify(self.out,self.reseal())
        shutil.rmtree(self.out);result=self.build();(self.out/'extra').write_bytes(b'extra')
        with self.assertRaises(ValueError):a.verify(self.out,self.reseal())
    def test_symlink_existing_and_nested_output_rejected(self):
        result=self.build()
        with self.assertRaises(FileExistsError):self.build()
        review=self.root/'review.json'
        with self.assertRaises(ValueError):a.build(self.parent,self.anchor,review,a.m.sha(review.read_bytes()),self.parent/'nested')
        p=self.out/'review.json';p.unlink();p.symlink_to(review)
        with self.assertRaises(ValueError):a.verify(self.out,result['manifest_sha256'])
    def test_duplicate_json_and_bounded_rows(self):
        mapping,parent=a.parent_bytes(self.parent,self.anchor)
        with self.assertRaises(ValueError):a.derive(b'{"schema":1,"schema":2}',mapping,parent)
        self.assessed();self.review['claims'][0]['comparisons']=[self.comparison()]*17
        with self.assertRaises(ValueError):self.build()
    def test_total_archive_limit_applies_to_build_and_replay(self):
        result=self.build()
        with patch.object(a,'MAX_BUNDLE',1),self.assertRaisesRegex(ValueError,'bundle byte limit'):
            a.verify(self.out,result['manifest_sha256'])
        shutil.rmtree(self.out)
        with patch.object(a,'MAX_BUNDLE',1),self.assertRaisesRegex(ValueError,'bundle byte limit'):
            self.build()
        self.assertFalse(self.out.exists())
    def test_cli_template_build_verify_and_bad_review(self):
        tool=Path(a.__file__);out=self.root/'template'
        def run(*args):return subprocess.run([sys.executable,'-B',str(tool),*map(str,args)],capture_output=True,text=True)
        r=run('template','--bundle',self.parent,'--sha256',self.anchor,'--reviewer','fixture','--output',out);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        review=out/'review.template.json'
        r=run('build','--bundle',self.parent,'--sha256',self.anchor,'--review',review,'--review-sha256',a.m.sha(review.read_bytes()),'--output',self.out);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        anchor=json.loads(r.stdout)['manifest_sha256']
        self.assertEqual(run('verify','--bundle',self.out,'--sha256',anchor).returncode,0)
        self.assertEqual(run('verify','--bundle',self.out,'--sha256','0'*64).returncode,2)


if __name__=='__main__':unittest.main()
