"""Fresh owned identities and two healthy distinct accepted jobs; grants no stage authority."""
from pathlib import Path
import hashlib,json,time
ROLES={'observer','worker','publisher','synthetic_source','recorder'}
def need(v,w):
    if not v:raise ValueError(w)
def validate_fresh(previous,manifests,run,prepare_start_ns):
    need(previous['schema']=='previous-current-lease-close-proof/v1' and previous['independent_actual_lease_audit_passed'] is True,'verified_prior_lease_close_required')
    need(set(manifests)==set(previous['old_role_manifests'])==set(previous['old_cleanup'])==ROLES,'five_fresh_owned_roles')
    need(run!=previous['run_id'] and prepare_start_ns>previous['old_all_groups_cleanup_observed_ns'],'new_prepare_after_old_groups_closed')
    for role,m in manifests.items():
        old=previous['old_role_manifests'][role];c=previous['old_cleanup'][role]
        need(c['cleanup_complete'] and c['remaining_members']==[] and c['returncode']==0,'previous_owned_group_not_closed:'+role)
        need(m['role']==role and m['run_id']==run+('-publisher' if role=='publisher' else '') and m['run_id']!=old['run_id']
            and m['boot_id']==previous['boot_id'] and m['contract_sha256']==previous['contract_sha256'],'fresh_role_run_boot_contract:'+role)
        need((m['pid'],m['process_start_ticks'])!=(old['pid'],old['process_start_ticks']),'old_process_identity_reused:'+role)
        need(m['binary_sha256']==old['binary_sha256'] and m['source_bundle_sha256']==old['source_bundle_sha256'],'same_current_role_lineage:'+role)
        need(m['effective_parameters_immutable'] and m['execute_qualified'] is False,'fresh_immutable_shadow_role:'+role)
    wm,om=manifests['worker'],manifests['observer'];op=om['effective_parameters'];wp=wm['effective_parameters']
    need(wm['worker_instance']!=previous['old_role_manifests']['worker']['worker_instance'],'old_Worker_instance_reused')
    need(wp['diagnostic_v2_policy']['value']=='none' and wp['diagnostic_v2_block_ms']['value']==0,'fresh_Worker_no_stimulus')
    need(op['mode']['value']=='shadow' and op['diagnostic_v1_sink_policy']['value']=='none'
        and op['diagnostic_v3_input_policy']['value']=='none' and op['diagnostic_v3_wait_ns']['value']==0
        and op['diagnostic_c38_mode']['value']=='none' and op['business_start_policy']['value']=='owned-prepare-before-business-v1'
        and om['physical_publisher_endpoints']==0,'fresh_Observer_explicit_healthy_gated_shadow')
    return dict(fresh_owned_identities_verified=True,previous_run_id=previous['run_id'],run_id=run,
        old_all_groups_cleanup_observed_ns=previous['old_all_groups_cleanup_observed_ns'],new_prepare_start_ns=prepare_start_ns,
        old_Worker_instance=previous['old_role_manifests']['worker']['worker_instance'],new_Worker_instance=wm['worker_instance'],
        stage_qualified=False,execute_qualified=False,research_conclusion=False)

def healthy_pairs(source,publisher):
    pairs=[];jobs=set()
    for d in source:
        if d.get('type')!='decision' or d.get('accepted') is not True or d['job_id']<=0 or d['job_id'] in jobs:continue
        callbacks=[r for r in source if r.get('type')=='controlled_phase_callback' and r.get('accepted') is True and r['authentication_reason']=='' and r['phase']['decision_sequence']==d['sequence']]
        if not callbacks:continue
        need(len(callbacks)==1,'unique_healthy_phase_callback');cb=callbacks[0]
        physical=[r for r in publisher if r.get('type')=='controlled_decision_physical_return' and r['decision_sequence']==d['sequence']]
        need(len(physical)==1,'unique_healthy_physical_return')
        applied=[r for r in publisher if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==physical[0]['applied_sequence']==cb['phase']['applied_sequence']]
        need(len(applied)==1,'unique_healthy_Applied');em=applied[0]
        need(d['activation_commit_ns']<=em['applied_publish_end_ns']<=cb['phase']['emitted_ns'],'healthy_decision_API_phase_order')
        pairs.append(dict(decision_sequence=d['sequence'],job_id=d['job_id'],Applied_sequence=em['applied_sequence'],activation_commit_ns=d['activation_commit_ns'],Applied_publish_end_ns=em['applied_publish_end_ns'],phase_emitted_ns=cb['phase']['emitted_ns']))
        jobs.add(d['job_id'])
    return pairs

def observe(root,*,spin,bound,create_only_json,overall_deadline_ns):
    root=Path(root);start=time.monotonic_ns();deadline=min(start+5000000000,overall_deadline_ns-15000000000)
    def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines(keepends=True) if x.endswith(b'\n')]
    while time.monotonic_ns()<deadline:
        bound();source=rows(root/'observer/source.jsonl')
        need(not any(r.get('type') in ['worker_unusable_transition','diagnostic_c38_gate_paused','diagnostic_v1_armed_after_ack'] for r in source),'unexpected_fault_during_healthy_recovery')
        pairs=healthy_pairs(source,rows(root/'publisher/controlled_source.jsonl'))
        if len(pairs)>=2:
            proof=dict(schema='fresh-recovery-two-healthy-jobs/v1',started_ns=start,finished_ns=time.monotonic_ns(),deadline_ns=deadline,
                pairs=pairs,distinct_accepted_jobs=len({r['job_id'] for r in pairs}),normal_business_qualified=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
            create_only_json(root/'recovery_healthy_observation.json',proof);return proof
        spin(.005)
    raise RuntimeError('two distinct healthy accepted jobs and actual Applied deadline')

def bind_before_business(root,previous,roles,run,prepare_start_ns,create_only_json):
    for path,f in previous['source_input_pins'].items():
        b=Path(path).read_bytes();need(dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==f,'old_lease_evidence_changed:'+path)
    proof=validate_fresh(previous,{k:v['manifest'] for k,v in roles.items()},run,prepare_start_ns)
    proof.update(new_manifest_sha256={k:v['sha256'] for k,v in roles.items()},checked_ns=time.monotonic_ns())
    create_only_json(Path(root)/'recovery_identity_before_business.json',proof);return proof
