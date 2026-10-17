"""Test-only inherited SQLBT1 reader/encoder; no acceptance authority."""
def decode(raw):
 if not raw.startswith(b'SQLBT\x01') or len(raw)>2*1024**2:raise ValueError('version_or_size')
 pos=6
 def take(n):
  nonlocal pos
  if pos+n>len(raw):raise ValueError('truncated')
  v=raw[pos:pos+n];pos+=n;return v
 def word():return int.from_bytes(take(2),'big')
 def text():return take(word()).decode('utf-8','strict')
 def node(depth):
  if depth>12:raise ValueError('depth')
  k=take(1)[0]
  if k==0:return None
  if k==1:return False
  if k==2:return True
  if k==3:raise ValueError('unexpected number in response')
  if k==4:return text()
  if k==5:return [node(depth+1)for _ in range(word())]
  if k==6:
   result={}
   for _ in range(word()):
    key=text()
    if key in result:raise ValueError('duplicate')
    result[key]=node(depth+1)
   return result
  raise ValueError('tag')
 obj=node(0)
 if pos!=len(raw):raise ValueError('trailing')
 return obj

def encode(obj):
 def word(n):return n.to_bytes(2,'big')
 def text(s):b=s.encode();return word(len(b))+b
 def node(o):
  if o is None:return b'\x00'
  if type(o)is bool:return b'\x02'if o else b'\x01'
  if type(o)is str:return b'\x04'+text(o)
  if type(o)is list:return b'\x05'+word(len(o))+b''.join(node(v)for v in o)
  if type(o)is dict:return b'\x06'+word(len(o))+b''.join(text(k)+node(v)for k,v in o.items())
  raise TypeError('unsupported')
 return b'SQLBT\x01'+node(obj)
