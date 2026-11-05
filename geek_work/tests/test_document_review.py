import copy
from html.parser import HTMLParser
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
import geek_work_document_review as v


class DocumentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.inputs=self.root/'inputs';self.inputs.mkdir();self.output=self.root/'review';self.spec_path=self.root/'spec.json'
        self.before='Heading\nNo speed guarantee.\n';self.after='New heading\nNo speed guarantee.\n'
        self.base=self.root/'base.md';self.candidate=self.root/'candidate.md';self.base.write_text(self.before);self.candidate.write_text(self.after)
        proposal=v.h.propose(self.base,self.candidate,'paper.md','author','synthetic proposal',self.inputs/'proposal')
        self.spec=dict(schema='geek-work-document-review-1',title='Document review',proposal=dict(path='proposal',sha256=proposal['manifest_sha256']),guards=None,diagrams=[])
    def prepare(self):
        self.spec_path.write_bytes(v.m.encoded(self.spec));return v.build(self.spec_path,v.m.sha(self.spec_path.read_bytes()),self.inputs,self.output)
    def add_guards(self,proposal=None,anchor=None):
        proposal=proposal or self.inputs/'proposal';anchor=anchor or self.spec['proposal']['sha256']
        text=v.m.read(proposal/'before.txt').decode();start=text.index('No speed guarantee.')
        spec=dict(schema='geek-work-editorial-guards-1',proposal_sha256=anchor,base_sha256=v.m.sha(text.encode()),guards=[dict(id='scope',kind='non_claim',rationale='Preserve caveat',span=dict(source='before',start=start,end=start+19,quote='No speed guarantee.'))])
        path=self.root/'guards.json';path.write_bytes(v.m.encoded(spec));result=v.guards.prepare(proposal,anchor,path,v.m.sha(path.read_bytes()),self.inputs/'guards')
        self.spec['guards']=dict(path='guards',sha256=result['manifest_sha256'])
    def add_diagram(self,ident='scope'):
        source=self.root/('source-'+ident);source.mkdir();(source/'note.md').write_text('No speed guarantee.')
        quote=dict(source='note',start=0,end=19,quote='No speed guarantee.')
        spec=dict(schema='geek-work-diagram-1',id=ident,title='Scope diagram',sources=[dict(id='note',path='note.md',sha256=v.m.sha(b'No speed guarantee.'))],nodes=[dict(id='limit',label='Performance remains open',state='open',citations=[quote])],edges=[],omissions=['Other claims omitted'],merges=[])
        path=self.root/(ident+'.json');path.write_bytes(v.m.encoded(spec));result=v.diagram.build(path,v.m.sha(path.read_bytes()),source,self.inputs/ident)
        self.spec['diagrams'].append(dict(id=ident,archive=dict(path=ident,sha256=result['manifest_sha256']),selected_node_ids=['limit'],context=dict(source='before',start=8,end=27,quote='No speed guarantee.'),rationale='Declared association with the caveat'))
    def report(self):return json.loads((self.output/'report.json').read_bytes())
    def reseal(self):
        meta=json.loads((self.output/'manifest.json').read_bytes());meta['files']={name:v.m.sha((self.output/name).read_bytes()) for name in meta['files']};raw=v.m.encoded(meta);(self.output/'manifest.json').write_bytes(raw);return v.m.sha(raw)
    def test_minimal_view_stays_review_required(self):
        result=self.prepare();v.verify(self.output,result['manifest_sha256']);r=self.report()
        self.assertEqual(r['missing_optional_views'],['guard_review','diagram']);self.assertFalse(r['proposal_guard_chain_consistent'])
        self.assertEqual(r['status'],'review_required');self.assertEqual(r['hunk_ids'],['h001'])
    def test_full_view_binds_same_proposal_and_selected_nodes(self):
        self.add_guards();self.add_diagram();result=self.prepare();v.verify(self.output,result['manifest_sha256']);r=self.report()
        self.assertTrue(r['proposal_guard_chain_consistent']);self.assertEqual(r['missing_optional_views'],[])
        self.assertFalse(r['diagrams'][0]['relationship_verified']);self.assertFalse(r['scientific_verification']);self.assertFalse(r['live_document_checked'])
    def test_guard_from_other_proposal_refused_even_with_same_document_bytes(self):
        other=self.root/'other';result=v.h.propose(self.base,self.candidate,'paper.md','different author','different provenance',other)
        self.add_guards(other,result['manifest_sha256'])
        with self.assertRaisesRegex(ValueError,'CHAIN_MISMATCH'):self.prepare()
    def test_missing_selected_diagram_node(self):
        self.add_diagram();self.spec['diagrams'][0]['selected_node_ids']=['invented']
        with self.assertRaises(ValueError):self.prepare()
    def test_diagram_context_must_match_selected_version(self):
        self.add_diagram();self.spec['diagrams'][0]['context']['source']='after'
        with self.assertRaises(ValueError):self.prepare()
        self.spec['diagrams'][0]['context'].update(start=12,end=31)
        self.prepare();self.assertEqual(self.report()['diagrams'][0]['context']['source'],'after')
    def test_wrong_context_quote_or_boolean_offsets(self):
        self.add_diagram();original=copy.deepcopy(self.spec)
        for update in ({'quote':'invented'},{'start':True},{'source':'live'}):
            self.spec=copy.deepcopy(original);self.spec['diagrams'][0]['context'].update(update)
            with self.assertRaises(ValueError):self.prepare()
    def test_duplicate_diagram_and_selected_node(self):
        self.add_diagram();self.spec['diagrams']*=2
        with self.assertRaises(ValueError):self.prepare()
        self.spec['diagrams'].pop();self.spec['diagrams'][0]['selected_node_ids']*=2
        with self.assertRaises(ValueError):self.prepare()
    def test_overlapping_paths_and_case_collisions(self):
        self.add_diagram()
        for path in ('proposal','Proposal','proposal/nested'):
            self.spec['diagrams'][0]['archive']['path']=path
            with self.assertRaises(ValueError):self.prepare()
    def test_path_traversal_and_directory_symlink(self):
        self.spec['proposal']['path']='../outside'
        with self.assertRaises(ValueError):self.prepare()
        (self.inputs/'link').symlink_to(self.inputs/'proposal',target_is_directory=True);self.spec['proposal']['path']='link'
        with self.assertRaises(ValueError):self.prepare()
    def test_wrong_nested_or_outer_anchor(self):
        old=self.spec['proposal']['sha256'];self.spec['proposal']['sha256']='0'*64
        with self.assertRaises(ValueError):self.prepare()
        self.spec['proposal']['sha256']=old;self.spec_path.write_bytes(v.m.encoded(self.spec))
        with self.assertRaises(ValueError):v.build(self.spec_path,'0'*64,self.inputs,self.output)
    def test_tampered_guard_report_refused(self):
        self.add_guards();(self.inputs/'guards/report.json').write_text('{}')
        with self.assertRaises(ValueError):self.prepare()
    def test_tampered_diagram_refused(self):
        self.add_diagram();(self.inputs/'scope/diagram.svg').write_text('<svg/>')
        with self.assertRaises(ValueError):self.prepare()
    def test_resealed_composite_html_or_report_refused(self):
        self.prepare()
        for name in ('index.html','report.json'):
            old=(self.output/name).read_bytes();(self.output/name).write_bytes(old+b' ')
            with self.assertRaises(ValueError):v.verify(self.output,self.reseal())
            (self.output/name).write_bytes(old)
    def test_extra_missing_files_and_output_refusal(self):
        result=self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()
        (self.output/'extra').write_text('x')
        with self.assertRaises(ValueError):v.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').unlink();(self.output/'inputs/proposal/after.txt').unlink()
        with self.assertRaises(ValueError):v.verify(self.output,result['manifest_sha256'])
    def test_output_must_be_disjoint(self):
        self.output=self.inputs/'review'
        with self.assertRaises(ValueError):self.prepare()
    def test_resource_limits(self):
        with patch.object(v,'MAX_BYTES',1),self.assertRaises(ValueError):self.prepare()
        with patch.object(v,'MAX_FILES',1),self.assertRaises(ValueError):self.prepare()
        self.add_diagram();self.spec['diagrams']*=5
        with self.assertRaises(ValueError):self.prepare()
    def test_no_source_modifications(self):
        self.add_guards();self.add_diagram();before={p.relative_to(self.inputs):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()}
        self.prepare();after={p.relative_to(self.inputs):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()};self.assertEqual(before,after)
    def test_html_escaping_and_csp(self):
        self.add_diagram();self.spec['title']='<script>boom</script>';self.spec['diagrams'][0]['rationale']='<img src=x onerror=boom>'
        self.prepare();page=(self.output/'index.html').read_text();self.assertNotIn('<script>',page);self.assertNotIn('<img src=x',page);self.assertIn('&lt;img src=x',page);self.assertIn("default-src 'none'",page)
    def test_every_local_navigation_link_resolves(self):
        self.add_guards();self.add_diagram();self.prepare()
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.links=[];self.ids=set()
            def handle_starttag(self,tag,attrs):
                attr=dict(attrs)
                if 'id' in attr:self.ids.add(attr['id'])
                if tag=='a' and 'href' in attr:self.links.append(attr['href'])
                if tag=='img' and 'src' in attr:self.links.append(attr['src'])
        for page in self.output.rglob('*.html'):
            parser=Links();parser.feed(page.read_text())
            for link in parser.links:
                if link.startswith('#'):self.assertIn(link[1:],parser.ids)
                else:
                    self.assertNotIn('://',link);target=(page.parent/link).resolve();self.assertTrue(target.is_relative_to(self.output.resolve()));self.assertTrue(target.is_file(),link)
    def test_relocation_offline_cli_without_inputs(self):
        self.add_guards();self.add_diagram();result=self.prepare();moved=self.root/'moved';shutil.copytree(self.output,moved);shutil.rmtree(self.inputs);self.spec_path.unlink()
        cmd=[sys.executable,'-B',v.__file__,'verify','--bundle',str(moved),'--sha256',result['manifest_sha256']]
        run=subprocess.run(cmd,capture_output=True,text=True,env={**os.environ,'PATH':''});self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['review_disposition'],'review_required');cmd[-1]='0'*64;self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
    def test_duplicate_json_and_unknown_fields(self):
        self.spec['accepted']=True
        with self.assertRaises(ValueError):self.prepare()
        del self.spec['accepted'];raw=v.m.encoded(self.spec).replace(b'"diagrams": []',b'"diagrams": [], "diagrams": []');self.spec_path.write_bytes(raw)
        with self.assertRaises(ValueError):v.build(self.spec_path,v.m.sha(raw),self.inputs,self.output)
    def test_diagram_attachment_order_and_reported_counts(self):
        self.add_diagram('second');self.add_diagram('first');self.prepare();r=self.report()
        self.assertEqual([x['id'] for x in r['diagrams']],['second','first']);self.assertEqual([x['node_count'] for x in r['diagrams']],[1,1])


if __name__=='__main__':unittest.main()
