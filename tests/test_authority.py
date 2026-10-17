"""Authority expectations are explicit; synthetic UIDs are model tests, not deployment."""
import unittest,os,tempfile,fcntl,socket,dataclasses,subprocess,struct
from pathlib import Path
from authority.gate import Grant,Job,Policy,Refusal,authorize,snapshot,authorized_peer,launch,SPEC,CAP
from codec import decode
ROOT=Path(__file__).resolve().parents[1]
class Authority(unittest.TestCase):
 def setUp(self):
  self.uid=os.getuid();self.control=(ROOT/'tests/fixtures/minimum-context.json').read_bytes();self.grant=Grant(self.uid,'task-0',1,self.control);self.job=Job('task-0',1,self.uid+1);self.policy=Policy((self.grant,))
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.local/tmp');self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name);os.chmod(self.d,0o700);self.path=self.d/'context';self.path.write_bytes(self.control);os.chmod(self.path,0o600);self.fd=os.open(self.d,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.fd)
 def denied(self,code,fn,*args):
  with self.assertRaises(Refusal)as c:fn(*args)
  self.assertEqual(c.exception.code,code)
 def auth(self,grant=None,job=None,policy=None,observed=None):return authorize(policy or self.policy,job or self.job,grant or self.grant,self.uid if observed is None else observed)
 def test_valid_model(self):self.assertEqual(self.auth(),self.control)
 def test_missing_policy(self):self.denied('missing_authority',authorize,None,self.job,self.grant,self.uid)
 def test_missing_grant(self):self.denied('missing_authority',authorize,self.policy,self.job,None,self.uid)
 def test_unapproved_grant(self):self.denied('unauthorized_grant',self.auth,dataclasses.replace(self.grant,control=b'{}'))
 def test_other_expected_same_bits(self):self.denied('unauthorized_grant',self.auth,dataclasses.replace(self.grant,control=(ROOT/'tests/fixtures/other-context.json').read_bytes()))
 def test_source_without_rights(self):self.denied('unauthorized_source',self.auth,None,None,None,self.uid+2)
 def test_executor_self_assignment(self):self.denied('executor_self_assignment',self.auth,None,dataclasses.replace(self.job,executor_uid=self.uid))
 def test_cross_task(self):self.denied('task_mismatch',self.auth,None,dataclasses.replace(self.job,task='task-1'))
 def test_stale_revision(self):self.denied('stale_revision',self.auth,None,dataclasses.replace(self.job,revision=2))
 def test_wrong_spec(self):self.denied('spec_mismatch',self.auth,None,dataclasses.replace(self.job,spec='other'))
 def test_boolean_uid(self):self.denied('invalid_authority',self.auth,None,dataclasses.replace(self.job,executor_uid=True))
 def test_resource_cap(self):
  g=dataclasses.replace(self.grant,control=b'x'*(CAP+1));self.denied('resource_limit',authorize,Policy((g,)),self.job,g,self.uid)
 def test_snapshot_exact(self):
  fd=snapshot(self.policy,self.job,self.grant,self.fd,'context');self.addCleanup(os.close,fd);self.assertEqual(os.read(fd,CAP),self.control)
 def test_snapshot_sealed(self):
  fd=snapshot(self.policy,self.job,self.grant,self.fd,'context');self.addCleanup(os.close,fd)
  with self.assertRaises(PermissionError):os.write(fd,b'x')
  with self.assertRaises(PermissionError):os.ftruncate(fd,0)
 def test_path_replacement_after_check(self):
  fd=snapshot(self.policy,self.job,self.grant,self.fd,'context');self.addCleanup(os.close,fd);self.path.write_bytes(b'{}');self.assertEqual(os.read(fd,CAP),self.control)
 def test_same_path_changed_content(self):
  self.path.write_bytes((ROOT/'tests/fixtures/other-context.json').read_bytes());self.denied('context_mismatch',snapshot,self.policy,self.job,self.grant,self.fd,'context')
 def test_group_write(self):
  os.chmod(self.path,0o660);self.denied('unsafe_source',snapshot,self.policy,self.job,self.grant,self.fd,'context')
 def test_unsafe_directory(self):
  os.chmod(self.d,0o770);self.denied('unsafe_directory',snapshot,self.policy,self.job,self.grant,self.fd,'context')
 def test_symlink_rejected(self):
  (self.d/'link').symlink_to(self.path)
  with self.assertRaises(OSError):snapshot(self.policy,self.job,self.grant,self.fd,'link')
 def test_path_traversal(self):self.denied('invalid_source',snapshot,self.policy,self.job,self.grant,self.fd,'../context')
 def test_actual_peer_credential(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);self.assertEqual(authorized_peer(dataclasses.replace(self.job,executor_uid=self.uid),a),self.uid)
 def test_actual_peer_mismatch(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);self.denied('unauthorized_executor',authorized_peer,self.job,a)
 def test_actual_same_uid_launch_refused(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close);self.denied('executor_self_assignment',launch,self.policy,dataclasses.replace(self.job,executor_uid=self.uid),self.grant,self.fd,'context',a,ROOT/'.lake/build/bin/sql_stream_reader')
 def test_native_uses_sealed_context(self):
  # Tests snapshot-to-native connection, not authenticated two-UID launch.
  fd=snapshot(self.policy,self.job,self.grant,self.fd,'context');self.addCleanup(os.close,fd);self.path.write_bytes((ROOT/'tests/fixtures/other-context.json').read_bytes())
  raw=(ROOT/'tests/fixtures/other-request.json').read_bytes();p=subprocess.run([str(ROOT/'.lake/build/bin/sql_stream_reader'),'--context',f'/proc/self/fd/{fd}','--budget','1'],input=struct.pack('>I',len(raw))+raw,pass_fds=(fd,),capture_output=True,timeout=10);self.assertEqual(p.returncode,0);self.assertEqual(decode(p.stdout[9:])['status'],'instance_mismatch')
 def test_no_default_allow(self):self.denied('unauthorized_grant',authorize,Policy(()),self.job,self.grant,self.uid)
 def test_frozen_grant(self):
  with self.assertRaises(dataclasses.FrozenInstanceError):self.grant.control=b'{}'
