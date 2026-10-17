"""POSIX supervisor gate 1.0.0. This Python/OS integration is not formally verified.

Policy and Job MUST be created by a trusted supervisor, separately from requests.
A file owner is authenticated by fstat, but only the separate policy grants rights.
No CLI turns request-supplied values into trusted policy. No default allow policy.
"""
from dataclasses import dataclass
import os,stat,fcntl,socket,struct,subprocess

SPEC='sql-gap-binary64-1.0.0'
CAP=16384
class Refusal(Exception):
 def __init__(self,code):super().__init__(code);self.code=code
@dataclass(frozen=True)
class Job:
 task:str
 revision:int
 executor_uid:int
 spec:str=SPEC
@dataclass(frozen=True)
class Grant:
 issuer_uid:int
 task:str
 revision:int
 control:bytes
 spec:str=SPEC
@dataclass(frozen=True)
class Policy:
 # Each exact grant includes the authorized control bytes, not merely its pathname/hash.
 grants:tuple[Grant,...]

def authorize(policy,job,grant,observed_uid):
 if policy is None or grant is None:raise Refusal('missing_authority')
 if type(policy) is not Policy or type(job) is not Job or type(grant) is not Grant:raise Refusal('invalid_authority')
 if type(policy.grants) is not tuple or any(type(g) is not Grant for g in policy.grants):raise Refusal('invalid_authority')
 for x in (job.revision,job.executor_uid,grant.revision,grant.issuer_uid,observed_uid):
  if type(x) is not int or x<0 or x.bit_length()>64:raise Refusal('invalid_authority')
 if any(type(x) is not str or not x or len(x)>128 for x in (job.task,job.spec,grant.task,grant.spec)):raise Refusal('invalid_authority')
 if type(grant.control) is not bytes:raise Refusal('invalid_authority')
 if len(grant.control)>CAP:raise Refusal('resource_limit')
 if grant not in policy.grants:raise Refusal('unauthorized_grant')
 if observed_uid!=grant.issuer_uid:raise Refusal('unauthorized_source')
 if grant.issuer_uid==job.executor_uid:raise Refusal('executor_self_assignment')
 if grant.task!=job.task:raise Refusal('task_mismatch')
 if grant.revision!=job.revision:raise Refusal('stale_revision')
 if grant.spec!=job.spec or job.spec!=SPEC:raise Refusal('spec_mismatch')
 return grant.control

def snapshot(policy,job,grant,directory_fd,name):
 """Open relative to a caller-owned directory handle; never reread the path.
 Exact byte pinning is a source-approval policy, NOT rational semantic equality.
 Equivalent request representations remain the native decoder's responsibility.
 """
 if type(name)is not str or not name or name in ('.','..') or '/' in name or '\0' in name:raise Refusal('invalid_source')
 if grant is None:raise Refusal('missing_authority')
 ds=os.fstat(directory_fd)
 if not stat.S_ISDIR(ds.st_mode) or ds.st_uid!=grant.issuer_uid or ds.st_mode&0o022:raise Refusal('unsafe_directory')
 fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory_fd)
 try:
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode) or before.st_mode&0o022:raise Refusal('unsafe_source')
  expected=authorize(policy,job,grant,before.st_uid)
  if before.st_size>CAP:raise Refusal('resource_limit')
  data=b''
  while len(data)<=CAP:
   chunk=os.read(fd,min(4096,CAP+1-len(data)))
   if not chunk:break
   data+=chunk
  after=os.fstat(fd)
  if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise Refusal('source_changed')
  if len(data)>CAP:raise Refusal('resource_limit')
  if data!=expected:raise Refusal('context_mismatch')
  sealed=os.memfd_create('simlab-authorized-context',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
  try:
   view=memoryview(data)
   while view:
    n=os.write(sealed,view)
    if n<=0:raise Refusal('snapshot_write_failed')
    view=view[n:]
   os.lseek(sealed,0,os.SEEK_SET)
   fcntl.fcntl(sealed,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
   return sealed
  except BaseException:
   os.close(sealed);raise
 finally:os.close(fd)

def authorized_peer(job,peer):
 """Authenticate a connected Unix socket's peer using Linux SO_PEERCRED.
 The caller must connect this same socket to the downstream request channel.
 """
 if peer.family!=socket.AF_UNIX:raise Refusal('invalid_peer')
 _,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
 if uid!=job.executor_uid:raise Refusal('unauthorized_executor')
 return uid

def launch(policy,job,grant,directory_fd,name,peer,exe,budget=1024):
 """Start trusted native gate with immutable approved bytes and the SAME peer socket.
 Caller is a trusted supervisor. No request-controlled executable or policy path.
 No pretense that this function authenticates the supervisor itself.
 """
 if type(budget)is not int or not 0<=budget<=1024:raise Refusal('resource_limit')
 authorized_peer(job,peer)
 fd=snapshot(policy,job,grant,directory_fd,name)
 try:
  return subprocess.Popen([str(exe),'--context',f'/proc/self/fd/{fd}','--budget',str(budget)],stdin=peer,stdout=peer,stderr=subprocess.PIPE,pass_fds=(fd,))
 finally:os.close(fd)
