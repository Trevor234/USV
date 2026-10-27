"""Post hoc read-only source/Storage audit of the six interior empty ticks."""
from pathlib import Path
import hashlib,json,sqlite3
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
D=Path(__file__).resolve().parents[1]
N=D.parent/'p1_execution_architecture_20261005_01/authored_D1_reference_time_anchor_20261018_v21r2'
R=N/'runs/task_time_r02_s005_01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def need(b,why):
 if not b:raise ValueError(why)
def decode(raw,typ):return dict(message_to_ordereddict(deserialize_message(raw,get_message(typ))))
def stamp(kind,m):
 if kind=='path_version':return m['header']['stamp']['sec']*10**9+m['header']['stamp']['nanosec']
 return int(m['layout']['dim'][0]['label'].split(':')[1])*10**9+int(m['layout']['dim'][1]['label'].split(':')[1])
def main():
 report_path=D/'runs/s005_02/check_result.json';report=json.loads(report_path.read_text());before=report['input_sha256_after'];need(before==report['input_sha256_before'],'complete report raw hashes')
 for p,s in before.items():need(sha(p)==s,'locked raw bytes changed: '+p)
 need(report['inherited']['passed'] and report['owner_evidence']['passed'],'existing full source/storage/owner proofs required')
 observer=rows(R/'observer/source.jsonl');publisher=rows(R/'publisher/controlled_source.jsonl');stored={'/path/reference':[],'/path/reference_profile':[]};dbpins={}
 for db in sorted((R/'recorder/bag').glob('*.db3')):
  dbpins[str(db)]=sha(db);conn=sqlite3.connect('file:'+str(db)+'?mode=ro&immutable=1',uri=True);conn.execute('PRAGMA query_only=ON');topics={i:(n,t) for i,n,t in conn.execute('SELECT id,name,type FROM topics')}
  for tid,blob in conn.execute('SELECT topic_id,data FROM messages ORDER BY id'):
   topic,typ=topics[tid]
   if topic in stored:stored[topic].append(decode(blob,typ))
  conn.close()
 current={};versions=[];callbacks={};applied={};freezes={};begins={};jobs={}
 for index,r in enumerate(observer):
  kind=r['type']
  if kind in ['path_version','profile_version']:
   raw=r['raw_input'];blob=bytes.fromhex(raw['cdr_hex']);need(hashlib.sha256(blob).hexdigest()==raw['cdr_sha256'] and len(blob)==raw['cdr_bytes'],'whole callback CDR identity');m=decode(blob,raw['message_type']);need(m in stored[raw['topic']],'entire selected callback typed message exists in actual Storage')
   item=dict(kind=kind,source_index=index,sequence=r['received_sequence'],stamp_ns=stamp(kind,m),processed_ns=r['processed_ns'],raw_CDR_sha256=raw['cdr_sha256'],raw_callback_sequence=raw['callback_sequence'],valid=r['valid'],resource_valid=r['resource_valid']);current[kind]=item;versions.append(item)
  if kind=='controlled_phase_callback' and 'phase' in r:callbacks[r['phase']['tick']]=dict(source_index=index,row=r,pair=dict(current))
  if kind=='controlled_phase_applied':applied[r['sequence']]=dict(source_index=index,row=r,pair=dict(current))
  if kind=='controlled_phase_freeze':freezes[r['tick']]=r
  if kind=='controlled_phase_begin':begins[r['tick']]=r
  if kind=='job':jobs[r['job']['target_tick']]=r['job']
 phases={r['phase']['tick']:r for r in publisher if r['type']=='controlled_phase_emitted'}
 start=report['window']['start_ready_ns'];end=report['window']['end_driver_requested_ns'];decisions=[r for r in observer if r['type']=='decision' and start<=r['activation_commit_ns']<end];first_accept=next(r['tick'] for r in decisions if r['accepted']);gaps=[r for r in decisions if not r['accepted']];interior=[r for r in gaps if r['tick']>first_accept];need(len(gaps)==7 and len(interior)==6,'one initial empty tick and six interior gaps')
 evidence=[]
 for gap in interior:
  tick=gap['tick']-1;entry=callbacks[tick];callback=entry['row'];phase=callback['phase'];pair=entry['pair'];pub=phases[tick];ap=applied[phase['applied_sequence']]
  need(gap['reason']=='no_candidate' and gap['job_id']==0 and tick not in freezes and gap['tick'] not in jobs,'entire Source has no frozen/submitted Job for empty target tick')
  need(callback['accepted'] is True and callback['reason']=='' and callback['authentication_reason']=='','phase actually authenticated and accepted')
  need(ap['row']['reason']=='' and ap['source_index']<entry['source_index'],'actual matching Applied was admitted before phase')
  need(pair['path_version']['stamp_ns']!=pair['profile_version']['stamp_ns'],'phase retry observed incomplete path/profile pair')
  need(pair['profile_version']['sequence']==pair['path_version']['sequence']+1,'actual profile first, older path still selected')
  repaired=next(v for v in versions if v['source_index']>entry['source_index'] and v['kind']=='path_version' and v['stamp_ns']==pair['profile_version']['stamp_ns'])
  need(repaired['valid'] and repaired['resource_valid'] and callback['processed_ns']<repaired['processed_ns']<phase['planned_ns']+150000000,'matching path arrived well before original cutoff')
  need(begins[gap['tick']]['expired_previous'] is True,'next actual tick expired unconsumed prior phase')
  need(pub['phase']==phase and pub['phase_publish_end_ns']<callback['observed_ns'],'actual publisher phase and receiver identity join')
  evidence.append(dict(empty_tick=gap['tick'],blocked_preparation_tick=tick,phase_decision_sequence=phase['decision_sequence'],applied_sequence=phase['applied_sequence'],phase_observed_ns=callback['observed_ns'],profile_stamp_ns=pair['profile_version']['stamp_ns'],old_path_stamp_ns=pair['path_version']['stamp_ns'],profile_source_index=pair['profile_version']['source_index'],phase_source_index=entry['source_index'],matching_path_source_index=repaired['source_index'],matching_path_processed_ns=repaired['processed_ns'],pair_recovered_after_phase_ms=(repaired['processed_ns']-callback['observed_ns'])/1e6,remaining_original_deadline_after_recovery_ms=(phase['planned_ns']+150000000-repaired['processed_ns'])/1e6,phase_publish_from_planned_ms=(pub['phase_publish_end_ns']-phase['planned_ns'])/1e6,phase_delivery_ms=(callback['observed_ns']-pub['phase_publish_end_ns'])/1e6,no_Job_target_tick=gap['tick'],next_tick_expired_previous=True,phase_accepted=True))
 cpp=N/'observer/src/shadow/regulator_shadow_observer.cpp';source=cpp.read_text();calls=[dict(line=i+1,text=line.strip()) for i,line in enumerate(source.splitlines()) if 'maybe_enqueue_controlled_locked(' in line and 'void maybe_enqueue_controlled_locked' not in line];need(len(calls)==2 and 'else maybe_enqueue_controlled_locked' in calls[0]['text'] and 'if(reason.empty())maybe_enqueue_controlled_locked' in calls[1]['text'],'actual only wakeups are Applied and phase; no path/profile retry')
 need(not [r for r in observer if r['type']=='job_not_submitted'],'no failed prepare/submit record hiding complete Job population')
 for p,s in before.items():need(sha(p)==s,'audit changed locked raw bytes: '+p)
 value=dict(schema='scheme-A-missing-reference-pair-wakeup-audit/v1',client_date='2026-10-18',audit_passed=True,post_hoc_diagnostic=True,overall_case_passed=False,measurement_empty_ticks=[r['tick'] for r in gaps],initial_empty_ticks=[r['tick'] for r in gaps if r['tick']<=first_accept],interior_empty_ticks=[r['tick'] for r in interior],events=evidence,actual_enqueue_call_sites=calls,actual_runtime_cpp=dict(path=str(cpp),sha256=sha(cpp)),actual_checker=dict(path=str(report_path),sha256=sha(report_path)),raw_locked_paths_rechecked=len(before),actual_SQLite=dbpins,conclusion='All six interior missing Jobs share an accepted phase while profile is new and path is old; exact matching path follows before cutoff but the actual callback has no enqueue wakeup. The next tick expires that phase. No corresponding Job reaches Worker. This is an observed conditional retry omission; it does not quantify the isolated performance effect of repairing it.',unique_cause_of_RMSE_failure_proven=False,ROS_nodes_started=False,guard_or_threshold_modified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False,recipe_sha256=sha(__file__))
 out=D/'postrun/missing_preparations_audit_v1.json'
 with out.open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps(dict(audit_passed=True,interior_gaps=len(interior),pair_recovery_after_phase_ms=[r['pair_recovered_after_phase_ms'] for r in evidence],minimum_remaining_deadline_ms=min(r['remaining_original_deadline_after_recovery_ms'] for r in evidence))))
if __name__=='__main__':main()
