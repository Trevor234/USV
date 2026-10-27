"""Independent current fresh identity, healthy-job and original normal-tail predicates."""
ROLES={'observer','worker','publisher','synthetic_source','recorder'}
def need(v,w):
    if not v:raise ValueError(w)

def identity(b):
    old,m=b['previous'],b['manifests'];r=b['result'];proof=b['identity']
    need(old['independent_actual_lease_audit_passed'] and set(m)==set(old['old_role_manifests'])==set(old['old_cleanup'])==ROLES,'old_current_lease_and_five_role_basis')
    need(r['run_id']!=old['run_id'] and r['prepare_start_ns']>old['old_all_groups_cleanup_observed_ns'],'fresh_prepare_after_exact_lease41_close')
    need(proof['previous_run_id']==old['run_id'] and proof['run_id']==r['run_id']
        and proof['fresh_owned_identities_verified'] is True and proof['old_all_groups_cleanup_observed_ns']==old['old_all_groups_cleanup_observed_ns']
        and proof['new_prepare_start_ns']==r['prepare_start_ns'],'actual_before_business_identity_proof')
    for role,n in m.items():
        prior=old['old_role_manifests'][role];clean=old['old_cleanup'][role]
        need(clean['cleanup_complete'] and clean['returncode']==0 and clean['remaining_members']==[],'previous_exact_owned_group_empty:'+role)
        need(n['run_id']==r['run_id']+('-publisher' if role=='publisher' else '') and n['run_id']!=prior['run_id']
            and n['boot_id']==old['boot_id'] and n['contract_sha256']==old['contract_sha256'],'new_role_run_boot_contract:'+role)
        need((n['pid'],n['process_start_ticks'])!=(prior['pid'],prior['process_start_ticks']),'old_PID_start_reused:'+role)
        need(n['binary_sha256']==prior['binary_sha256'] and n['source_bundle_sha256']==prior['source_bundle_sha256'],'same_final_role_lineage:'+role)
        need(proof['new_manifest_sha256'][role]==b['prepared']['roles'][role]['manifest_sha256'],'fresh_proof_full_manifest_binding:'+role)
    wm=m['worker'];oldwm=old['old_role_manifests']['worker']
    need(wm['worker_instance']!=oldwm['worker_instance'] and proof['new_Worker_instance']==wm['worker_instance']
        and proof['old_Worker_instance']==oldwm['worker_instance'],'new_native_Worker_instance_required')
    gate=[r for r in b['source'] if r.get('type')=='business_start_authorized'];need(len(gate)==1 and proof['checked_ns']<gate[0]['authorized_ns'],'fresh_identity_check_precedes_new_business')
    caps=[r for r in b['source'] if r.get('type')=='capability_admission' and r['renewed']]
    need(caps and all(r['capability']['run_id']==wm['run_id'] and r['capability']['pid']==wm['pid']
        and r['capability']['worker_instance']==wm['worker_instance'] for r in caps),'all_renewals_new_exact_Worker_identity')
    need(b['witness']['header']['worker_instance']==wm['worker_instance'],'Witness_new_Worker_binding')
    return dict(passed=True,previous_run=old['run_id'],new_run=r['run_id'],old_all_groups_closed_before_new_prepare=True,
        old_Worker_instance=oldwm['worker_instance'],new_Worker_instance=wm['worker_instance'],all_five_PID_start_pairs_fresh=True,
        same_five_registered_ELFs=True,new_own_manifest_bindings=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)

