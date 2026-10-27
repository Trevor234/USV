"""Pure notice/cursor negatives and real Linux owned-child cleanup; no ROS nodes."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(D/'author'),str(D/'author/runtime')]
from supervision_bridge_v1 import SourceCursor,validate_notice
from owned_process_supervisor import Supervisor,sha256_file


def need(v,w):
 if not v:raise AssertionError(w)


def main():
 P=D.parent/'scheme_A_V2_watchdog_lease_20261019_35/author_r3/runs/v2_active_r3_05'
 records=[json.loads(x) for x in (P/'observer/source.jsonl').read_bytes().splitlines()]
 om=json.loads((P/'observer/owned_manifest.json').read_bytes());wm=json.loads((P/'worker/owned_manifest.json').read_bytes())
 result=json.loads((P/'result.json').read_bytes())
 expected={'run_id':om['run_id'],'boot_id':om['boot_id'],'observer_pid':om['pid'],'contract_sha256':om['contract_sha256'],
           'worker_pid':wm['pid'],'worker_instance':wm['worker_instance'],'prepare_start_ns':result['prepare_start_ns']}
 need(validate_notice(records,expected)['cause']=='active_watchdog','frozen active Source example')
 rejected=[]
 for key,value in [('run_id','wrong'),('boot_id','wrong'),('observer_pid',1),('contract_sha256','0'*64),
                   ('worker_pid',1),('worker_instance','wrong'),('prepare_start_ns',time.monotonic_ns()+1)]:
  bad=dict(expected);bad[key]=value
  try:validate_notice(records,bad)
  except ValueError as e:rejected.append({'case':key,'reason':str(e)})
  else:raise AssertionError('invalid notice context accepted:'+key)
 for case in ['missing_causal_link','unknown_cause','duplicate_terminal','invalidated_work_present']:
  bad=deepcopy(records)
  terminal=next(r for r in bad if r.get('type')=='worker_unusable_transition')
  if case=='missing_causal_link':bad=[r for r in bad if r.get('type')!='legacy_ready_invalidated']
  elif case=='unknown_cause':terminal['reason']='unrelated:active_watchdog'
  elif case=='duplicate_terminal':bad.append(deepcopy(terminal))
  else:terminal['pending_after']=True
  try:validate_notice(bad,expected)
  except ValueError as e:rejected.append({'case':case,'reason':str(e)})
  else:raise AssertionError('invalid terminal accepted:'+case)
 cursor_dir=D/'component_runs/source_cursor';cursor_dir.mkdir()
 p=cursor_dir/'source.jsonl';p.write_bytes(b'{"type":"test"}')
 st=p.stat();identity={'device':st.st_dev,'inode':st.st_ino}
 cursor=SourceCursor(p,identity)
 try:
  need(cursor.poll()==[],'unterminated row must not be accepted')
  with p.open('ab') as f:f.write(b'\n')
  need(cursor.poll()==[{'type':'test'}],'actual completed row')
  p.rename(cursor_dir/'source_retained.jsonl');p.write_bytes(b'{"forged":true}\n')
  try:cursor.poll()
  except ValueError:rejected.append({'case':'Source_path_replaced','reason':'descriptor/path inode mismatch'})
  else:raise AssertionError('replaced source path accepted')
 finally:cursor.close()
 exe=Path('/usr/bin/python3').resolve();actual=[]
 for name,kind,expected_signal in [('graceful','graceful',2),('TERM','term',15),('KILL','kill',9)]:
  root=D/'component_runs'/name;root.mkdir()
  ready=root/'ready';code='import signal,time,pathlib\n'
  if kind in ['term','kill']:code+='signal.signal(signal.SIGINT,signal.SIG_IGN)\n'
  if kind=='kill':code+='signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
  code+='pathlib.Path('+repr(str(ready))+').write_text("ready")\ntime.sleep(20)\n'
  sup=Supervisor(root)
  try:
   child=sup.spawn('unit_child',[str(exe),'-c',code],dict(os.environ),exe,sha256_file(exe))
   until=time.monotonic()+2
   while not ready.exists() and time.monotonic()<until:time.sleep(.005)
   need(ready.exists(),'unit child did not enter controlled state')
   cleanup=sup.stop(child,.05,.1,.3)
   count=len([r for r in sup.memory_tail if r['type']=='signal_call_result'])
   need(sup.stop(child,.05,.1,.3)==cleanup,'idempotent stop')
   need(count==len([r for r in sup.memory_tail if r['type']=='signal_call_result']),'idempotent stop emitted a new signal')
   calls=[r for r in sup.memory_tail if r['type']=='signal_call_result']
   need(calls[-1]['signal']==expected_signal and all(r['returned'] for r in calls),'actual expected terminating signal')
   need(cleanup['cleanup_complete'] and cleanup['remaining_members']==[],'real child group not empty')
   actual.append({'case':name,'passed':True,'actual_signal_sequence':[r['signal'] for r in calls],
                  'returncode':cleanup['returncode'],'qualification_clean':cleanup['qualification_clean'],
                  'resource_cleanup_complete':True,'ROS_node_started':False})
  finally:
   for item in sup.owned.values():
    if item.cleanup is None:sup.stop(item,.05,.1,.3)
   sup.close()
 out={'passed':True,'notice_frozen_positive_case':True,'notice_and_cursor_rejected':len(rejected),'negative_cases':rejected,
      'real_owned_child_cases':actual,'component_children_are_not_ROS_experiments':True,
      'child_executable':str(exe),'child_executable_sha256':sha256_file(exe),
      'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 with (D/'verification/supervision_components_v1.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True)
 print(json.dumps({'passed':True,'rejected':len(rejected),'real_owned_child_cases':len(actual)}))


if __name__=='__main__':main()
