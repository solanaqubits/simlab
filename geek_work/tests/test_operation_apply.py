import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import geek_work_operation_apply as a
import test_operation_git as fixture_module


class OperationApplyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture_module.OperationGitTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.repo=self.f.repo;self.bundle=self.f.out;self.pin=self.f.stage()['manifest_sha256'];self.txn=self.f.f.root/'transaction'
        self.anchor=a.prepare(self.bundle,self.pin,self.repo,self.txn)['manifest_sha256'];self.before=self.snapshot()

    def snapshot(self):return {k:v for k,v in self.f.snapshot().items() if k!='.git/geek-work-apply.lock'}
    def run_action(self,action):return a.execute(self.txn,self.anchor,self.repo,action,True)
    def state(self):return json.loads((self.txn/'state.json').read_bytes())['status']

    def test_apply_idempotent_rollback_preserves_index_refs_objects(self):
        index=(self.repo/'.git/index').read_bytes();self.assertEqual(self.run_action('apply')['status'],'applied')
        self.assertFalse((self.repo/'refs.bib').exists());self.assertTrue((self.repo/'bib/refs.bib').exists());self.assertIn(b'{bib/refs}',(self.repo/'main.tex').read_bytes())
        self.assertEqual((self.repo/'.git/index').read_bytes(),index);self.assertTrue(self.run_action('apply')['idempotent'])
        self.assertEqual(self.run_action('rollback')['status'],'rolled_back');self.assertEqual(self.snapshot(),self.before);self.assertFalse((self.repo/'bib').exists())
        self.assertEqual(self.run_action('rollback')['status'],'rolled_back')
        with self.assertRaisesRegex(ValueError,'recovery'):self.run_action('apply')

    def test_unrelated_dirty_worktree_is_preserved(self):
        (self.repo/'unrelated.txt').write_bytes(b'Personal edit')
        self.run_action('apply');self.run_action('rollback');self.assertEqual((self.repo/'unrelated.txt').read_bytes(),b'Personal edit')

    def test_stale_selected_file_rejected_before_mutation(self):
        (self.repo/'section.tex').write_bytes(b'Intervening edit');before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'STALE'):self.run_action('apply')
        self.assertEqual(before,self.snapshot());self.assertEqual(self.state(),'prepared')

    def test_staged_index_or_head_change_rejects_apply(self):
        (self.repo/'unrelated.txt').write_bytes(b'Staged');self.f.cmd('add','unrelated.txt');before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'identity'):self.run_action('apply')
        self.assertEqual(self.snapshot(),before)
        self.f.cmd('commit','-qm','Moved HEAD');before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'identity'):self.run_action('apply')
        self.assertEqual(self.snapshot(),before)

    def test_prepare_rejects_dirty_index_and_selected_worktree(self):
        (self.repo/'main.tex').write_bytes(b'Dirty')
        with self.assertRaisesRegex(ValueError,'STALE'):a.prepare(self.bundle,self.pin,self.repo,self.txn.parent/'other')
        self.f.cmd('add','main.tex')
        with self.assertRaisesRegex(ValueError,'staged'):a.prepare(self.bundle,self.pin,self.repo,self.txn.parent/'other')

    def test_occupied_target_and_new_parent_rejected(self):
        (self.repo/'bib').mkdir()
        with self.assertRaisesRegex(ValueError,'directory baseline'):self.run_action('apply')
        (self.repo/'bib/refs.bib').write_bytes(b'External')
        with self.assertRaisesRegex(ValueError,'STALE'):self.run_action('apply')
        self.assertEqual((self.repo/'bib/refs.bib').read_bytes(),b'External')

    def test_symlink_and_hardlink_rejected(self):
        p=self.repo/'section.tex';raw=p.read_bytes();p.unlink();p.symlink_to('main.tex')
        with self.assertRaises((ValueError,OSError)):self.run_action('apply')
        p.unlink();p.write_bytes(raw);os.link(p,self.repo/'alias')
        with self.assertRaisesRegex(ValueError,'single-link'):self.run_action('apply')

    def test_foreign_index_lock_is_not_removed(self):
        lock=self.repo/'.git/index.lock';lock.write_bytes(b'Foreign Git operation')
        with self.assertRaises(ValueError):self.run_action('apply')
        self.assertEqual(lock.read_bytes(),b'Foreign Git operation');self.assertEqual(self.state(),'prepared')

    def test_live_own_lock_pid_is_not_reclaimed(self):
        lock=self.repo/'.git/index.lock';lock.write_bytes(a.m.encoded(dict(transaction_sha256=self.anchor,pid=os.getpid())))
        with self.assertRaisesRegex(ValueError,'still alive'):self.run_action('apply')
        self.assertTrue(lock.exists())

    def test_regular_failure_rolls_back_automatically(self):
        def fail(name):
            if name.startswith('written:'):raise RuntimeError('Injected failure')
        with patch.object(a,'checkpoint',fail),self.assertRaisesRegex(RuntimeError,'Injected'):self.run_action('apply')
        self.assertEqual(self.snapshot(),self.before);self.assertEqual(self.state(),'rolled_back');self.assertFalse((self.repo/'.git/index.lock').exists())

    def test_intervening_edit_blocks_whole_rollback(self):
        self.run_action('apply');(self.repo/'main.tex').write_bytes(b'Keep human edit');before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'INTERVENING_EDIT'):self.run_action('rollback')
        self.assertEqual(before,self.snapshot());self.assertEqual(self.state(),'recovery_required')

    def test_apply_failure_with_external_edit_requires_recovery(self):
        def fail(name):
            if name.startswith('written:'):
                (self.repo/'section.tex').write_bytes(b'Keep external change');raise RuntimeError('Injected')
        with patch.object(a,'checkpoint',fail),self.assertRaises(RuntimeError):self.run_action('apply')
        self.assertEqual(self.state(),'recovery_required');self.assertEqual((self.repo/'section.tex').read_bytes(),b'Keep external change')
        (self.repo/'section.tex').write_bytes((self.txn/'git-bundle/preflight/baseline/section.tex').read_bytes())
        self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_crash_after_file_write_and_explicit_recovery(self):
        code="import os,sys;sys.path.insert(0,sys.argv[1]);import geek_work_operation_apply as a;a.checkpoint=lambda n: os._exit(91) if n.startswith('written:') else None;a.execute(__import__('pathlib').Path(sys.argv[2]),sys.argv[3],__import__('pathlib').Path(sys.argv[4]),'apply',True)"
        r=subprocess.run([sys.executable,'-c',code,str(Path(a.__file__).parent),str(self.txn),self.anchor,str(self.repo)],capture_output=True)
        self.assertEqual(r.returncode,91,r.stderr);self.assertEqual(self.state(),'applying');self.assertTrue((self.repo/'.git/index.lock').exists())
        self.run_action('rollback');self.assertEqual(self.snapshot(),self.before);self.assertFalse((self.repo/'.git/index.lock').exists())

    def test_recovery_after_interrupted_rollback(self):
        self.run_action('apply')
        def fail(name):
            if name.startswith('restored:'):raise RuntimeError('Interrupted rollback')
        with patch.object(a,'checkpoint',fail),self.assertRaises(RuntimeError):self.run_action('rollback')
        self.assertEqual(self.state(),'recovery_required');self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_nonempty_created_directory_preserved_on_rollback(self):
        self.run_action('apply');(self.repo/'bib/user-note').write_bytes(b'Keep')
        with self.assertRaises(OSError):self.run_action('rollback')
        self.assertEqual((self.repo/'bib/user-note').read_bytes(),b'Keep');self.assertEqual(self.state(),'recovery_required')
        (self.repo/'bib/user-note').unlink();self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_mode_preserved_and_mode_change_rejected(self):
        (self.repo/'main.tex').chmod(0o600)
        with self.assertRaisesRegex(ValueError,'STALE'):self.run_action('apply')
        other=self.txn.parent/'mode-transaction';pin=a.prepare(self.bundle,self.pin,self.repo,other)['manifest_sha256']
        a.execute(other,pin,self.repo,'apply',True);self.assertEqual((self.repo/'main.tex').stat().st_mode&0o777,0o600)
        a.execute(other,pin,self.repo,'rollback',True);self.assertEqual((self.repo/'main.tex').stat().st_mode&0o777,0o600)

    def test_transaction_tamper_unknown_entries_and_root_binding(self):
        with self.assertRaisesRegex(ValueError,'anchor'):a.execute(self.txn,'0'*64,self.repo,'apply',True)
        (self.txn/'unexpected').write_bytes(b'No')
        with self.assertRaises(ValueError):self.run_action('apply')
        (self.txn/'unexpected').unlink();copy=self.txn.parent/'repo-copy';shutil.copytree(self.repo,copy)
        with self.assertRaisesRegex(ValueError,'repository mismatch'):a.execute(self.txn,self.anchor,copy,'apply',True)
        self.assertEqual(self.snapshot(),self.before)

    def test_rejected_operations_do_not_create_unused_directories(self):
        self.f.f.spec['files']=['main.tex','section.tex','refs.bib']
        self.f.rebuild(json.loads(self.f.f.ops.read_bytes())['operations'],reject=True)
        shutil.rmtree(self.bundle);self.pin=self.f.stage()['manifest_sha256'];self.txn=self.txn.parent/'rejected-transaction'
        self.anchor=a.prepare(self.bundle,self.pin,self.repo,self.txn)['manifest_sha256']
        self.run_action('apply');self.assertFalse((self.repo/'bib').exists());self.assertEqual(self.snapshot(),self.before)
        self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_crash_with_scratch_file_before_replace_recovers(self):
        code="import os,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import geek_work_operation_apply as a;original=a.os.replace;a.os.replace=lambda src,dst,**kw: os._exit(92) if str(src).endswith('.tmp') else original(src,dst,**kw);a.execute(Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4]),'apply',True)"
        r=subprocess.run([sys.executable,'-c',code,str(Path(a.__file__).parent),str(self.txn),self.anchor,str(self.repo)],capture_output=True)
        self.assertEqual(r.returncode,92,r.stderr);self.assertTrue(list((self.txn/'scratch').glob('*.tmp')))
        self.run_action('rollback');self.assertEqual(self.snapshot(),self.before);self.assertFalse(list((self.txn/'scratch').glob('*.tmp')))

    def test_binary_roundtrip_preserves_existing_directory(self):
        f=self.f.f;old=b'old\x00asset';new=b'new\x00asset'
        (f.base/'old.png').write_bytes(old);(self.repo/'old.png').write_bytes(old);(f.candidate/'new.png').write_bytes(new)
        self.f.cmd('add','.');self.f.cmd('commit','-qm','Binary baseline');self.f.commit=self.f.cmd('rev-parse','HEAD').decode().strip()
        rows=json.loads(f.ops.read_bytes())['operations']+[
            dict(id='delete-image',op='delete',kind='binary',source='old.png',target=None),
            dict(id='create-image',op='create',kind='binary',source=None,target='new.png')]
        f.spec['files'].append('new.png');self.f.rebuild(rows);shutil.rmtree(self.bundle);self.pin=self.f.stage()['manifest_sha256']
        (self.repo/'bib').mkdir();self.txn=self.txn.parent/'binary-transaction';self.anchor=a.prepare(self.bundle,self.pin,self.repo,self.txn)['manifest_sha256'];before=self.snapshot()
        self.run_action('apply');self.assertEqual((self.repo/'new.png').read_bytes(),new);self.assertFalse((self.repo/'old.png').exists())
        self.run_action('rollback');self.assertEqual(self.snapshot(),before);self.assertTrue((self.repo/'bib').is_dir())

    def test_competing_process_rejected_by_cooperative_lock(self):
        marker=self.txn.parent/'started';release=self.txn.parent/'release'
        code="import sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import geek_work_operation_apply as a;a.checkpoint=lambda n: (Path(sys.argv[5]).write_text('ready'),any(Path(sys.argv[6]).exists() or time.sleep(.01) for _ in range(1000))) if n=='started' else None;a.execute(Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4]),'apply',True)"
        child=subprocess.Popen([sys.executable,'-c',code,str(Path(a.__file__).parent),str(self.txn),self.anchor,str(self.repo),str(marker),str(release)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline=time.monotonic()+10
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(marker.exists())
        try:
            with self.assertRaises(BlockingIOError):self.run_action('apply')
        finally:release.write_text('continue')
        out,err=child.communicate(timeout=10);self.assertEqual(child.returncode,0,err);self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_linked_state_temp_does_not_overwrite_external_file(self):
        victim=self.txn.parent/'unrelated-external-file';victim.write_bytes(b'Preserve outside bytes')
        os.link(victim,self.txn/'state.next');self.run_action('apply')
        self.assertEqual(victim.read_bytes(),b'Preserve outside bytes');self.run_action('rollback');self.assertEqual(self.snapshot(),self.before)

    def test_quiescent_ack_and_output_separation(self):
        with self.assertRaisesRegex(ValueError,'quiescent'):a.execute(self.txn,self.anchor,self.repo,'apply')
        with self.assertRaises(ValueError):a.prepare(self.bundle,self.pin,self.repo,self.repo/'transaction')
        self.assertEqual(self.snapshot(),self.before)


if __name__=='__main__':unittest.main()
