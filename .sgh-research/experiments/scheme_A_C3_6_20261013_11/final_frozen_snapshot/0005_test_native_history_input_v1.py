#!/usr/bin/env python3
"""Exercise the actual native stdin decoder with semantic type/boundary cases."""
import copy,hashlib,json,pathlib,subprocess
N=pathlib.Path(__file__).resolve().parent.parent
D=N.parent.parent/'scheme_A_C3_6_20261013_11'
B=D/'component/attempt03/test_command_anchor_v1'
def main():
 out=D/'negatives/native_input_v1';out.mkdir(exist_ok=False)
 before=hashlib.sha256(B.read_bytes()).hexdigest()
 a={'n':[0.,0.],'sequence':[1,1],'publish_ns':[1000,2000],'known':[True,True]}
 base=[{'job_id':1,'expected':a,'actual':copy.deepcopy(a),'history':[{'channel':ch,'sequence':1,'publish_ns':a['publish_ns'][ch],'n':0.,'known':True} for ch in (0,1)]}]
 cases=[]
 for name in ['positive','sequence_bool','sequence_float','sequence_negative','sequence_uint64_overflow','time_int64_overflow','known_number','command_bool','nonfinite_number','extra_field','duplicate_key','empty_population']:
  x=copy.deepcopy(base)
  if name=='sequence_bool':x[0]['expected']['sequence'][0]=True
  elif name=='sequence_float':x[0]['expected']['sequence'][0]=1.25
  elif name=='sequence_negative':x[0]['expected']['sequence'][0]=-1
  elif name=='sequence_uint64_overflow':x[0]['expected']['sequence'][0]=1<<64
  elif name=='time_int64_overflow':x[0]['expected']['publish_ns'][0]=1<<63
  elif name=='known_number':x[0]['expected']['known'][0]=1
  elif name=='command_bool':x[0]['expected']['n'][0]=True
  elif name=='extra_field':x[0]['extra']=True
  elif name=='empty_population':x=[]
  raw=json.dumps(x,sort_keys=True,allow_nan=False).encode()
  if name=='nonfinite_number':raw=raw.replace(b'0.0',b'1e309',1)
  if name=='duplicate_key':raw=raw.replace(b'"job_id": 1',b'"job_id": 1, "job_id": 1',1)
  with (out/(name+'.input.json')).open('xb') as f:f.write(raw)
  r=subprocess.run([str(B),'--history'],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
  with (out/(name+'.stdout')).open('xb') as f:f.write(r.stdout)
  with (out/(name+'.stderr')).open('xb') as f:f.write(r.stderr)
  passed=r.returncode==(0 if name=='positive' else 2)
  if name=='positive':passed=passed and json.loads(r.stdout)==[{'job_id':1,'reason':''}]
  cases.append({'case':name,'returncode':r.returncode,'expected_rejection':name!='positive','passed':passed})
 result={'schema':'p1-C3.6-A-native-history-decoder-tests/v1','passed':all(x['passed'] for x in cases),'count':len(cases),'negative_count':len(cases)-1,'cases':cases,'binary_sha256':before,'binary_unchanged':hashlib.sha256(B.read_bytes()).hexdigest()==before,'source_data':'synthetic decoder-boundary inputs','actual_actuator_publish':False,'stage_qualified':False}
 with (out/'result.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps(result))
 if not result['passed'] or not result['binary_unchanged']:raise ValueError('native_decoder_test_failed')
if __name__=='__main__':main()
