from pathlib import Path
import hashlib,json,math
SPEC_SHA256='ad15bcbb6e86fbd4b2127387663923e9ef0e7c46b7e66ac43ee66cc7e60bdeb4'
def validate(c):
 p=Path(__file__).with_name('cold_start_contract_spec_v1.json');raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SPEC_SHA256:raise ValueError('cold-start spec identity')
 spec=json.loads(raw);expected=spec['legacy_baseline'];integer_keys=set(spec['integer_keys'])
 def equal(a,b,key=""):
  if isinstance(b,dict):return type(a) is dict and set(a)==set(b) and all(equal(a[k],b[k],k) for k in b)
  if isinstance(b,list):return type(a) is list and len(a)==len(b) and all(equal(x,y,key) for x,y in zip(a,b))
  if type(b) is bool:return type(a) is bool and a==b
  if type(b) is int:return (type(a) is int if key in integer_keys else type(a) in (int,float)) and a==b
  if type(b) is float:return type(a) in (int,float) and math.isfinite(a) and a==b
  return type(a) is type(b) and a==b
 if not equal(c,expected):raise ValueError('exact revision9 cold-start profile required')
 return c
