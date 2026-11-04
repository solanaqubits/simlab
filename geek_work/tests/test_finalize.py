import copy
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import chat_intake as intake
import geek_work as gw
import geek_work_finalize as tx
import geek_work_ledger as costs
sys.path.pop(0)


def put(path, doc):
    path.write_bytes(tx.encoded(doc))


def task(tid='t1', outcome='rejected', amount='0.25'):
    return dict(task_id=tid, outcome=outcome, attempts_count=1, acceptance=None, attempts=[dict(
        attempt_id=1, model_profile=None, model_transition='initial', token_usage=None,
        monetary_cost=amount, verification_wall_time_ms=None,
        failure_classes=['incorrect_sha'] if outcome == 'rejected' else [], human_interventions=None)])


def ledger(tasks):
    return dict(schema='geek-work-ledger-1', currency='USD',
                cost_scope='attempt_including_verification', tasks=tasks)


def crash_worker(registry, request, phase):
    tx.checkpoint = lambda reached: os._exit(73) if reached == phase else None
    tx.finalize(Path(registry), request)


def race_worker(registry, request, event, results):
    event.wait()
    try: results.put(tx.finalize(Path(registry), request)['status'])
    except tx.FinalizeError as e: results.put(e.code)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name); self.src = self.p / 'src'; self.src.mkdir()
        (self.src / 'a.md').write_text('Вопрос: x = 1\n\nОтвет: не доказано.\n')
        self.store = self.p / 'store'; inventory = intake.inventory(self.src, self.store)
        self.prep = self.p / 'prepared'; prep = intake.prepare(self.store, 'a.md', self.prep)
        self.row = dict(path='a.md', sha256=inventory['files'][0]['sha256'],
                        stage='prepared', prepared=str(self.prep))
        self.old = self.p / 'old.json'; put(self.old, dict(batch='old', items=[self.row], next_batch=['a']))
        self.reg = self.p / 'registry.json'; put(self.reg, dict(streams=[
            dict(id='test', current_queue=str(self.old), current_summary={'old': True}),
            dict(id='other', important='preserve')]))
        self.pkg = self.p / 'package'; self.pkg.mkdir()
        (self.pkg/'README.md').write_text('Synthetic test package, not a real scientific result.')
        chunk = prep['chunks'][0]
        self.review = self.pkg / 'review.json'; put(self.review, dict(source_path='a.md',
            source_sha256=self.row['sha256'], chunk_path=chunk['file'],
            chunk_sha256=chunk['sha256'], chunk_chars=chunk['chars']))
        self.newrow = dict(self.row, stage='editorial_pilot_reviewed',
            reviews=[str(self.review)], reviewed_chunks=[chunk['file']], unreviewed_chunks=[],
            reviewed_chars=chunk['chars'])
        self.queue = self.pkg / 'queue.json'; put(self.queue, dict(batch='next', items=[self.newrow],
            previous_queue=str(self.old), next_batch=[]))
        self.ledger = self.pkg / 'ledger.json'; put(self.ledger, ledger([task()]))
        self.artifact(self.review, (self.prep / chunk['file']).read_text())
        self.manifest = self.pkg / 'MANIFEST.sha256'; self.manifest_refresh()
        self.request = dict(schema='geek-work-finalize-1', stream='test', operation_id='op1',
            expected_state=tx.state_identity(tx.load(self.reg)['streams'][0]),
            expected_queue_sha256=tx.digest(self.old.read_bytes()), queue=str(self.queue),
            ledger=str(self.ledger), manifest=str(self.manifest), store=str(self.store))

    def artifact(self, review, text):
        output=review.with_suffix('.edited.md'); journal=review.with_suffix('.edits.json')
        output.write_text(text); h=tx.digest(text.encode())
        put(journal,dict(input_sha256=h,output_sha256=h,edits=[]))
        r=tx.load(review);r.update(edited_output=str(output),edit_journal=str(journal));put(review,r)

    def manifest_refresh(self):
        self.manifest.write_text(''.join(tx.digest(p.read_bytes())+'  '+p.name+'\n'
            for p in sorted(self.pkg.iterdir()) if p.is_file() and p != self.manifest))

    def test_completed_status_correction_requires_pinned_reason(self):
        old = tx.load(self.old); old['items'][0]['stage'] = 'editorial_pilot_reviewed'; put(self.old, old)
        self.request['expected_state'] = tx.state_identity(tx.load(self.reg)['streams'][0])
        self.request['expected_queue_sha256'] = tx.digest(self.old.read_bytes())
        q = tx.load(self.queue); q['items'][0]['stage'] = 'extraction_review_required'; put(self.queue,q)
        self.manifest_refresh()
        before = self.reg.read_bytes()
        with self.assertRaisesRegex(ValueError, 'explicit reason'):
            tx.finalize(self.reg,self.request)
        self.assertEqual(self.reg.read_bytes(),before)
        evidence=self.pkg/'quality.json';put(evidence,dict(issue='Source export is clipped'))
        q['items'][0]['status_correction']=dict(previous_stage='editorial_pilot_reviewed',
            new_stage='extraction_review_required',reason='Source quality needs followup',
            evidence=[dict(path=str(evidence),sha256='0'*64)])
        put(self.queue,q);self.manifest_refresh()
        with self.assertRaisesRegex(ValueError,'evidence mismatch'):
            tx.finalize(self.reg,self.request)
        q['items'][0]['status_correction']['evidence'][0]['sha256']=tx.digest(evidence.read_bytes())
        put(self.queue,q);self.manifest_refresh()
        self.assertEqual(tx.finalize(self.reg,self.request)['status'],'COMMITTED')

    def test_readiness_is_read_only_and_matches_finalize(self):
        before = self.reg.read_bytes()
        result = tx.audit_queue(self.queue, self.store, 'test')
        self.assertEqual(result['status'], 'valid')
        self.assertFalse(result['committed'])
        self.assertFalse(result['semantic_review'])
        self.assertEqual(self.reg.read_bytes(), before)
        self.assertFalse((self.p / 'geek-work-transactions').exists())
        self.assertEqual(tx.finalize(self.reg, self.request)['status'], 'COMMITTED')

    def test_readiness_catches_artifact_tamper_and_source_tamper(self):
        self.review.with_suffix('.edited.md').write_text('lost formula')
        result = tx.audit_queue(self.queue, self.store, 'test')
        self.assertEqual(result['status'], 'invalid')
        self.assertEqual(result['issues'][0]['source'], 'a.md')
        self.assertIn('hash mismatch', result['issues'][0]['detail'])
        inv = tx.load(self.store / 'inventory.json')
        (self.store / inv['files'][0]['snapshot']).write_text('changed source')
        result = tx.audit_queue(self.queue, self.store, 'test')
        self.assertIn('Source snapshot mismatch', result['issues'][0]['detail'])

    def test_readiness_rechecks_inputs_after_validation(self):
        original = tx.check_source_row
        def mutate(*args):
            original(*args)
            self.review.with_suffix('.edited.md').write_text('changed after check')
        with patch.object(tx, 'check_source_row', mutate):
            result = tx.audit_queue(self.queue, self.store, 'test')
        self.assertEqual(result['status'], 'invalid')
        self.assertTrue(any('changed during' in x['detail'] for x in result['issues']))

    def test_readiness_cli_reports_failure_without_registry_write(self):
        self.review.with_suffix('.edited.md').unlink()
        output = self.p / 'readiness.json'; before = self.reg.read_bytes()
        proc = subprocess.run([sys.executable, '-B', str(TOOLS / 'geek_work.py'),
            'audit-queue', str(self.queue), str(self.store), '--output', str(output)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(tx.load(output)['status'], 'invalid')
        self.assertEqual(self.reg.read_bytes(), before)

    def test_commit_all_bindings_and_preserve_other_stream(self):
        result = tx.finalize(self.reg, self.request); self.assertEqual(result['status'], 'COMMITTED')
        doc = tx.load(self.reg); s = doc['streams'][0]; r = tx.load(Path(result['receipt']))
        self.assertEqual(doc['streams'][1]['important'], 'preserve')
        self.assertEqual(s['current_summary']['queue_sha256'], r['queue_sha256'])
        self.assertEqual(tx.digest(Path(s['current_queue']).read_bytes()), r['queue_sha256'])
        self.assertEqual(s['current_summary']['batch'], r['batch'])
        self.assertEqual(tx.ledger_report(self.reg, 'test')['committed_operations'], 1)
        self.assertEqual(gw.status(self.reg, 'test')['expected_state'], tx.state_identity(s))

    def test_exact_retry_does_not_write_or_double_charge(self):
        first = tx.finalize(self.reg, self.request); original = self.reg.read_bytes()
        second = tx.finalize(self.reg, self.request)
        self.assertEqual(second['status'], 'ALREADY_COMMITTED')
        self.assertEqual(first['receipt'], second['receipt']); self.assertEqual(original, self.reg.read_bytes())
        self.assertEqual(tx.ledger_report(self.reg, 'test')['by_currency']['USD']['known_cost_total'], '0.25')

    def test_reused_id_different_payload_conflicts(self):
        tx.finalize(self.reg, self.request); original = self.reg.read_bytes()
        put(self.ledger, ledger([task(amount='0.50')])); self.manifest_refresh()
        with self.assertRaises(tx.FinalizeError) as caught: tx.finalize(self.reg, self.request)
        self.assertEqual(caught.exception.code, 'OPERATION_ID_CONFLICT'); self.assertEqual(original, self.reg.read_bytes())

    def test_stale_queue_hash_and_generation_rejected(self):
        for field in ['expected_state', 'expected_queue_sha256']:
            with self.subTest(field=field):
                request = dict(self.request); request[field] = '0' * 64; before = self.reg.read_bytes()
                with self.assertRaises(tx.FinalizeError) as e: tx.finalize(self.reg, request)
                self.assertEqual(e.exception.code, 'STALE_STATE_REJECTED'); self.assertEqual(before, self.reg.read_bytes())

    def test_source_tamper_missing_review_manifest_damage_refused(self):
        targets = [self.store / tx.load(self.store / 'inventory.json')['files'][0]['snapshot'],
                   self.review, self.manifest]
        for path in targets:
            with self.subTest(path=path):
                original = path.read_bytes(); before = self.reg.read_bytes(); path.write_bytes(b'corrupt')
                with self.assertRaises((ValueError, KeyError)): tx.finalize(self.reg, self.request)
                self.assertEqual(before, self.reg.read_bytes()); path.write_bytes(original)

    def test_windows_reject_gap_overlap_and_accept_full_partition(self):
        r = tx.load(self.review); n = r['chunk_chars']; second = self.pkg / 'review2.json'
        q = tx.load(self.queue); q['items'][0]['reviews'].append(str(second)); put(self.queue, q)
        for lo in [n//2-1, n//2+1, n//2]:
            put(self.review, dict(r, review_window_char_offsets=[0,n//2], chunk_chars=n//2))
            put(second, dict(r, review_window_char_offsets=[lo,n], chunk_chars=n-lo))
            text=(self.prep/'chunks/0001.md').read_text()
            self.artifact(self.review,text[:n//2]);self.artifact(second,text[lo:]);self.manifest_refresh()
            if lo == n//2: self.assertEqual(tx.finalize(self.reg,self.request)['status'], 'COMMITTED')
            else:
                before=self.reg.read_bytes()
                with self.assertRaisesRegex(ValueError,'gap or overlap'): tx.finalize(self.reg,self.request)
                self.assertEqual(before,self.reg.read_bytes())

    def test_edited_content_tampering_even_with_fresh_manifest_refused(self):
        r=tx.load(self.review);p=Path(r['edited_output']);p.write_text('Lost formula')
        journal=Path(r['edit_journal']);j=tx.load(journal);j['output_sha256']=tx.digest(p.read_bytes());put(journal,j)
        self.manifest_refresh();before=self.reg.read_bytes()
        with self.assertRaisesRegex(ValueError,'reconstruction mismatch'):tx.finalize(self.reg,self.request)
        self.assertEqual(before,self.reg.read_bytes())

    def test_change_after_prepare_refused_and_orphan_not_committed(self):
        before=self.reg.read_bytes()
        def change(phase):
            if phase=='prepared': self.review.write_text('{}')
        with patch.object(tx,'checkpoint',side_effect=change):
            with self.assertRaisesRegex(ValueError,'changed before commit'): tx.finalize(self.reg,self.request)
        self.assertEqual(before,self.reg.read_bytes())
        inspect=tx.inspect_transactions(self.reg,'test'); self.assertEqual(len(inspect['unreferenced']),1)
        self.assertEqual(tx.ledger_report(self.reg,'test')['committed_operations'],0)

    def test_real_process_crashes_before_and_after_commit(self):
        for phase in ['prepared', 'before_replace', 'after_replace']:
            with self.subTest(phase=phase):
                # Restore fixture registry only; orphan transactions stay and cannot count themselves.
                put(self.reg,dict(streams=[dict(id='test',current_queue=str(self.old),current_summary={'old':True})]))
                before=self.reg.read_bytes(); proc=multiprocessing.Process(target=crash_worker,args=(str(self.reg),self.request,phase))
                proc.start();proc.join(10);self.assertFalse(proc.is_alive());self.assertEqual(proc.exitcode,73)
                if phase!='after_replace':self.assertEqual(before,self.reg.read_bytes())
                result=tx.finalize(self.reg,self.request)
                self.assertEqual(result['status'],'ALREADY_COMMITTED' if phase=='after_replace' else 'COMMITTED')
                self.assertEqual(tx.ledger_report(self.reg,'test')['committed_operations'],1)

    def test_two_processes_only_one_wins(self):
        event=multiprocessing.Event();results=multiprocessing.Queue()
        requests=[self.request,dict(self.request,operation_id='op2')]
        procs=[multiprocessing.Process(target=race_worker,args=(str(self.reg),r,event,results)) for r in requests]
        for p in procs:p.start()
        event.set()
        for p in procs:p.join(10);self.assertFalse(p.is_alive());self.assertEqual(p.exitcode,0)
        self.assertEqual(sorted(results.get(timeout=2) for _ in procs),['COMMITTED','STALE_STATE_REJECTED'])
        self.assertEqual(tx.ledger_report(self.reg,'test')['committed_operations'],1)

    def test_second_commit_and_old_retry_do_not_double_count_tasks(self):
        tx.finalize(self.reg,self.request); s=tx.load(self.reg)['streams'][0]
        q=tx.load(self.queue);q['previous_queue']=s['current_queue'];q['batch']='next2';put(self.queue,q)
        request=dict(self.request,operation_id='op2',expected_state=tx.state_identity(s),
                     expected_queue_sha256=tx.digest(Path(s['current_queue']).read_bytes()))
        self.manifest_refresh();before=self.reg.read_bytes()
        with self.assertRaisesRegex(ValueError,'Duplicate task'):tx.finalize(self.reg,request)
        self.assertEqual(before,self.reg.read_bytes())
        put(self.ledger,ledger([task('t2')]));self.manifest_refresh();tx.finalize(self.reg,request)
        self.assertEqual(tx.ledger_report(self.reg,'test')['by_currency']['USD']['known_cost_total'],'0.50')

    def test_old_retry_after_later_commit_returns_original_receipt(self):
        first=tx.finalize(self.reg,self.request);s=tx.load(self.reg)['streams'][0]
        pkg2=self.p/'package2';pkg2.mkdir();(pkg2/'README.md').write_text('Synthetic package2')
        q=tx.load(self.queue);q['previous_queue']=s['current_queue'];q['batch']='next2'
        put(pkg2/'queue.json',q);put(pkg2/'ledger.json',ledger([task('t2')]))
        (pkg2/'MANIFEST.sha256').write_text(''.join(tx.digest(p.read_bytes())+'  '+p.name+'\n'
            for p in sorted(pkg2.iterdir())))
        request=dict(self.request,operation_id='op2',expected_state=tx.state_identity(s),
            expected_queue_sha256=tx.digest(Path(s['current_queue']).read_bytes()),
            queue=str(pkg2/'queue.json'),ledger=str(pkg2/'ledger.json'),manifest=str(pkg2/'MANIFEST.sha256'))
        tx.finalize(self.reg,request);before=self.reg.read_bytes()
        result=tx.finalize(self.reg,self.request)
        self.assertEqual(result['status'],'ALREADY_COMMITTED');self.assertEqual(result['receipt'],first['receipt'])
        self.assertEqual(before,self.reg.read_bytes());self.assertEqual(tx.ledger_report(self.reg,'test')['committed_operations'],2)

    def test_acceptance_evidence_is_hashed_and_attempt_retries_are_charged(self):
        t=task(outcome='accepted');t['acceptance']=dict(kind='machine_check',
            evidence=[dict(path=str(self.review),sha256=tx.digest(self.review.read_bytes()))])
        retry=copy.deepcopy(t['attempts'][0]);retry.update(attempt_id=2,model_transition='downgrade')
        t['attempts'].append(retry);t['attempts_count']=2
        put(self.ledger,ledger([t]));self.manifest_refresh();tx.finalize(self.reg,self.request)
        c=tx.ledger_report(self.reg,'test')['by_currency']['USD']
        self.assertEqual(c['cost_per_accepted_result'],'0.50');self.assertEqual(c['attempts'],2)

    def test_failed_write_leaves_original_registry(self):
        before=self.reg.read_bytes()
        with patch.object(tx,'write_new',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):tx.finalize(self.reg,self.request)
        self.assertEqual(before,self.reg.read_bytes());self.assertEqual(tx.ledger_report(self.reg,'test')['committed_operations'],0)

    def test_tampered_committed_transaction_rejected(self):
        result=tx.finalize(self.reg,self.request); p=Path(result['receipt']).parent/'ledger.json';p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'seal mismatch'):tx.ledger_report(self.reg,'test')

    def test_cli_status_finalize_and_report(self):
        req=self.p/'request.json';put(req,self.request)
        for args in [['status',str(self.reg),'--stream','test'],['finalize',str(self.reg),str(req)],
                     ['ledger-report',str(self.reg),'--stream','test']]:
            proc=subprocess.run([sys.executable,'-B',str(TOOLS/'geek_work.py'),*args],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout);json.loads(proc.stdout)


class LedgerTests(unittest.TestCase):
    def test_unknowns_remain_unknown_and_rejected_costs_count(self):
        accepted=task('a','accepted','0.10');accepted['acceptance']=dict(kind='machine_check',
            evidence=[dict(path='/test',sha256='0'*64)])
        d=ledger([accepted,task('b','rejected','0.20')]);r=costs.summarize([d])['by_currency']['USD']
        self.assertEqual(r['cost_per_accepted_result'],'0.30');self.assertEqual(r['known_cost_total'],'0.30')
        self.assertEqual(r['unknown_token_attempts'],2);self.assertEqual(r['unknown_human_intervention_attempts'],2)
        d['tasks'][1]['attempts'][0]['monetary_cost']=None
        r=costs.summarize([d])['by_currency']['USD'];self.assertIsNone(r['total_cost']);self.assertIsNone(r['cost_per_accepted_result'])
        self.assertEqual(r['known_cost_total'],'0.10')
        self.assertIsNone(costs.summarize([ledger([task()])])['by_currency']['USD']['cost_per_accepted_result'])

    def test_retry_models_and_human_events(self):
        t=task();a=t['attempts'][0];a['model_profile']=dict(model_id='primary',configuration={})
        b=copy.deepcopy(a);b.update(attempt_id=2,model_transition='downgrade',model_profile=dict(model_id='fallback',configuration={}),
                                   human_interventions=[dict(type='restart',description='owner restart')])
        t['attempts'].append(b);t['attempts_count']=2
        r=costs.summarize([ledger([t])])['by_currency']['USD'];self.assertEqual(r['attempts'],2);self.assertEqual(r['known_human_interventions'],1)
        b['model_transition']='same'
        with self.assertRaises(ValueError):costs.validate(ledger([t]))

    def test_invalid_numbers_and_self_acceptance_fail(self):
        for amount in [True,1.0,'NaN','-0.1','Infinity']:
            with self.subTest(amount=amount),self.assertRaises(ValueError):costs.validate(ledger([task(amount=amount)]))
        t=task(outcome='accepted');t['acceptance']=dict(kind='model_self_report',evidence=[])
        with self.assertRaises(ValueError):costs.validate(ledger([t]))
        t=task();t['attempts_count']=True
        with self.assertRaises(ValueError):costs.validate(ledger([t]))

    def test_currencies_are_not_added_together(self):
        a=ledger([task('a')]);b=ledger([task('b')]);b['currency']='EUR'
        self.assertEqual(set(costs.summarize([a,b])['by_currency']),{'USD','EUR'})


if __name__=='__main__':unittest.main()
