"""Independent actual-storage accounting for preregistered negative runs."""
from pathlib import Path
import argparse, hashlib, json
from collections import Counter
import yaml, rosbag2_py
from check_owned_fixture import load_json, load_jsonl, analyze_inputs
from owned_release import create_only_json
N=Path(__file__).resolve().parent
PHYSICAL=['/wamv/thrusters/left/thrust','/wamv/thrusters/right/thrust']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def scan(bag):
 meta=yaml.safe_load((bag/'metadata.yaml').read_text())['rosbag2_bagfile_information']
 expected={x['topic_metadata']['name']:x['message_count'] for x in meta['topics_with_message_count']}
 if len(expected)!=len(meta['topics_with_message_count']):raise ValueError('duplicate metadata topic')
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id=meta['storage_identifier']),rosbag2_py.ConverterOptions(input_serialization_format='cdr',output_serialization_format='cdr'))
 counts={x.name:0 for x in reader.get_all_topics_and_types()};total=0;size=0;h=hashlib.sha256()
 while reader.has_next():
  topic,blob,stamp=reader.read_next();total+=1;size+=len(blob)
  if total>20000 or size>128*1024*1024:raise ValueError('storage budget exceeded')
  counts[topic]+=1;raw=topic.encode();h.update(len(raw).to_bytes(4,'big'));h.update(raw);h.update(len(blob).to_bytes(8,'big'));h.update(blob)
 if counts!=expected or total!=meta['message_count']:raise ValueError('actual full storage counts differ from metadata')
 return {'counts':counts,'messages':total,'cdr_bytes':size,'ordinal_framed_cdr_sha256':h.hexdigest(),'metadata_conserved':True}
def analyze(name):
 r=N/'runs'/name;result=load_json(r/'result.json');mode=result['mode'];issues=[];read_error=None;storage=None
 try:storage=scan(r/'recorder/bag')
 except Exception as e:read_error=type(e).__name__+': '+str(e)
 receipt_absent=not (r/'publisher/release_receipt.json').exists()
 if not result.get('held_negative_passed') or not result.get('expected_negative_rejection'):issues.append('negative trigger absent')
 if not result.get('resource_cleanup_complete',result.get('cleanup_complete')):issues.append('owned resources remain')
 if result.get('elapsed_ns',60_000_000_001)>60_000_000_000 or not result.get('cleanup_within_budget'):issues.append('declared runtime budget exceeded')
 if mode=='recorder_drain_failure':
  if result.get('evidence_qualification_clean') is not False or result.get('passed') is not False:issues.append('failed drain improperly qualified')
  if (r/'recorder/terminal.json').exists():issues.append('killed recorder unexpectedly has normal terminal')
  try:chain=analyze_inputs(load_json(r/'checker_inputs.json'));rejected=not chain['passed'];chain_error=None
  except Exception as e:rejected=True;chain_error=type(e).__name__+': '+str(e)
  if not rejected:issues.append('incomplete close incorrectly accepted by actual reader')
  return {'run':name,'mode':mode,'passed':not issues,'issues':issues,'resource_cleanup_complete':result['resource_cleanup_complete'],'evidence_qualification_clean':False,'actual_reader_rejected':rejected,'reader_error':read_error,'chain_error':chain_error,'storage':storage,'result_sha256':sha(r/'result.json')}
 if storage is None:issues.append('negative complete storage unreadable: '+str(read_error))
 elif any(storage['counts'].get(t,0)!=0 for t in PHYSICAL+['/research/control/applied']):issues.append('held negative has actual physical/Applied output')
 if not receipt_absent:issues.append('held negative accepted receipt')
 if (r/'synthetic_start.json').exists():issues.append('held negative activated synthetic sensors')
 session=load_json(r/'publisher/session_summary.json')
 if not session.get('normal_end') or not session.get('flushed') or session.get('publish_errors')!=0 or session.get('queue_dropped_total')!=0:issues.append('held publisher close not normal')
 if set(session.get('streams',{}))!={'applied','cycle','reference_prediction','state'} or any(v.get(k)!=0 for v in session.get('streams',{}).values() for k in ['generated','emitted','dropped']):issues.append('held publisher full stream count not zero')
 ledger=load_jsonl(r/'owned_process_ledger.jsonl')
 if any(x['type'] in ['owned_descendant_observed','launch_identity_missing','launch_group_invalid'] for x in ledger):issues.append('negative unexpected child identity')
 for event in ledger:
  if event['type']=='spawn':
   i=event['identity'];p=Path('/proc')/str(i['pid'])
   if p.exists():
    fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    if int(fields[19])==i['start_ticks']:issues.append('owned identity still alive')
 if mode in ['expired_release','duplicate_release']:
  if not result.get('expired_release_no_receipt') or sha(r/'release.json')!=result.get('expired_fixture_release_sha256'):issues.append('expired release state not preserved')
  if mode=='duplicate_release' and not result.get('duplicate_release_bytes_unchanged'):issues.append('duplicate overwrite not excluded')
 elif (r/'release.json').exists():issues.append('failed prepare created release')
 if mode=='prepare_io_ambiguous':
  state=result.get('publication_ambiguous',{})
  if state.get('target_visible') is not True or sha(state['path'])!=state.get('content_sha256') or result.get('evidence_qualification_clean') is not False:issues.append('IO ambiguous falsely marked absent/clean')
 return {'run':name,'mode':mode,'passed':not issues,'issues':issues,'storage':storage,'publisher_all_streams_zero':not any(v['generated'] for v in session['streams'].values()),'actual_physical_and_Applied_zero':storage is not None and not any(storage['counts'].get(t,0) for t in PHYSICAL+['/research/control/applied']),'release_receipt_absent':receipt_absent,'resource_cleanup_complete':result.get('resource_cleanup_complete',result['cleanup_complete']),'evidence_qualification_clean':result.get('evidence_qualification_clean'),'result_sha256':sha(r/'result.json'),'session_sha256':sha(r/'publisher/session_summary.json')}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 rows=[]
 for run in a.runs:
  try:rows.append(analyze(run))
  except Exception as e:rows.append({'run':run,'passed':False,'error':type(e).__name__+': '+str(e)})
 report={'schema':'p1-owned-negative-actual-storage-v3','passed':all(x['passed'] for x in rows),'cases':rows,'checker_sha256':sha(__file__),'shared_v2_full_chain_qualified':False,'D1_dynamic_qualified':False,'execute_qualified':False}
 create_only_json(a.output,report);print(json.dumps({'passed':report['passed'],'cases':len(rows),'issues':[{k:v for k,v in x.items() if k in ['run','issues','error']} for x in rows],'output':str(a.output)},indent=2));return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