def healthy(b):
    source,worker,pub,witness=b['source'],b['worker'],b['publisher'],b['witness'];wm=b['manifests']['worker'];obs=b['healthy'];run=b['result']['run_id']
    need(not any(r.get('type') in ['worker_unusable_transition','diagnostic_v1_armed_after_ack','diagnostic_c38_gate_paused','diagnostic_c38_gate_timeout'] for r in source),'healthy_recovery_has_no_terminal_or_stimulus')
    need(not any(r.get('type')=='diagnostic_v2_pre_native_enter' for r in worker),'healthy_Worker_no_pre_native_stimulus')
    need(obs['finished_ns']<=obs['deadline_ns'] and obs['distinct_accepted_jobs']>=2,'two_healthy_jobs_observation_deadline')
    jobs={r['job']['job_id']:r for r in source if r.get('type')=='job'};candidates={r['job']['job_id']:r for r in worker if r.get('type')=='candidate'}
    accepted={r['job_id']:r for r in source if r.get('type')=='decision' and r['accepted']};pairs=obs['pairs']
    need(len(pairs)>=2 and len({r['job_id'] for r in pairs})==obs['distinct_accepted_jobs']==len(pairs),'distinct_healthy_job_identity_set')
    need(len({r['decision_sequence'] for r in pairs})==len(pairs) and len({r['Applied_sequence'] for r in pairs})==len(pairs),'unique_healthy_Decision_Applied_pairs')
    details=[]
    for p in pairs:
        jid=p['job_id'];need(jid in jobs and jid in candidates and jid in accepted,'healthy_job_candidate_accepted_join');j=jobs[jid]['job'];c=candidates[jid];d=accepted[jid]
        need(j['run_id']==run and j['worker_instance']==wm['worker_instance'] and c['worker_instance']==wm['worker_instance']
            and c['job']==j and c['success'] and c['solver_invoked'],'new_exact_Worker_healthy_candidate')
        origins=[r for r in source if r.get('type')=='controlled_phase_freeze' and r['target_tick']==j['target_tick']]
        need(len(origins)==1 and j['tick_origin_ns']==origins[0]['planned_ns']
            and j['target_ns']==j['tick_origin_ns']+200000000
            and j['deadline_ns']==j['tick_origin_ns']+150000000 and d['ready_commit_ns']<=j['deadline_ns']
            and c['solve_end_ns']<=j['deadline_ns'],'unchanged_absolute150ms_ready_deadline')
        activation=[r for r in witness['activation'] if r['job_id']==jid and r['accepted']]
        need(len(activation)==1 and activation[0]['commit_ns']==d['activation_commit_ns']
            and d['sequence']==p['decision_sequence'] and d['activation_commit_ns']==p['activation_commit_ns'],'healthy_Witness_exact_activation')
        physical=[r for r in pub if r.get('type')=='controlled_decision_physical_return' and r['decision_sequence']==d['sequence']]
        need(len(physical)==1 and physical[0]['applied_sequence']==p['Applied_sequence'],'healthy_real_owner_physical_return')
        emissions=[r for r in pub if r.get('type')=='controlled_Applied_emitted' and r['applied_sequence']==p['Applied_sequence']]
        callbacks=[r for r in source if r.get('type')=='controlled_phase_callback' and r.get('accepted') and r['phase']['decision_sequence']==d['sequence']]
        need(len(emissions)==len(callbacks)==1,'healthy_actual_Applied_and_phase_callback')
        em,cb=emissions[0],callbacks[0]
        need(cb['authentication_reason']=='' and cb['phase']['applied_sequence']==p['Applied_sequence']
            and d['activation_commit_ns']<=em['applied_publish_end_ns']==p['Applied_publish_end_ns']
            <=cb['phase']['emitted_ns']==p['phase_emitted_ns']<=obs['finished_ns'],'healthy_API_authenticated_phase_order')
        details.append(dict(job_id=jid,decision_sequence=d['sequence'],Applied_sequence=p['Applied_sequence'],ready_margin_ns=j['deadline_ns']-d['ready_commit_ns']))
    close=b['close_ack']['observer']['observed_ns'];need(obs['finished_ns']<close,'healthy_observation_before_normal_close')
    return dict(passed=True,distinct_healthy_jobs=len(details),pairs=details,no_current_fault_transition=True,
        original_absolute_deadlines=True,stage_qualified=False,execute_qualified=False,research_conclusion=False)

