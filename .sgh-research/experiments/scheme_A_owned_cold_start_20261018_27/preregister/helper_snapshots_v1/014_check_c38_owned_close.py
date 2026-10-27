#!/usr/bin/env python3
"""Actual owned close diagnostics, complete inputs; no phase qualification."""
from pathlib import Path
import argparse,hashlib,json,math,os,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE/'runtime')]
import check_c37_owned_run_v2 as p
c36=p.c36
exact=p.exact
CASES={'normal','queued_tail','late_tail','pre_request_tail','malformed_close','wrong_driver','duplicate_close','ack_missing','forced_cleanup'}
FLAGS=p.FLAGS.copy()
def integer(x):return type(x) is int and x>0
def tail_permitted(m,auth,gid,request,observed,receipt):
 if auth!='owner_process_exited' or not gid or not all(integer(v) for v in (request,observed,receipt)) or not request<=observed<=receipt or receipt-request>2_000_000_000:return False
 n=m.get('final_n');times=[m.get(k) for k in ['left_publish_start_steady_ns','left_publish_end_steady_ns','right_publish_start_steady_ns','right_publish_end_steady_ns']]
 return (m.get('control_source')=='shutdown_zero' and type(n) is list and len(n)==2 and all(type(v) in (int,float) and math.isfinite(v) and v==0 for v in n) and m.get('left_publish_success') is True and m.get('right_publish_success') is True and all(integer(v) for v in times) and request<=times[0]<=times[1]<=times[2]<=times[3]<=receipt)
