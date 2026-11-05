import contextlib
import copy
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import geek_work_proof_nonce as n
sys.path.pop(0)


def request(nonce='01'*32):
    return dict(target=dict(ecosystem='offline', network='local', application_id='pilot',
                            verifier_id='vk'), nonce=nonce)


def worker(path, rid, statement, q):
    try:
        with contextlib.closing(n.connect(path, rid)) as db:
            r = n._commit_verified(db, rid, request(), statement, {})
        q.put(r['status'])
    except n.k.Refusal as e:
        q.put(str(e))


def crash_worker(path, rid, point):
    def fault(stage):
        if stage == point: os._exit(71)
    with contextlib.closing(n.connect(path, rid)) as db:
        n._commit_verified(db, rid, request(), 'aa'*32, {}, fault)


class ProofNonceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root/'registry.db'
        self.rid = n.initialize(self.path)['registry_id']

    def commit(self, r=None, statement='aa'*32, fault=lambda s: None):
        with contextlib.closing(n.connect(self.path, self.rid)) as db:
            return n._commit_verified(db, self.rid, r or request(), statement, {}, fault)

    def count(self):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT count(*) FROM consumed').fetchone()[0]

    def test_receipt_idempotence_and_conflict(self):
        first = self.commit(); second = self.commit()
        self.assertEqual(first['status'], 'consumed')
        self.assertEqual(second['status'], 'already_consumed')
        self.assertEqual(first['receipt_sha256'], second['receipt_sha256'])
        self.assertEqual(first['receipt'], second['receipt'])
        self.assertFalse(second['new_consumption'])
        with self.assertRaisesRegex(n.k.Refusal,'nonce_conflict'): self.commit(statement='bb'*32)
        self.assertEqual(self.count(),1)

    def test_scope_and_verifier_rotation(self):
        self.commit()
        r=request();r['target']['verifier_id']='rotated'
        with self.assertRaisesRegex(n.k.Refusal,'nonce_conflict'):self.commit(r,'bb'*32)
        for field in ('network','application_id'):
            r=request();r['target'][field]='other';self.assertTrue(self.commit(r,'bb'*32)['new_consumption'])
        self.assertTrue(self.commit(request('02'*32))['new_consumption'])
        self.assertEqual(self.count(),4)

    def test_missing_wrong_identity_and_no_overwrite(self):
        with self.assertRaises(FileExistsError):n.initialize(self.path)
        with self.assertRaisesRegex(n.k.Refusal,'registry_identity'):n.connect(self.path,'wrong')
        other=self.root/'lost.db'
        with self.assertRaises(n.k.Refusal):n.connect(other,self.rid)
        self.assertFalse(other.exists())
        link=self.root/'link';link.symlink_to(self.path)
        with self.assertRaises(n.k.Refusal):n.connect(link,self.rid)

    def test_crash_before_commit_rolls_back_after_commit_replays(self):
        ctx=multiprocessing.get_context('fork')
        for point,rows in [('before_commit',0),('after_commit',1)]:
            p=ctx.Process(target=crash_worker,args=(str(self.path),self.rid,point))
            p.start();p.join(10);self.assertEqual(p.exitcode,71)
            self.assertEqual(self.count(),rows)
        self.assertEqual(self.commit()['status'],'already_consumed')

    def test_concurrent_same_and_conflicting_requests(self):
        ctx=multiprocessing.get_context('fork');q=ctx.Queue()
        procs=[ctx.Process(target=worker,args=(str(self.path),self.rid,'aa'*32,q)) for _ in range(4)]
        for p in procs:p.start()
        for p in procs:p.join(10);self.assertEqual(p.exitcode,0)
        results=[q.get(timeout=2) for _ in procs]
        self.assertEqual(results.count('consumed'),1)
        self.assertEqual(results.count('already_consumed'),3)
        self.assertEqual(self.count(),1)
        q.close()
        other=self.root/'race.db';rid=n.initialize(other)['registry_id'];q=ctx.Queue()
        procs=[ctx.Process(target=worker,args=(str(other),rid,s*64,q)) for s in ('a','b')]
        for p in procs:p.start()
        for p in procs:p.join(10);self.assertEqual(p.exitcode,0)
        self.assertEqual(sorted(q.get(timeout=2) for _ in procs),['consumed','nonce_conflict'])
        q.close()

    def test_unverified_or_timeout_result_never_consumes(self):
        # Mocking only tests orchestration ordering. Real crypto is a separate e2e run.
        bundle=self.root/'bundle';bundle.mkdir()
        a=dict(specification=n.adapter.SPEC,parameters=n.adapter.PARAMETERS,program=b'circuit',
               verifier=b'key',input=b'{"h":[1,2,3]}',public_output=b'{"t":[4,13,28,27,18]}')
        r=request();r.update(schema=n.adapter.contract.SCHEMA,claim='bounded-convolution-v1',
                            artifacts={k:n.k.digest(v) for k,v in a.items()},
                            backend=dict(id='gnark',version='v0.16.4',proof_system='groth16-bn254'),
                            requirements=dict(zero_knowledge=True,post_quantum=False))
        raw=n.k.canonical(r);(bundle/'request.json').write_bytes(raw)
        for name,b in a.items():(bundle/n.adapter.FILES[name]).write_bytes(b)
        (bundle/'proof.bin').write_bytes(b'proof')
        binary=self.root/'binary';binary.write_bytes(b'test-placeholder-not-executed')
        args=(bundle,n.k.digest(raw),self.path,self.rid,binary,n.k.digest(binary.read_bytes()))
        for reason in ('verification_failed','verification_timeout','verification_result_missing'):
            with patch.object(n,'_verify',side_effect=n.k.Refusal(reason)),self.assertRaises(n.k.Refusal):n.consume(*args)
            self.assertEqual(self.count(),0)
        # The verifier sees a stable snapshot even if originals change meanwhile.
        def verifier(snapshot,executable,sha,timeout):
            self.assertNotEqual(snapshot,bundle)
            (bundle/'proof.bin').write_bytes(b'changed-after-snapshot')
            self.assertEqual((snapshot/'proof.bin').read_bytes(),b'proof')
        with patch.object(n,'_verify',side_effect=verifier):first=n.consume(*args)
        self.assertTrue(first['new_consumption']);self.assertEqual(self.count(),1)
        with patch.object(n,'_verify',side_effect=n.k.Refusal('verification_failed')),self.assertRaises(n.k.Refusal):n.consume(*args)
        self.assertEqual(self.count(),1)
        with self.assertRaisesRegex(n.k.Refusal,'backend_pin_mismatch'):
            n.consume(*args[:-1],'00'*32)

    def test_backend_exit_marker_and_timeout(self):
        import subprocess
        from types import SimpleNamespace
        for rc,output in [(1,n.SUCCESS.encode()),(0,b'arbitrary success')]:
            with patch.object(n.subprocess,'run',return_value=SimpleNamespace(returncode=rc,stdout=output,stderr=b'')),self.assertRaises(n.k.Refusal):n._verify(self.root,self.path,'00'*32,1)
        with patch.object(n.subprocess,'run',side_effect=subprocess.TimeoutExpired('backend',1)),self.assertRaisesRegex(n.k.Refusal,'verification_timeout'):
            n._verify(self.root,self.path,'00'*32,1)

    def test_artifact_reader_rejects_symlinks_and_oversize(self):
        p=self.root/'large';p.write_bytes(b'12345')
        with self.assertRaises(n.k.Refusal):n.read_regular(p,4)
        l=self.root/'link';l.symlink_to(p)
        with self.assertRaises(OSError):n.read_regular(l,10)

        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(n.k.Refusal):n.read_regular(fifo,10)

    def test_cli_initialization_and_missing_registry(self):
        import subprocess
        path=self.root/'cli.db'
        cmd=[sys.executable,n.__file__,'init','--registry',str(path)]
        first=subprocess.run(cmd,capture_output=True)
        self.assertEqual(first.returncode,0,first.stderr)
        result=json.loads(first.stdout)
        with contextlib.closing(n.connect(path,result['registry_id'])):pass
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        missing=self.root/'missing.db'
        bad=subprocess.run([sys.executable,n.__file__,'consume','--registry',str(missing),
                            '--registry-id',self.rid,'--bundle',str(self.root),
                            '--expected-request-sha256','00'*32,'--backend',str(self.root/'none'),
                            '--expected-backend-sha256','00'*32],capture_output=True)
        self.assertEqual(bad.returncode,1)
        self.assertEqual(json.loads(bad.stdout)['reason'],'registry_missing_or_symlink')
        self.assertFalse(missing.exists())
