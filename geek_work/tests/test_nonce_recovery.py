import contextlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import geek_work_nonce_recovery as r
sys.path.pop(0)


def req(value='01'*32):
    return dict(target=dict(ecosystem='offline',network='local',application_id='test'),nonce=value)


def add(path,rid,value='01'*32):
    with contextlib.closing(r.nonce.connect(path,rid)) as db:
        return r.nonce._commit_verified(db,rid,req(value),'aa'*32,{})


def writer(path,rid,ready):
    def after_insert(stage):
        if stage=='before_commit':ready.set()
    with contextlib.closing(r.nonce.connect(path,rid)) as db:
        r.nonce._commit_verified(db,rid,req('02'*32),'bb'*32,{},after_insert)


class NonceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'source.db'
        self.rid=r.nonce.initialize(self.db)['registry_id'];self.first=add(self.db,self.rid)

    def snap(self,name='snapshot'):
        p=self.root/name;result=r.snapshot(self.db,self.rid,p)
        return p,result['checkpoint_sha256']

    def test_roundtrip_preserves_receipt_and_no_active_switch(self):
        p,h=self.snap();dest=self.root/'restored.db'
        result=r.restore(p,h,self.rid,dest)
        self.assertFalse(result['active_registry_switched'])
        self.assertEqual(r.compare(dest,self.rid,p/'checkpoint.json',h)['rows'],1)
        replay=add(dest,self.rid)
        self.assertEqual(replay['status'],'already_consumed')
        self.assertEqual(replay['receipt_sha256'],self.first['receipt_sha256'])

    def test_stale_snapshot_rejected_against_new_external_anchor(self):
        old,old_h=self.snap('old');add(self.db,self.rid,'02'*32);new,new_h=self.snap('new')
        with self.assertRaisesRegex(r.k.Refusal,'checkpoint_anchor_mismatch'):
            r.restore(old,new_h,self.rid,self.root/'stale.db')
        self.assertFalse((self.root/'stale.db').exists())
        with self.assertRaisesRegex(r.k.Refusal,'state_mismatch'):
            r.compare(old/'registry.db',self.rid,new/'checkpoint.json',new_h)
        # Old anchor explicitly provided still restores old state: no monotonic service.
        self.assertEqual(r.restore(old,old_h,self.rid,self.root/'explicit-old.db')['rows'],1)

    def test_equal_row_count_changed_state_is_rejected(self):
        p,h=self.snap()
        with sqlite3.connect(self.db) as db:
            raw=db.execute('SELECT receipt FROM consumed').fetchone()[0];obj=json.loads(raw)
            obj['extra']='changed'
            db.execute('UPDATE consumed SET receipt=?',(r.k.canonical(obj).decode(),))
        with self.assertRaisesRegex(r.k.Refusal,'state_mismatch'):r.compare(self.db,self.rid,p/'checkpoint.json',h)

    def test_no_overwrite_or_symlink_follow(self):
        p,h=self.snap();before=self.db.read_bytes()
        with self.assertRaises(FileExistsError):r.restore(p,h,self.rid,self.db)
        self.assertEqual(self.db.read_bytes(),before)
        link=self.root/'link';link.symlink_to(self.root/'absent')
        with self.assertRaises(FileExistsError):r.restore(p,h,self.rid,link)
        self.assertFalse((self.root/'absent').exists())
        with self.assertRaises(FileExistsError):r.snapshot(self.db,self.rid,p)

    def test_tampered_missing_wrong_identity_and_bounds(self):
        p,h=self.snap()
        with self.assertRaisesRegex(r.k.Refusal,'checkpoint_identity'):r.restore(p,h,'wrong',self.root/'wrong.db')
        with (p/'registry.db').open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(r.k.Refusal,'backup_bytes_mismatch'):r.restore(p,h,self.rid,self.root/'changed.db')
        (p/'checkpoint.json').unlink()
        with self.assertRaises(OSError):r.restore(p,h,self.rid,self.root/'missing.db')
        with patch.object(r,'MAX_ROWS',0),self.assertRaisesRegex(r.k.Refusal,'registry_bounds'):
            self.snap('too-many')
        self.assertFalse((self.root/'too-many/checkpoint.json').exists())

    def test_failed_snapshot_has_no_completion_marker(self):
        dest=self.root/'incomplete'
        def fail():raise RuntimeError('injected')
        with self.assertRaises(RuntimeError):r.snapshot(self.db,self.rid,dest,fail)
        self.assertFalse((dest/'checkpoint.json').exists())

    def test_restore_failure_before_and_after_atomic_publish(self):
        p,h=self.snap()
        for phase,exists in [('before_publish',False),('after_publish',True)]:
            dest=self.root/(phase+'.db')
            def fault(stage):
                if stage==phase:raise RuntimeError('injected')
            with self.assertRaises(RuntimeError):r.restore(p,h,self.rid,dest,fault)
            self.assertEqual(dest.exists(),exists)
            if exists:r.compare(dest,self.rid,p/'checkpoint.json',h)
        self.assertEqual(list(self.root.glob('.nonce-restore-*')),[])

    def test_snapshot_is_consistent_during_concurrent_write(self):
        ctx=multiprocessing.get_context('fork');ready=ctx.Event();process=ctx.Process(target=writer,args=(str(self.db),self.rid,ready))
        def start():
            process.start();self.assertTrue(ready.wait(3))
        p=self.root/'concurrent'
        result=r.snapshot(self.db,self.rid,p,start)
        process.join(10);self.assertEqual(process.exitcode,0)
        h=result['checkpoint_sha256']
        self.assertIn(result['checkpoint']['rows'],(1,2))
        self.assertEqual(r.compare(p/'registry.db',self.rid,p/'checkpoint.json',h)['rows'],result['checkpoint']['rows'])
        # Advance again after the snapshot; the captured state must remain fixed.
        add(self.db,self.rid,'03'*32)
        with self.assertRaisesRegex(r.k.Refusal,'state_mismatch'):r.compare(self.db,self.rid,p/'checkpoint.json',h)

    def test_cli_and_portable_snapshot_without_source(self):
        p,h=self.snap();self.db.unlink()
        moved=self.root/'moved';p.rename(moved);dest=self.root/'recovered.db'
        proc=subprocess.run([sys.executable,r.__file__,'restore','--snapshot',str(moved),
                             '--registry-id',self.rid,'--expected-checkpoint-sha256',h,
                             '--destination',str(dest)],capture_output=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['restored_path'],str(dest))
        self.assertEqual(add(dest,self.rid)['receipt_sha256'],self.first['receipt_sha256'])

    def test_schema_and_receipt_invariants_checked_before_snapshot_completion(self):
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE consumed SET nonce=?',('03'*32,))
        with self.assertRaisesRegex(r.k.Refusal,'receipt_identity'):self.snap('bad-receipt')
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE consumed SET nonce=?',('01'*32,))
            db.execute('ALTER TABLE consumed RENAME TO previous')
            db.execute('CREATE TABLE consumed AS SELECT * FROM previous')
            db.execute('DROP TABLE previous')
        with self.assertRaisesRegex(r.k.Refusal,'registry_unique_key_schema'):self.snap('no-unique-key')
        self.assertFalse((self.root/'no-unique-key/checkpoint.json').exists())