def analyze(run):
 run=Path(run).resolve();c=c36.Checks();files=[f for f in run.rglob('*') if f.is_file()];before={str(f):c36.sha(f) for f in files}
 inputs=c36.load(run/'inputs.json');result=c36.load(run/'result.json');case=inputs.get('c38_case');c.need(case in CASES and result.get('c38_case')==case,'case_domain')
 c.need(inputs.get('measurement_seconds')==4 and inputs.get('witness_validation_profile')==p.PROFILE and result.get('finite_prepare_and_measurement_passed') is True and result.get('released') is True,'preregistered_prepare_measurement')
 c.need(result.get('diagnostic_case_completed') is True and result.get('cleanup_complete') is True and result.get('cleanup_within_budget') is True and result.get('close_elapsed_ns',16_000_000_000)<=15_000_000_000,'bounded_owned_cleanup_and_scenario')
 c.need(set(result.get('cleanup',{}))==c36.ROLES and all(v.get('remaining_members')==[] and v.get('cleanup_complete') is True for v in result['cleanup'].values()),'all_registered_groups_reaped')
 manifests={k:c36.load(run/k/'owned_manifest.json') for k in c36.ROLES};pub=manifests['publisher'];worker=manifests['worker'];obs=manifests['observer'];peer=c36.load(run/'adapter_peer_pins.json')
 p.worker_binding(run,inputs,manifests,peer,c);p.configurations(run,inputs,result,manifests,c);p.worker_contract_configuration(inputs,worker,c)
 c.need(obs['effective_parameters']['mode']['value']=='shadow' and obs.get('physical_publisher_endpoints')==0,'actual_shadow_no_regulator_outputs')
 topicmap=c36.load(run/'topics.json')['topics'];decoded,raw_rows,storage=p.base.read_actual_storage(run/'recorder/bag',topicmap)
 observer=c36.lines(run/'observer/source.jsonl');ws=c36.lines(run/'worker/source.jsonl')
 transport=p.base.transport_join(raw_rows,c36.lines(run/'synthetic_source/transport_source.jsonl'),manifests,topicmap);c.need(transport.get('passed') is True,'whole_transport_storage',issues=transport.get('issues'))
 source=p.base.source_typed_join(observer,ws,decoded);c.need(source.get('passed') is True,'whole_Job_Candidate_source_storage',issues=source.get('issues'))
 receipts,raw_worker=p.worker_population(observer,decoded,worker,peer,c);pubs=p.worker_publication_population(run,inputs,ws,observer,decoded,worker,c)
 expected={k:worker[k] for k in ('run_id','boot_id')};expected.update(contract_hash=worker['contract_sha256'],nominal_hash=worker['nominal_hash'],pid=worker['pid'],fault_injection_enabled=p.worker_fault_permission(worker,c))
 lr=p.lease.replay(observer,expected,obs['contract_configuration']['worker_capability_receipt_timeout_ns'],c.need,decode_raw=lambda raw,index:raw_worker['capability'].get(raw['callback_sequence']),require_observation=True)
 witness=p.witness_source_population(c36.load(run/'observer/witness.json'),c36.load(run/'expected_witness_header.json'),observer,c)
 session_path=run/'publisher/session_summary.json';publisher_complete=False
 if session_path.exists():
  pp=p.base.publisher_join(c36.load(session_path),decoded,c36.load(run/'publisher/startup_manifest.json'),pub);publisher_complete=pp.get('passed') is True;c.need(publisher_complete,'whole_originalF5_session_storage',issues=pp.get('issues'))
 else:c.need(case=='forced_cleanup','missing_session_only_declared_kill')
 get=lambda kind:[r for r in observer if r.get('type')==kind]
 good=get('adapter_driver_close_observed');bad=get('adapter_close_evidence_failed');co=c36.load(run/'c38_close_observation.json');request_sha=c36.sha(run/'adapter_driver_close_request.json')
 if case in ('malformed_close','wrong_driver'):c.need(len(bad)==1 and not good and co.get('rejected') is not None and result.get('passed') is False,'invalid_close_failed_and_not_normal')
 elif case=='ack_missing':c.need(not good and not bad and co.get('ack_missing') is True and len(get('diagnostic_c38_close_poll_suppressed'))==1 and result.get('passed') is False,'actual_absent_ack_at_deadline')
 else:c.need(len(good)==1 and not bad and good[0].get('request_sha256')==request_sha and co.get('observer')==good[0],'valid_request_Source_ack_once')
 closing_ns=good[0]['observed_ns'] if len(good)==1 else bad[0]['observed_ns'] if len(bad)==1 else None
 if closing_ns:
  c.need(not [r for r in get('job') if r['submit_commit_ns']>closing_ns],'no_new_Job_after_actual_close')
  c.need(not [r for r in get('decision') if r.get('accepted') is True and r['activation_commit_ns']>closing_ns],'no_new_Accepted_after_actual_close')
 rows=get('adapter_applied_callback');closure=get('adapter_applied_reception_closed');c.need(len(closure)==1 and closure[0]['executor_detached'] is True and closure[0]['legacy_received']==closure[0]['raw_callback_sequence']==len(rows),'entire_actual_Applied_received_counter_closure')
 expected_gid=[e['gid'] for e in pub['endpoints'] if e['kind']=='publisher' and e['topic']==c36.APPLIED];c.need(len(expected_gid)==1,'owner_manifest_unique_Applied_GID');expected_gid=expected_gid[0]
 stored={r['message']['sequence']:r['message'] for r in decoded[c36.APPLIED]};c.need(len(stored)==len(decoded[c36.APPLIED]),'stored_Applied_sequence_unique')
 c.need([r['raw_input']['callback_sequence'] for r in rows]==list(range(1,len(rows)+1)),'all_Applied_callback_sequences')
 anchors=get('legacy_anchor');rejections=get('adapter_applied_auth_rejected');applied=[];last_anchor=[0.,0.];row_index={id(r):i for i,r in enumerate(observer)}
 for r in observer:
  if r.get('type')=='legacy_anchor':last_anchor=r['final_n']
  if r.get('type')=='adapter_applied_auth_rejected':c.need(exact(r['anchor_after'],last_anchor),'denied_owner_receipt_keeps_anchor',sequence=r['sequence'])
 for r in rows:
  raw=r['raw_input'];seq=r['sequence'];m=p.decode_callback(raw,c,{'sequence':seq});c.need(m is not None and seq in stored and exact(m,stored.get(seq)),'whole_typed_received_CDR_Storage_binding',sequence=seq)
  c.need(exact(raw['publisher_gid'],expected_gid) and raw['rmw_implementation']=='rmw_fastrtps_cpp' and raw['entry_steady_ns']<=r['processed_ns'] and r['processed_ns']<=closure[0]['closed_ns'],'actual_original_Writer_metadata_and_window',sequence=seq)
  if m is None:continue
  req=good[0]['requested_ns'] if len(good)==1 else 0;observed=good[0]['observed_ns'] if len(good)==1 else 0
  permitted=tail_permitted(m,r['authentication_reason'],True,req,observed,r['processed_ns']);c.need(r.get('queued_terminal_tail') is permitted,'original_post_exit_tail_predicate_exact',sequence=seq)
  if r['authentication_reason']:
   if permitted:c.need(any(a['sequence']==seq for a in anchors),'allowed_post_exit_zero_actually_admitted',sequence=seq)
   else:c.need(any(a['sequence']==seq for a in rejections) and not any(a['sequence']==seq for a in anchors),'denied_owner_receipt_not_admitted',sequence=seq)
  applied.append({'sequence':seq,'entry_ns':raw['entry_steady_ns'],'processed_ns':r['processed_ns'],'owner_alive_later':r['owner_process_alive'],'auth':r['authentication_reason'],'tail':permitted,'control_source':m['control_source'],'final_n':m['final_n'],'left_start_ns':m['left_publish_start_steady_ns'],'right_end_ns':m['right_publish_end_steady_ns']})
 exitproof=c36.load(run/'c38_owner_exit_proof.json');ledger=c36.lines(run/'owned_process_ledger.jsonl');sig=[r for r in ledger if r.get('type')=='signal' and r.get('name')=='publisher']
 c.need(exitproof['publisher_pid']==pub['pid'] and exitproof['publisher_start_ticks']==pub['process_start_ticks'] and exitproof['owner_manifest_sha256']==c36.sha(run/'publisher/owned_manifest.json') and exitproof['remaining_members']==[] and integer(exitproof['proof_ns']) and exitproof['returncode']==result['owned_role_returncodes']['publisher'],'actual_owner_exit_reap_identity')
 if case in ('queued_tail','late_tail','pre_request_tail'):
  paused=get('diagnostic_c38_gate_paused');resumed=get('diagnostic_c38_gate_resumed');c.need(len(paused)==len(resumed)==1 and not get('diagnostic_c38_gate_timeout') and not get('diagnostic_c38_gate_rejected'),'actual_applied_group_gate_finite')
  c.need(paused[0]['group_registered'] is False and resumed[0]['group_registered'] is True and paused[0]['checked_ns']<exitproof['proof_ns']<=resumed[0]['checked_ns'],'executor_pause_owner_exit_resume_order')
  for action,event in [('pause',paused[0]),('resume',resumed[0])]:
   request=c36.load(run/('c38_'+action+'_request.json'));c.need(event['request_sha256']==c36.sha(run/('c38_'+action+'_request.json')) and request['driver_pid']==peer['driver']['pid'] and request['driver_start_ticks']==peer['driver']['start_ticks'] and request['driver_tool_sha256']==peer['driver_tool_sha256'] and request['owner_manifest_sha256']==c36.sha(run/'publisher/owned_manifest.json'),'actual_gate_request_full_binding',action=action)
  zeros=[r for r in applied if r['control_source']=='shutdown_zero' and r['auth']=='owner_process_exited' and r['entry_ns']>exitproof['proof_ns']]
  c.need(bool(zeros),'actual_DDS_take_callback_after_owner_exit')
  if case=='queued_tail':c.need(any(r['tail'] for r in zeros),'post_exit_zero_within_window_accepted')
  else:
   c.need(all(not r['tail'] for r in zeros),'post_exit_negative_not_authorized')
   if case=='late_tail':c.need(all(r['processed_ns']-good[0]['requested_ns']>2_000_000_000 for r in zeros),'actual_late_window_condition')
   else:c.need(all(r['left_start_ns']<good[0]['requested_ns'] for r in zeros),'actual_call_before_request_condition')
 if case=='duplicate_close':
  duplicate=c36.load(run/'c38_duplicate_close.json');c.need(duplicate['refused'] is True and duplicate['first_bytes_unchanged'] is True and duplicate['first_sha256']==duplicate['after_sha256']==request_sha,'duplicate_create_only_preserves_first_request')
 if case=='forced_cleanup':
  fp=c36.load(run/'c38_forced_cleanup_proof.json');c.need(fp['target']=='publisher' and fp['graceful_wait_empty'] is False and fp['wait_end_ns']-fp['wait_start_ns']>=fp['grace_budget_ns']==2_000_000_000 and fp['returncode']==-9 and fp['remaining_members']==[] and any(r['signal']==9 for r in sig) and result['passed'] is False,'actual_graceful_deadline_failure_and_scoped_kill_recovery')
 for r in get('adapter_closed_after_join'):c.need(r['evidence']['actual_regulator_publish'] is False and r['owner_endpoints_exited']=='unknown','no_physical_release_inference')
 assets=p.asset_pins(inputs,c)
 deps=[Path(__file__),HERE/'check_c37_owned_run_v2.py',HERE/'check_c36_adapter_run.py',HERE/'check_owned_fixture.py',HERE/'runtime/check_p1_execution.py',HERE/'runtime/check_p1_witness_v2.py',HERE/'lease_replay_v1.py',HERE/'owned_auth.py',HERE/'owned_release.py']
 for dep in deps:
  rel=str(dep.relative_to(HERE));c.need(inputs['tool_sha256'].get(rel)==c36.sha(dep) and c36.sha(run/(rel.replace('/','__')+'.snapshot'))==c36.sha(dep),'prerun_checker_dependency_exact',tool=rel)
 after={str(f):c36.sha(f) for f in files};c.need(before==after,'all_raw_run_files_unchanged')
 return c.result(schema='p1-C3.8-owned-close-check-v1',run_dir=str(run),case=case,diagnostic_case_predicate_passed=not c.issues,normal_driver_passed=result['passed'],resource_cleanup_complete=result['cleanup_complete'],qualifications=FLAGS,unknowns=p.UNKNOWNS,applied_received=len(rows),applied_recorded=len(stored),applied_diagnostic_population=applied,worker_callbacks=receipts,worker_publications=pubs,witness_v2=witness,storage=storage,publisher_normal_session_complete=publisher_complete,input_sha256_before=before,input_sha256_after=after,author_asset_sha256=assets,checker_dependencies={str(dep):c36.sha(dep) for dep in deps},checker_sha256=c36.sha(__file__),all_published_received_claimed=False,window_clipped=False)
def write(path,data):
 raw=(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n').encode();assert len(raw)<=8*1024*1024
 assert not any(p.is_symlink() for p in path.parents)
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert path.read_bytes()==raw
 return len(raw)
def main():
 a=argparse.ArgumentParser();a.add_argument('--run-dir',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 try:r=analyze(args.run_dir)
 except Exception as e:r={'schema':'p1-C3.8-owned-close-check-v1','passed':False,'reader_error':repr(e),'case':args.run_dir.name,'qualifications':FLAGS}
 size=write(args.output,r);print(json.dumps({'passed':r['passed'],'issues':r.get('issues'),'reader_error':r.get('reader_error'),'bytes':size}));return 0 if r['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