def normal_tail(b):
    src,pub=b['source'],b['publisher'];result,ack,tail=b['result'],b['close_ack'],b['tail'];command=b['close_command'];session=b['publisher_session']
    need(result['fresh_recovery_case_completed'] is True and result['passed'] is True and result['normal_business_qualified'] is False
        and result['diagnostic_case_completed'] and not result.get('error') and result['close_errors']==[],'healthy_fixture_success_separate_from_business')
    need(result['close_policy']=='publisher-first' and b['inputs']['explicit_close_profile']=='normal','original_normal_close_profile')
    good=[r for r in src if r.get('type')=='adapter_driver_close_observed']
    need(len(good)==1 and not any(r.get('type')=='adapter_close_evidence_failed' for r in src)
        and ack['observer']==good[0] and ack['request_sha256']==good[0]['request_sha256']==b['close_command_sha256'],'unique_actual_close_request_ACK')
    at=good[0]['observed_ns'];need(command['request_ns']<=at and ack['publisher_still_alive'] is True,'normal_close_requested_while_Publisher_alive')
    need(not any(r['submit_commit_ns']>at for r in src if r.get('type')=='job')
        and not any(r['activation_commit_ns']>at and r['accepted'] for r in src if r.get('type')=='decision'),'no_new_authorization_after_close_ACK')
    anchors=[r for r in src if r.get('type')=='legacy_anchor'];callbacks=[r for r in src if r.get('type')=='adapter_applied_callback'];last=session['streams']['applied']['last_sequence']
    need(anchors and [r['sequence'] for r in anchors]==list(range(1,last+1)),'full_original_normal_anchor_population')
    need([r['sequence'] for r in callbacks]==list(range(1,last+1)),'full_actual_Applied_callback_population')
    need(tail['publisher_session_sha256']==b['publisher_session_sha256'] and tail['observer_last_applied_sequence']==tail['publisher_last_applied_sequence']==last
        and tail['complete_observer_anchor_count']==len(anchors) and tail['transport_counts']==tail['expected_counts']
        and tail['receiver_roles_alive'] is True,'original_full_normal_tail_ACK_binding')
    zero=[r for r in pub if r.get('type')=='controlled_Applied_emitted' and r['control_source']=='shutdown_zero']
    need(len(zero)==1 and zero[0]['applied_sequence']==last and zero[0]['final_n']==[0.,0.]
        and command['request_ns']<=zero[0]['left_start_ns'],'actual_zero_tail_after_close_request')
    need(anchors[-1]['final_n']==[0.,0.] and anchors[-1]['applied']['left_publish_success'] and anchors[-1]['applied']['right_publish_success'],'normal_anchor_tail_actual_both_API_zero')
    summaries=[r for r in src if r.get('type')=='source_summary'];need(len(summaries)==1 and src[-1] is summaries[0]
        and summaries[0]['normal_source_complete'] and summaries[0]['dropped']==0
        and summaries[0]['generated']==summaries[0]['emitted']==len(src)-1,'normal_Observer_Source_complete')
    need(b['witness']['closed'] and b['witness']['observation_complete'] and not b['witness']['incomplete'] and not b['witness']['overflow'],'normal_Witness_closed_complete')
    clean=[r for r in b['ledger'] if r['type']=='cleanup_result'];need([r['name'] for r in clean]==['publisher','observer','worker','synthetic_source','recorder'],'normal_five_role_cleanup_order')
    need(result['cleanup_complete'] and result['cleanup_within_budget'] and result['owned_role_returncodes']=={k:0 for k in ROLES},'normal_five_owned_resources_closed')
    need(not any(r.get('signal') in [19,15,9] for r in b['ledger']),'normal_close_without_pause_or_forced_cleanup')
    return dict(passed=True,selected_normal_resource_close_verified=True,original_normal_tail_verified=True,anchor_count=len(anchors),
        final_zero_Applied_sequence=last,all_five_returns_zero=True,normal_business_qualified=False,
        stage_qualified=False,execute_qualified=False,research_conclusion=False)
