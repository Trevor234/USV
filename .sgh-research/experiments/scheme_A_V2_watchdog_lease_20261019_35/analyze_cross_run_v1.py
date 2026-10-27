"""Recompute new-run recovery and scope limits from the two audited final runs."""
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
pins={}
def load(p):
 b=p.read_bytes();pins[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return json.loads(b)
def rows(p):
 b=p.read_bytes();pins[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return [json.loads(x) for x in b.splitlines()]
B=D/'author_r3/runs/v2_lease_r3_04';A=D/'author_r3/runs/v2_active_r3_05'
audits=[load(D/'postrun/v2_lease_r3_audit_v1.json'),load(D/'postrun/v2_active_r3_audit_v1.json')]
assert all(x['passed'] and x['component_passed'] for x in audits)
mb,ma=load(B/'worker/owned_manifest.json'),load(A/'worker/owned_manifest.json')
sa,wa,pa,la=rows(A/'observer/source.jsonl'),rows(A/'worker/source.jsonl'),rows(A/'publisher/controlled_source.jsonl'),rows(A/'owned_process_ledger.jsonl')
lb=rows(B/'owned_process_ledger.jsonl');ra,rb=load(A/'result.json'),load(B/'result.json')
assert ma['worker_instance']!=mb['worker_instance'] and ma['pid']!=mb['pid'] and ma['process_start_ticks']>mb['process_start_ticks']
assert ma['binary_sha256']==mb['binary_sha256']=='6ad949b4ce68db8d26d97d6409c2d710739750ec107bf0ee735edfbf63f11a58'
assert ma['contract_sha256']==mb['contract_sha256'] and ma['boot_id']==mb['boot_id']
prior_closed=max(x['monotonic_ns'] for x in lb if x['type']=='cleanup_result')
new_spawn=next(x['monotonic_ns'] for x in la if x['type']=='spawn' and x['name']=='worker')
assert new_spawn>prior_closed
entry=next(x for x in wa if x['type']=='diagnostic_v2_pre_native_enter')
release=next(x for x in wa if x['type']=='diagnostic_v2_pre_native_release')
transition=next(x for x in sa if x['type']=='worker_unusable_transition')
first_accepted=next(x for x in sa if x['type']=='decision' and x['accepted'])
physical=next(x for x in pa if x['type']=='controlled_decision_physical_return' and x['decision_sequence']==first_accepted['sequence'])
emission=next(x for x in pa if x['type']=='controlled_Applied_emitted' and x['applied_sequence']==physical['applied_sequence'])
worker_cleanup=next(x for x in la if x['type']=='cleanup_result' and x['name']=='worker')
assert emission['applied_publish_end_ns']<transition['check_ns']
caps=[x for x in wa if x['type']=='capability_publish_attempt']
pending_max=max(x['payload']['pending_count'] for x in caps)
assert pending_max<=1 and all(ra[k] and rb[k] for k in ['cleanup_complete','cleanup_within_budget','V2_case_completed'])
out={'schema':'V2-cross-run-recovery-and-scope/v1','passed':True,
 'same_Worker_ELF_and_contract':True,'different_Worker_instances_PIDs_and_start_times':True,
 'prior_all_owned_groups_closed_before_new_Worker_spawn':True,
 'fresh_run_new_actual_accepted_prefix_before_its_separate_fault':True,
 'fresh_prefix_Decision':first_accepted['sequence'],'fresh_prefix_Applied':physical['applied_sequence'],
 'fresh_prefix_actual_API_before_barrier':emission['applied_publish_end_ns']<entry['start_ns'],
 'barrier_started_after_at_least_one_completed_Job':entry['completed_jobs_before'],
 'barrier_release_after_watchdog_ns':release['released_ns']-transition['check_ns'],
 'watchdog_to_Worker_group_cleanup_observed_ns':worker_cleanup['monotonic_ns']-transition['check_ns'],
 'observed_capability_pending_max':pending_max,'all_interleavings_pending_bound_proven':False,
 'Native_in_C_uninterruptible_hang_tested':False,'watchdog_triggered_TERM_KILL_deadline_qualified':False,
 'current_version_old_instance_packet_injection_tested':False,
 'sustained_normal_twenty_second_recovery_qualified':False,
 'V2_scoped_minimal_cases_complete':True,'all_original_V2_stage_claims_complete':False,
 'original_normal_business_results':[rb['passed'],ra['passed']],
 'actual_launches':4,'released_runs':3,'final_profile_passed_runs':2,
 'initial_missing_library_failure_preserved':True,'initial_literal_reason_and_normal_tail_failure_preserved':True,
 'role_cpp_builds':1,'new_native_policy_assertions':22,'new_time_boundary_checks':12,
 'new_causal_close_offline_checks':10,'actual_raw_terminal_negative_checks':8,
 'input_pins':pins,'stage_qualified':False,'execute_qualified':False,'true_plant_qualified':False,'research_conclusion':False}
with (D/'postrun/cross_run_recovery_scope_v1.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True)
print(json.dumps({k:v for k,v in out.items() if k!='input_pins'}))
