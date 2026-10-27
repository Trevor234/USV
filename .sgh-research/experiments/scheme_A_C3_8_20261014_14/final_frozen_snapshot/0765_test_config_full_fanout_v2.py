#!/usr/bin/python3
"""Close the two-field nominal stored-population negative coverage explicitly."""
from pathlib import Path
import argparse,hashlib,json,shutil,sqlite3,sys
sys.dont_write_bytecode=True
N=Path(__file__).resolve().parent
sys.path[:0]=[str(N),str(N/'runtime')]
import check_config_identity_v1 as identity
import consolidate_current_v5 as current
import test_config_and_current_v5 as cases

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 c,_,_=identity.imports();_,_,safe,_,fc=current.imports();base=Path(c['original_run'])
 before=cases.tree_hash(base)
 root=N/'validation_copies'/a.output.parent.name/'full_fanout_two_field_forgery'
 root.parent.mkdir(exist_ok=False);shutil.copytree(base,root);p=cases.paths(root,c);(root/'external').mkdir()
 for key,pin in c['record_files'].items():
  if not Path(pin['path']).is_relative_to(base):shutil.copy2(pin['path'],p[key])
 inherited=cases.fake_all(p,root)
 from rclpy.serialization import deserialize_message,serialize_message
 from rosidl_runtime_py.utilities import get_message
 fake='a'*64
 def replace_claims(msg):
  changed=0
  if not hasattr(msg,'get_fields_and_field_types'):return 0
  for key in msg.get_fields_and_field_types():
   if key in ('nominal_hash','nominal_config_hash'):
    setattr(msg,key,fake);field_counts[key]=field_counts.get(key,0)+1;changed+=1
   else:
    value=getattr(msg,key)
    if isinstance(value,(list,tuple)):
     changed+=sum(replace_claims(v) for v in value)
    else:changed+=replace_claims(value)
  return changed
 db=sqlite3.connect(root/'recorder/bag/bag_0.db3');counts={};field_counts={}
 for tid,name,typ in db.execute('SELECT id,name,type FROM topics').fetchall():
  cls=get_message(typ)
  for mid,blob in db.execute('SELECT id,data FROM messages WHERE topic_id=?',(tid,)).fetchall():
   msg=deserialize_message(blob,cls)
   if not replace_claims(msg):continue
   db.execute('UPDATE messages SET data=? WHERE id=?',(serialize_message(msg),mid));counts[name]=counts.get(name,0)+1
 db.commit();db.close()
 expected={'/p1/solve_job':23,'/p1/solve_candidate':23,'/p1/worker_capability':52,'/research/reference_prediction':22}
 assert counts==expected and sum(counts.values())==120,(counts,field_counts)
 mutated=cases.tree_hash(root);s=identity.load_data(root)
 def claims(q):
  if isinstance(q,dict):return [v for k,v in q.items() if k in ('nominal_hash','nominal_config_hash')]+sum([claims(v) for k,v in q.items() if k not in ('nominal_hash','nominal_config_hash')],[])
  if isinstance(q,list):return sum([claims(v) for v in q],[])
  return []
 for topic,wanted in expected.items():
  population=s['typed']['decoded'][topic];assert len(population)==wanted
  assert all(claims(x['message']) and all(v==fake for v in claims(x['message'])) for x in population)
 report=identity.analyze(s,fc);codes=[i['code'] for g in report['components'].values() for i in g['issues']]
 assert not report['passed'] and 'nominal_byte_identity' in codes and report['original_authenticity_qualified'] is False
 unchanged=before==cases.tree_hash(base) and mutated==cases.tree_hash(root);assert unchanged
 result={'schema':'p1-complete-stored-nominal-fanout-negative-v2','passed':True,'additional_causal_negative_cases':1,
  'fresh_whole_run_copy':str(root),'original_run_and_copy_unchanged_during_validation':True,
  'prior_case_retained_with_explicit_coverage_limit':{'stored_messages_changed':75,'missing_alternate_field_messages':22,'missing_nested_job_field_messages':23},
  'document_claim_positions_changed':inherited['document_claims_changed'],'complete_stored_claim_population':counts,
  'stored_claim_messages':120,'stored_field_counts':field_counts,'both_nominal_field_names_handled':True,
  'independent_nominal_preimage_unchanged':True,'observed_semantic_codes':sorted(set(codes)),
  'identity_report':report,'original_authenticity_qualified':False,'strict_readiness_passed':False,'D1':False,'execute':False}
 safe.create_only(a.output,result)
 print(json.dumps({'passed':True,'stored_claim_messages':120,'field_counts':field_counts,'strict_readiness_passed':False}))
 return 0
if __name__=='__main__':raise SystemExit(main())
