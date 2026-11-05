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
import geek_work_experiment_tree as t


class ExperimentTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.inputs=self.root/'inputs';self.inputs.mkdir();self.source=self.root/'source';self.source.mkdir()
        (self.source/'code.txt').write_text('INERT code; do not execute\n');(self.source/'data.json').write_text('{"x":2}\n')
        self.plan=t.experiment.plan_template();self.plan.update(id='baseline-plan',title='Baseline',hypothesis='Synthetic hypothesis',readiness='ready_for_protocol_review')
        self.plan['sources']=[dict(id='code',path='code.txt',sha256=t.m.sha((self.source/'code.txt').read_bytes()),role='code')]
        self.ref=self.freeze('baseline',self.plan)
        self.spec=dict(schema='geek-work-experiment-tree-1',id='fixture',title='Synthetic tree',nodes=[self.node('base',None,self.ref)])
        self.spec_path=self.root/'spec.json';self.output=self.root/'tree'
    def freeze(self,name,plan):
        path=self.root/(name+'.json');path.write_bytes(t.m.encoded(plan))
        result=t.experiment.capture('plan',path,t.m.sha(path.read_bytes()),self.source,self.inputs/name)
        return dict(path=name,sha256=result['manifest_sha256'])
    def node(self,ident,parent,plan):return dict(id=ident,parent=parent,builds_on=None if parent is None else 'Declared inheritance only',plan=copy.deepcopy(plan),ledger=None,claim_maps=[])
    def child(self,ident='child'):
        plan=copy.deepcopy(self.plan);plan.update(id=ident,title=ident);plan['parameters']={'step':2}
        ref=self.freeze(ident,plan);node=self.node(ident,'base',ref);self.spec['nodes'].append(node);return node
    def ledger(self,node,outcome='rejected',cost=None,task_id='fixture-task',attempts=2):
        entries=[dict(attempt_id=i+1,model_profile=None,model_transition='initial' if i==0 else 'unknown',token_usage=None,
                 monetary_cost=cost,verification_wall_time_ms=None,failure_classes=['synthetic_failure'],human_interventions=None) for i in range(attempts)]
        task=dict(task_id=task_id,outcome=outcome,attempts_count=len(entries),attempts=entries,
                  acceptance=None if outcome=='rejected' else dict(kind='machine_check',evidence=[dict(path='unresolved.json',sha256='0'*64)]))
        doc=dict(schema='geek-work-ledger-1',currency='USD',cost_scope='attempt_including_verification',tasks=[task])
        path=self.inputs/(node['id']+'-ledger.json');path.write_bytes(t.m.encoded(doc))
        node['ledger']=dict(path=path.name,sha256=t.m.sha(path.read_bytes()),task_id=task_id);return doc,path
    def build(self):
        self.spec_path.write_bytes(t.m.encoded(self.spec));return t.build(self.spec_path,t.m.sha(self.spec_path.read_bytes()),self.inputs,self.output)
    def report(self):return json.loads((self.output/'report.json').read_bytes())
    def reseal(self):
        manifest=json.loads((self.output/'manifest.json').read_bytes())
        manifest['files']={p:t.m.sha((self.output/p).read_bytes()) for p in manifest['files']}
        raw=t.m.encoded(manifest);(self.output/'manifest.json').write_bytes(raw);return t.m.sha(raw)

    def test_plan_only_is_not_run(self):
        result=self.build();t.verify(self.output,result['manifest_sha256']);r=self.report();n=r['nodes'][0]
        self.assertEqual(n['state'],'plan_only');self.assertEqual(n['reported_attempts'],[])
        self.assertFalse(n['execution_verified']);self.assertFalse(r['budget_enforced']);self.assertFalse(r['chronology_verified'])
    def test_hierarchy_siblings_depth_and_changed_fields(self):
        a=self.child('a');b=self.child('b');self.spec['nodes'].reverse();self.build();nodes=self.report()['nodes']
        self.assertEqual([x['id'] for x in nodes],['base','a','b']);self.assertEqual([x['depth'] for x in nodes],[0,1,1])
        self.assertIn('parameters',nodes[1]['changed_plan_fields']);self.assertFalse(nodes[1]['inheritance_verified'])
    def test_failed_attempts_and_unknown_costs_remain(self):
        self.ledger(self.spec['nodes'][0]);self.build();r=self.report();n=r['nodes'][0];summary=r['reported_ledger_summary']['by_currency']['USD']
        self.assertEqual(len(n['reported_attempts']),2);self.assertEqual(n['reported_task_outcome'],'rejected')
        self.assertTrue(n['reported_attempts_exceed_declared_limit']);self.assertIsNone(summary['total_cost']);self.assertIsNone(summary['cost_per_accepted_result'])
    def test_accepted_ledger_does_not_certify_science_or_evidence(self):
        self.ledger(self.spec['nodes'][0],outcome='accepted',cost='0.10');self.build();r=self.report();n=r['nodes'][0]
        self.assertEqual(n['reported_task_outcome'],'accepted');self.assertFalse(n['scientific_verification']);self.assertFalse(n['acceptance_evidence_verified'])
        self.assertEqual(r['reported_ledger_summary']['by_currency']['USD']['cost_per_accepted_result'],'0.20')
    def test_ledger_all_selected_task_attempts_retained(self):
        doc,_=self.ledger(self.spec['nodes'][0],attempts=3);self.build()
        self.assertEqual(self.report()['nodes'][0]['reported_attempts'],doc['tasks'][0]['attempts'])
    def test_duplicate_task_across_nodes_refused(self):
        child=self.child();self.ledger(self.spec['nodes'][0]);child['ledger']=copy.deepcopy(self.spec['nodes'][0]['ledger'])
        with self.assertRaises(ValueError):self.build()
    def test_duplicate_task_id_across_distinct_ledgers_refused(self):
        child=self.child();self.ledger(self.spec['nodes'][0]);self.ledger(child,cost='1')
        with self.assertRaises(ValueError):self.build()
    def test_missing_task_and_bad_attempt_sequence_refused(self):
        doc,path=self.ledger(self.spec['nodes'][0]);self.spec['nodes'][0]['ledger']['task_id']='absent'
        with self.assertRaises(ValueError):self.build()
        self.spec['nodes'][0]['ledger']['task_id']='fixture-task';doc['tasks'][0]['attempts'][0]['attempt_id']=9
        path.write_bytes(t.m.encoded(doc));self.spec['nodes'][0]['ledger']['sha256']=t.m.sha(path.read_bytes())
        with self.assertRaises(ValueError):self.build()
    def test_cycles_missing_parent_and_multiple_roots_refused(self):
        self.child()
        for parent in ['child','missing',None]:
            spec=copy.deepcopy(self.spec);spec['nodes'][1]['parent']=parent
            if parent is None:spec['nodes'][1]['builds_on']=None
            with self.subTest(parent=parent),self.assertRaises(ValueError):t.validate(spec)
        self.spec['nodes'][0]['parent']='child';self.spec['nodes'][0]['builds_on']='cycle'
        with self.assertRaises(ValueError):t.validate(self.spec)
    def test_duplicate_node_and_empty_inheritance_refused(self):
        self.spec['nodes'].append(copy.deepcopy(self.spec['nodes'][0]))
        with self.assertRaises(ValueError):t.validate(self.spec)
        self.spec['nodes'].pop();self.child()['builds_on']=''
        with self.assertRaises(ValueError):t.validate(self.spec)
    def test_limits_nodes_snapshots_and_attempts(self):
        self.child()
        with patch.object(t,'MAX_NODES',1),self.assertRaises(ValueError):self.build()
        with patch.object(t,'MAX_TOTAL',10),self.assertRaises(ValueError):self.build()
        self.assertFalse(self.output.exists())
        self.ledger(self.spec['nodes'][0],attempts=129)
        with self.assertRaises(ValueError):self.build()
    def test_wrong_plan_anchor_and_wrong_archive_kind_refused(self):
        self.spec['nodes'][0]['plan']['sha256']='0'*64
        with self.assertRaises(ValueError):self.build()
        self.spec['nodes'][0]['plan']=copy.deepcopy(self.ref);self.spec['nodes'][0]['claim_maps']=[dict(path='baseline-copy',sha256=self.ref['sha256'])]
        shutil.copytree(self.inputs/'baseline',self.inputs/'baseline-copy')
        with self.assertRaises(ValueError):self.build()
    def test_numeric_mismatch_is_visible_without_promoting_node(self):
        spec=dict(schema='geek-work-numeric-claims-1',id='numbers',sources=[dict(id='data',path='data.json',sha256=t.m.sha((self.source/'data.json').read_bytes()),role='data')],claims=[dict(id='x',statement='Synthetic',value='3',unit='unspecified',uncertainty=None,operation='identity',operands=[dict(source_id='data',selector={'json_pointer':'/x'})])])
        path=self.root/'map.json';path.write_bytes(t.m.encoded(spec));result=t.experiment.capture('claims',path,t.m.sha(path.read_bytes()),self.source,self.inputs/'map')
        self.spec['nodes'][0]['claim_maps']=[dict(path='map',sha256=result['manifest_sha256'])];self.build();node=self.report()['nodes'][0]
        self.assertEqual(node['state'],'plan_only');self.assertEqual(node['claim_maps'][0]['report']['status'],'numeric_map_mismatch');self.assertFalse(node['map_plan_conformance_verified'])
    def test_traversal_symlink_and_prefix_collision_refused(self):
        self.spec['nodes'][0]['plan']['path']='../escape'
        with self.assertRaises(ValueError):self.build()
        self.spec['nodes'][0]['plan']=copy.deepcopy(self.ref);node=self.child();node['plan']['path']='baseline/nested'
        with self.assertRaises(ValueError):self.build()
        node['plan']['path']='linked';(self.inputs/'linked').symlink_to(self.inputs/'child')
        with self.assertRaises(ValueError):self.build()
    def test_inputs_unchanged_and_output_disjoint(self):
        before={str(p.relative_to(self.inputs)):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()};self.build()
        after={str(p.relative_to(self.inputs)):p.read_bytes() for p in self.inputs.rglob('*') if p.is_file()};self.assertEqual(before,after)
        self.output=self.inputs/'nested'
        with self.assertRaises(ValueError):self.build()
    def test_existing_output_and_partial_archive_refused(self):
        result=self.build()
        with self.assertRaises(ValueError):self.build()
        (self.output/'index.html').unlink()
        with self.assertRaises(ValueError):t.verify(self.output,result['manifest_sha256'])
    def test_resealed_scientific_promotion_or_html_change_refused(self):
        self.build();p=self.output/'report.json';r=self.report();r['scientific_verification']=True;p.write_bytes(t.m.encoded(r))
        with self.assertRaises(ValueError):t.verify(self.output,self.reseal())
    def test_resealed_preview_change_refused(self):
        self.build();(self.output/'index.html').write_text('<html>wrong</html>')
        with self.assertRaises(ValueError):t.verify(self.output,self.reseal())
    def test_unknown_status_or_attempt_field_not_accepted_in_spec(self):
        self.spec['nodes'][0]['verified']=True
        with self.assertRaises(ValueError):self.build()
    def test_html_is_offline_escaped_and_has_actual_tree(self):
        self.spec['title']='<script>alert(1)</script>';self.child();self.build();page=(self.output/'index.html').read_text()
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page);self.assertIn('href="#child"',page)
        self.assertIn("default-src 'none'",page);self.assertNotIn('fonts.googleapis',page)
    def test_offline_relocation_after_removing_sources(self):
        self.child();self.ledger(self.spec['nodes'][1]);result=self.build();moved=self.root/'moved';shutil.move(self.output,moved)
        shutil.rmtree(self.inputs);shutil.rmtree(self.source);self.spec_path.unlink()
        with patch.object(subprocess,'run',side_effect=AssertionError('no execution')):t.verify(moved,result['manifest_sha256'])
        p=subprocess.run([sys.executable,'-B',t.__file__,'verify','--bundle',str(moved),'--sha256',result['manifest_sha256']],capture_output=True,env=dict(os.environ,PATH=''),timeout=15)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['status'],'tree_integrity_reproduced')
    def test_extra_file_and_missing_ledger_never_skip_evidence(self):
        self.ledger(self.spec['nodes'][0]);result=self.build();(self.output/'extra').write_text('x')
        with self.assertRaises(ValueError):t.verify(self.output,result['manifest_sha256'])
        (self.output/'extra').unlink();(self.output/'inputs/base-ledger.json').unlink()
        with self.assertRaises(ValueError):t.verify(self.output,result['manifest_sha256'])


    def test_currencies_remain_separate_and_partial_cost_stays_unknown(self):
        child=self.child();self.ledger(self.spec['nodes'][0],cost='1.00',task_id='usd')
        doc,path=self.ledger(child,task_id='eur');doc['currency']='EUR'
        doc['tasks'][0]['attempts'][0]['monetary_cost']='2.00'
        path.write_bytes(t.m.encoded(doc));child['ledger']['sha256']=t.m.sha(path.read_bytes())
        self.build();groups=self.report()['reported_ledger_summary']['by_currency']
        self.assertEqual(set(groups),{'USD','EUR'});self.assertEqual(groups['USD']['total_cost'],'2.00')
        self.assertIsNone(groups['EUR']['total_cost']);self.assertEqual(groups['EUR']['known_cost_total'],'2.00')
    def test_shared_plan_is_copied_once_with_separate_nodes(self):
        self.spec['nodes'].append(self.node('child','base',self.ref));self.build()
        manifest=json.loads((self.output/'manifest.json').read_bytes())
        self.assertEqual(len([p for p in manifest['files'] if p.endswith('/manifest.json')]),1)
        self.assertEqual(len(self.report()['nodes']),2)


if __name__=='__main__':unittest.main()
