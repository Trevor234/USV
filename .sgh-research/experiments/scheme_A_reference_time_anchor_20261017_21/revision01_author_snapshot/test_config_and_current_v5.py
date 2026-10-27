#!/usr/bin/python3
"""Fresh whole-run causal copies; never change or repin authenticated originals."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sqlite3,sys
sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
sys.path[:0]=[str(N),str(N/'runtime')]
import check_config_identity_v1 as identity
import consolidate_current_v5 as current

C1=[
 ('missing_mass','nominal_vehicle_field_set'),('extra_vehicle','nominal_vehicle_field_set'),
 ('bool_mass','nominal_source_numeric_type'),('string_mass','nominal_source_numeric_type'),
 ('nonfinite_mass','strict_input_load_error'),('changed_mass','nominal_byte_identity'),
 ('negative_zero_Nv','nominal_byte_identity'),('asymmetric_cross_terms','nominal_byte_identity'),
 ('changed_thruster','nominal_byte_identity'),('fake_all_nominal_claims','nominal_byte_identity'),
 ('F5_effective_hash','F5_effective_nominal_identity'),('live_model_value','actual_vehicle_nominal_differs'),
 ('live_model_integer_type','actual_vehicle_nominal_differs'),('wrong_live_canonical','actual_parameter_canonical'),
 ('dynamic_Q','solver_effective_contract_differs'),('horizon','solver_effective_contract_differs'),
 ('contract_dt','solver_effective_contract_differs'),('capability_payload_hash','whole_nominal_fanout_differs'),
 ('changed_fingerprint','independent_cpp_reference_fingerprint'),('known_raw_path_value','independent_cpp_reference_fingerprint'),
 ('unknown_raw_profile_bits','unqualified_float_bits'),('raw_cdr_hash','fingerprint_raw_cdr_identity')]
C2=[
 ('nonzero_worker_hook','nonzero_or_wrong_type_hook'),('tail_coherent_missing_pair','tail_ack_entire_declared_output_population'),
 ('tail_wrong_driver','tail_ack_driver_identity'),('tail_receiver_dead','tail_ack_receiver_alive_population'),
 ('unknown_worker_event','unknown_or_failure_worker_source_event'),('missing_legacy_ready','exactly_one_event_required'),
 ('immutable_job_changed','immutable_job_pipeline_payload_differs'),('ready_executor_false','ready_schema_callback_flags'),
 ('ready_history_changed','ready_complete_held_history_replay')]

def save(p,q):
 with p.open('x') as f:json.dump(q,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def tree_hash(root):
 return {str(p.relative_to(root)):identity.sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
def read(p):
 return [json.loads(x) for x in p.read_text().splitlines()] if p.suffix=='.jsonl' else json.loads(p.read_text())
def write(p,q,nonfinite=False):
 if p.suffix=='.jsonl':p.write_text(''.join(json.dumps(x,sort_keys=True,allow_nan=nonfinite)+'\n' for x in q))
 else:p.write_text(json.dumps(q,sort_keys=True,indent=2,allow_nan=nonfinite)+'\n')
def paths(root,c):
 base=Path(c['original_run'])
 return {k:root/Path(v['path']).relative_to(base) if Path(v['path']).is_relative_to(base) else root/'external'/k for k,v in c['record_files'].items()}
def coherent_parameter(p,role,name,value,kind=None):
 live=read(p['live_'+role]);owned=read(p['owned_'+role])
 row=copy.deepcopy(live[name]);row['value']=value
 if kind is not None:row['type']=kind
 row['canonical_value']=identity.bits(value) if row['type']==3 else [identity.bits(x) for x in value] if row['type']==8 else value
 live[name]=copy.deepcopy(row);owned['effective_parameters'][name]=copy.deepcopy(row)
 owned['effective_parameters_sha256']=identity.parameter_digest(owned['effective_parameters'])
 write(p['live_'+role],live);write(p['owned_'+role],owned)
def bind_copy_contract(p):
 q=read(p['run_inputs']);q['contract']=str(p['contract']);q['contract_sha256']=identity.sha(p['contract'].read_bytes());write(p['run_inputs'],q)
def edit_raw(row,which):
 from rclpy.serialization import deserialize_message,serialize_message
 from rosidl_runtime_py.utilities import get_message
 raw=row['raw_input'];msg=deserialize_message(bytes.fromhex(raw['cdr_hex']),get_message(raw['message_type']))
 if which=='path':msg.poses[0].pose.position.x=1.0
 else:msg.data[0]=3.1415926
 blob=serialize_message(msg);raw.update(cdr_hex=blob.hex(),cdr_sha256=identity.sha(blob),cdr_bytes=len(blob))
def fake_all(p,root):
 fake='a'*64;count=0
 def visit(q):
  nonlocal count
  if type(q) is dict:
   for k,v in q.items():
    if k in ('nominal_hash','nominal_config_hash'):q[k]=fake;count+=1
    elif k=='research_nominal_config_hash':
     if type(v) is dict:v['value']=v['canonical_value']=fake
     else:q[k]=fake
     count+=1
    else:visit(v)
  elif type(q) is list:
   for v in q:visit(v)
 for key,path in p.items():
  if key in ('nominal_source','nominal_f5_source'):continue
  q=read(path);visit(q)
  if key.startswith('owned_') and 'effective_parameters' in q:q['effective_parameters_sha256']=identity.parameter_digest(q['effective_parameters'])
  write(path,q)
 # All four stored nominal-claim populations, not only JSON headers.
 from rclpy.serialization import deserialize_message,serialize_message
 from rosidl_runtime_py.utilities import get_message
 db=sqlite3.connect(root/'recorder/bag/bag_0.db3');stored=0
 for tid,typ in db.execute('SELECT id,type FROM topics').fetchall():
  cls=get_message(typ)
  for mid,blob in db.execute('SELECT id,data FROM messages WHERE topic_id=?',(tid,)).fetchall():
   msg=deserialize_message(blob,cls)
   if hasattr(msg,'nominal_hash'):
    msg.nominal_hash=fake;db.execute('UPDATE messages SET data=? WHERE id=?',(serialize_message(msg),mid));stored+=1
 db.commit();db.close();bind_copy_contract(p)
 return {'document_claims_changed':count,'stored_typed_nominal_claims_changed':stored,
         'independent_nominal_preimage_unchanged':True,'no_original_or_contract_repin':True}
def mutate(name,p,root):
 details={}
 if name in ('missing_mass','extra_vehicle','bool_mass','string_mass','nonfinite_mass','changed_mass','negative_zero_Nv','asymmetric_cross_terms','changed_thruster'):
  q=read(p['nominal_source']);v=q['/**']['ros__parameters']['vehicle'];t=q['/**']['ros__parameters']['thruster']
  if name=='missing_mass':del v['mass']
  elif name=='extra_vehicle':v['unknown']=0.0
  elif name=='bool_mass':v['mass']=True
  elif name=='string_mass':v['mass']='14.3'
  elif name=='nonfinite_mass':v['mass']=float('nan')
  elif name=='changed_mass':v['mass']+=1.0
  elif name=='negative_zero_Nv':
   assert v['Nv']==0.0 and identity.bits(float(v['Nv']))=='0000000000000000';v['Nv']=-0.0
  elif name=='asymmetric_cross_terms':v['Yr_dot']=-0.3;v['Nv_dot']=-0.1
  elif name=='changed_thruster':t['T_max_forward']=30.0
  write(p['nominal_source'],q,name=='nonfinite_mass')
 elif name=='fake_all_nominal_claims':details=fake_all(p,root)
 elif name=='F5_effective_hash':
  q=read(p['f5_parameters']);q['f5_actual_parameters']['research_nominal_config_hash']='b'*64;write(p['f5_parameters'],q)
 elif name=='live_model_value':coherent_parameter(p,'publisher','vehicle.mass',15.3)
 elif name=='live_model_integer_type':coherent_parameter(p,'publisher','vehicle.mass',14,2)
 elif name=='wrong_live_canonical':
  q=read(p['live_publisher']);q['vehicle.mass']['canonical_value']='0'*16;write(p['live_publisher'],q)
 elif name=='dynamic_Q':
  q=read(p['live_publisher'])['dynamic.Q']['value'];q[0]+=1.0;coherent_parameter(p,'publisher','dynamic.Q',q)
 elif name=='horizon':coherent_parameter(p,'publisher','horizon',21)
 elif name=='contract_dt':
  q=read(p['contract']);q['dt']=0.3;write(p['contract'],q);bind_copy_contract(p)
 elif name=='capability_payload_hash':
  q=read(p['worker_source']);next(x for x in q if x['type']=='capability_publish_attempt')['payload']['nominal_hash']='c'*64;write(p['worker_source'],q)
 elif name in ('changed_fingerprint','known_raw_path_value','unknown_raw_profile_bits','raw_cdr_hash'):
  q=read(p['observer_source']);typ='profile_version' if name=='unknown_raw_profile_bits' else 'path_version';row=next(x for x in q if x['type']==typ)
  if name=='changed_fingerprint':row['fingerprint']='f'*64
  elif name=='raw_cdr_hash':row['raw_input']['cdr_sha256']='e'*64
  else:edit_raw(row,'profile' if name=='unknown_raw_profile_bits' else 'path')
  write(p['observer_source'],q)
 elif name=='nonzero_worker_hook':coherent_parameter(p,'worker','test_delay_ms',1)
 elif name.startswith('tail_'):
  q=read(p['close_tail_ack'])
  if name=='tail_coherent_missing_pair':
   topic='/research/control/applied';q['expected_counts'][topic]-=1;q['transport_counts'][topic]-=1
  elif name=='tail_wrong_driver':q['driver_identity']['pid']+=1
  elif name=='tail_receiver_dead':q['receiver_roles_alive']=False
  write(p['close_tail_ack'],q)
 elif name=='unknown_worker_event':
  q=read(p['worker_source']);q.insert(-1,{'type':'unknown_worker_event'});q[-1]['source_rows_before_terminal']+=1;q[-1]['source_rows_emitted_before_terminal']+=1;write(p['worker_source'],q)
 elif name in ('missing_legacy_ready','ready_executor_false','ready_history_changed'):
  q=read(p['observer_source']);ready=next(x for x in q if x['type']=='legacy_ready')
  if name=='missing_legacy_ready':q.remove(ready);q[-1]['generated']-=1;q[-1]['emitted']-=1
  elif name=='ready_executor_false':ready['readiness']['executor_spinning']=False
  else:ready['readiness']['held_history'][0]['n']+=0.1
  write(p['observer_source'],q)
 elif name=='immutable_job_changed':
  q=read(p['worker_source']);next(x for x in q if x['type']=='job_received')['job']['frozen_state'][0]+=0.01;write(p['worker_source'],q)
 elif name=='whitespace_invariance':
  q=read(p['nominal_source']);p['nominal_source'].write_text(json.dumps(q,separators=(',',':'))+'\n')
 else:raise ValueError('unknown case: '+name)
 return details

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output-directory',type=Path,required=True);a=ap.parse_args();out=a.output_directory;out.mkdir(exist_ok=False)
 c,_,_=identity.imports();_,_,_,_,fc=current.imports();original=Path(c['original_run'])
 pinpaths={str(Path(x['path'])) for x in c['record_files'].values()}|{str(Path(x['path'])) for x in list(c['sealed_helpers'].values())+list(c['source_pins'].values())}
 pinpaths|={str(N/x) for x in ['check_config_identity_v1.py','consolidate_current_v5.py','validate_current_legacy_rules_v5.py','test_config_and_current_v5.py']}
 pins={p:identity.sha(Path(p).read_bytes()) for p in sorted(pinpaths)};before=tree_hash(original)
 copies=N/'validation_copies'/out.name;copies.mkdir(parents=True,exist_ok=False)
 results=[]
 for suite,cases in [('identity',C1),('current',C2),('invariance',[('whitespace_invariance',None)])]:
  for name,expected in cases:
   root=copies/name;shutil.copytree(original,root);p=paths(root,c);(root/'external').mkdir()
   for key,pin in c['record_files'].items():
    if not Path(pin['path']).is_relative_to(original):shutil.copy2(pin['path'],p[key])
   # Copies are independent writable regular files; no original aliases.
   assert all(p[k].stat().st_ino!=Path(v['path']).stat().st_ino or p[k].stat().st_dev!=Path(v['path']).stat().st_dev for k,v in c['record_files'].items())
   copybefore=tree_hash(root);details=mutate(name,p,root);mutated=tree_hash(root)
   if suite=='current':
    report=current.analyze(root);codes=[i['code'] for g in report['components'].values() for i in g.get('issues',[])]+[i['code'] for i in report['source_component_issues']];passed=report['component_suite_passed']
   else:
    try:report=identity.analyze(identity.load_data(root),fc);codes=[i['code'] for g in report['components'].values() for i in g['issues']];passed=report['passed']
    except ValueError as error:
     if name!='nonfinite_mass':raise
     report={'passed':False,'load_error':str(error),'negative_copy':str(root),'original_authenticity_qualified':False};codes=['strict_input_load_error'];passed=False
   unchanged=mutated==tree_hash(root)
   if expected is None:
    ok=passed and unchanged and report['components']['independent_nominal_byte_preimage']['raw_source_equals_canonical'] is False
   else:ok=not passed and expected in codes and unchanged
   assert report['original_authenticity_qualified'] is False
   result={'name':name,'suite':suite,'expected_semantic_code':expected,'observed_codes':sorted(set(codes)),
           'expected_outcome_observed':ok,'copy_unchanged_during_validation':unchanged,'copy':str(root),
           'changed_files':{k:{'before':copybefore.get(k),'after':v} for k,v in mutated.items() if copybefore.get(k)!=v},
           'details':details,'report':report,'stage_qualified':False}
   save(out/(name+'.json'),result);results.append({k:result[k] for k in ['name','suite','expected_semantic_code','observed_codes','expected_outcome_observed']})
   print(json.dumps(results[-1]),flush=True)
 original_unchanged=before==tree_hash(original) and all(identity.sha(Path(p).read_bytes())==v for p,v in pins.items())
 summary={'schema':'p1-config-current-causal-negative-suite-v1','passed':all(x['expected_outcome_observed'] for x in results) and original_unchanged,
          'negative_cases':len(C1)+len(C2),'identity_negative_cases':len(C1),'current_negative_cases':len(C2),'positive_semantic_invariance_cases':1,
          'results':results,'original_and_implementation_pins_unchanged':original_unchanged,'original_run_sha256':before,'immutable_pins':pins,
          'copy_authenticity_or_stage_qualified':False,'strict_readiness_passed':False,'D1':False,'execute':False}
 save(out/'summary.json',summary);return 0 if summary['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
