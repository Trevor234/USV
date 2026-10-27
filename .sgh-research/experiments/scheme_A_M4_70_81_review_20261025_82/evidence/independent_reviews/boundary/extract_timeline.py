#!/usr/bin/env python3
import pathlib,json,hashlib
base=pathlib.Path('/home/trevor/USV/.sgh-research/experiments')
r=base/'scheme_A_M4_t2_r2_driver_20261025_78/implementation/runs/T2B_P01'
author=r.parents[1]/'t2_author_r3'
def rr(rel):return [(i,json.loads(s)) for i,s in enumerate((r/rel).read_text().splitlines(),1) if s.strip()]
R=rr('regulator/source.jsonl');W=rr('worker/source.jsonl');F=rr('fixture/nominal_steps.jsonl');D=rr('driver_events.jsonl')
def find(rows,t,p=lambda x:True):return next((i,x) for i,x in rows if x.get('type')==t and p(x))
_,j=find(R,'job',lambda x:x['job']['job_id']==2);job=j['job'];ori=job['tick_origin_ns'];dl=job['deadline_ns']
_,recv=find(W,'job_received',lambda x:x['job']['job_id']==2)
bi,b=find(W,'w2_boundary_entered');ri,bres=find(W,'w2_boundary_result');br=bres['boundary']
fi,f=find(F,'t2_action_executed');vi,v=find(R,'path_version',lambda x:x.get('task_generation')==3)
ci,c=find(W,'candidate',lambda x:x['job']['job_id']==2);cr_i,cr=find(R,'candidate_registration',lambda x:x['job']['job_id']==2)
pi,p=find(W,'cold_start_policy_result',lambda x:x['job_id']==2)
_,command=find(D,'t2_command_evidence');_,commanded=find(D,'t2_action_commanded');_,release=find(D,'t2_boundary_released')
driver=json.loads((r/'driver_result.json').read_bytes());registered=json.loads((base/'scheme_A_M4_t2b_prepos_20261025_81/implementation/T2B_prepos_registration.json').read_bytes())
timepoints={'tick_origin':ori,'job_received':recv['receive_ns'],'boundary_entered':b['entered_ns'],'driver_command_evidence':command['driver_observed_ns'],'fixture_path_executed':f['executed_ns'],'regulator_task3_commit':v['processed_ns'],'driver_command_fsync_done':commanded['checked_ns'],'driver_release_written':release['checked_ns'],'boundary_release_received':br['released_ns'],'final_guard':br['guard_ns'],'candidate_publish':c['publish_start_ns'],'candidate_registered_rejected':cr['ready_commit_ns'],'deadline':dl}
positives={'original_deadline_150ms':dl-ori==150000000,'full_job_echo_identical':all(x==job for x in [recv['job'],c['job'],cr['job'],driver['t2_command_records'][0]['command']['trigger']['job']]),'real_held_order':b['entered_ns']<f['executed_ns']<v['processed_ns']<br['released_ns']<=br['guard_ns']<c['publish_start_ns']<cr['ready_commit_ns']<dl,'native_one_real_C_call':p['metadata']['actual_C_solve_calls_this_job']==1 and br['actual_native_invoked'] is True,'allowed_not_expired':br['disposition']=='allowed' and br['past_deadline_ns']<0,'same_job_version_mismatch':cr['accepted_registration'] is False and cr['reason']=='version_mismatch','four_clean_closures':len(driver['closed_roles'])==4 and all(x['returncode']==0 and x['group_empty'] for x in driver['closed_roles'])}
out={'run':str(r),'positive_observation_checks':positives,'timepoints_ns':timepoints,'timepoints_from_origin_ms':{k:(v-ori)/1e6 for k,v in timepoints.items()},'source_lines':{'worker_boundary_entered':bi,'worker_boundary_result':ri,'worker_native_policy':pi,'fixture_receipt':fi,'regulator_commit':vi,'worker_candidate':ci,'regulator_registration':cr_i},'corrections':{'received_before_boundary_ms':(b['entered_ns']-recv['receive_ns'])/1e6,'command_evidence_after_boundary_ms':(command['driver_observed_ns']-b['entered_ns'])/1e6,'fixture_execution_after_boundary_ms':(f['executed_ns']-b['entered_ns'])/1e6,'margin_at_final_guard_ms':(dl-br['guard_ns'])/1e6},'audit_identity':{'registered_sha256':registered['audit_tool']['sha256'],'current_sha256':hashlib.sha256(pathlib.Path(registered['audit_tool']['path']).read_bytes()).hexdigest(),'matching_pinned_copy':str(base/'scheme_A_M4_t2b_flush_20261025_80/implementation/t2_author_r4/audit_t2.py')}}
pathlib.Path('/tmp/review81_boundary/timeline_evidence.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
