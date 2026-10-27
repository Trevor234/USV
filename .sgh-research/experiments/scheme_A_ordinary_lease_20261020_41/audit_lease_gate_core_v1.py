"""Driver-independent actual receipt-lease trigger, monitor entry and post-exit queue proof."""
def need(v,w):
    if not v:raise ValueError(w)

def check(source,worker,witness,report,ledger,manifests,result,contract,stimulus,resumed,commands,prefix,prepared):
    om,wm,pm=[manifests[k] for k in ['observer','worker','publisher']]
    terminals=[r for r in source if r.get('type')=='worker_unusable_transition'];need(len(terminals)==1,'unique_terminal');terminal=terminals[0];t=terminal['check_ns'];last=terminal['capability_last_valid_commit_ns']
    pauses=[r for r in source if r.get('type')=='diagnostic_c38_gate_paused'];resumes=[r for r in source if r.get('type')=='diagnostic_c38_gate_resumed']
    need(len(pauses)==len(resumes)==1,'unique_actual_pause_resume');pause,resume=pauses[0],resumes[0];start,end=pause['gate']['paused_ns'],resume['gate']['resumed_ns']
    need(last<=start<t<end<pause['gate']['deadline_ns'] and t-last>contract['worker_capability_receipt_timeout_ns'],'receipt_expiry_inside_paused_interval')
    need(stimulus['pause']['ack']==pause and resumed['resume']['ack']==resume and result['lease_stimulus']==stimulus
        and result['lease_resume']==resumed,'driver_proofs_match_actual_Source')
    need(stimulus['delayed_900ms_observation_used'] is False and stimulus['process_pause_used'] is False
        and resumed['same_run_revival'] is False,'explicit_immediate_monitor_without_process_pause')
    entry=[r for r in ledger if r['type']=='ordinary_lease_monitor_entered'];need(len(entry)==1,'unique_monitor_entry')
    need(pause['checked_ns']<=stimulus['ready_for_monitor_ns']<=entry[0]['monotonic_ns']<t
        and entry[0]['pause_ack_ns']==pause['checked_ns'] and entry[0]['pause_command_sha256']==commands['pause']['sha256']
        and entry[0]['delayed_900ms_observation_used'] is False,'ordinary_monitor_entered_before_actual_terminal')
    need(not any(r.get('type') in ['diagnostic_c38_gate_timeout','diagnostic_c38_gate_rejected'] for r in source),'no_implicit_gate_timeout_or_rejection')
    for action,row in [('pause',pause),('resume',resume)]:
        command=commands[action]['value'];gate=row['gate'];is_resume=action=='resume'
        need(command['schema']=='p1-C3.8-applied-gate-v1' and command['action']==action
            and command['run_id']==om['run_id'] and command['boot_id']==om['boot_id']
            and command['owner_manifest_sha256']==prepared['roles']['publisher']['manifest_sha256']
            and command['seq']==(2 if is_resume else 1) and command['stage_qualified'] is False,'actual_gate_command_binding:'+action)
        need(row['request_sha256']==commands[action]['sha256'] and row['gate_interface']=='worker'
            and row['group_registered'] is is_resume and gate['state']==('resumed' if is_resume else 'paused')
            and gate['ttl_ns']==3500000000 and gate['deadline_ns']==start+3500000000,'actual_gate_state:'+action)
        for k in ['run_id','boot_id','driver_pid','driver_start_ticks','driver_tool_sha256','owner_manifest_sha256']:
            need(type(gate[k]) is type(command[k]) and gate[k]==command[k],'actual_native_gate_identity:'+k)
        complete=end if is_resume else start
        need(command['issued_ns']<=complete<=row['checked_ns']<gate['deadline_ns'],'gate_freshness_and_completion:'+action)
    need(all(commands['pause']['value'][k]==commands['resume']['value'][k] for k in ['driver_pid','driver_start_ticks','driver_tool_sha256']),'same_exact_driver_for_resume')
    need(not any(r.get('type')=='adapter_worker_callback' and start<r['entry_ns']<end for r in source)
        and not any(r.get('type')=='capability_admission' and start<r['validation_commit_ns']<end for r in source),
        'no_worker_callback_inside_removed_group')
    for k in ['candidate_callback_sequence','capability_callback_sequence','candidate_received','capability_received']:
        need(pause[k]==resume[k],'native_receive_population_frozen:'+k)
    clean=[r for r in ledger if r['type']=='cleanup_result' and r['name']=='worker'];need(len(clean)==1,'one_actual_Worker_cleanup')
    need(clean[0]['cleanup_complete'] and clean[0]['remaining_members']==[] and clean[0]['returncode']==0
        and t<=clean[0]['cleanup_finished_ns']<=clean[0]['monotonic_ns']<commands['resume']['value']['issued_ns'],
        'resume_only_after_registered_Worker_fully_stopped')
    calls=[r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker'];need(calls,'actual_worker_stop_call')
    publications=[r for r in worker if r.get('type')=='capability_publish_result' and r['returned'] and start<r['publish_start_ns']<t]
    need(len(publications)>=2,'actual_Worker_publishes_while_Observer_callbacks_paused')
    need(all(r['publish_end_ns']<=clean[0]['cleanup_finished_ns'] for r in publications),'publications_before_actual_exit')
    post=[r for r in source if r.get('type')=='adapter_worker_callback' and r['entry_ns']>=end]
    caps=[r for r in post if r['interface']=='capability'];need(caps,'actual_post_exit_capability_callback_required')
    need(resumed['finished_ns']<=resumed['deadline_ns'] and resumed['post_exit_capability_callbacks_observed']>=1
        and set(resumed['callback_sequences']).issubset({r['callback_sequence'] for r in caps}),'actual_resume_observation_bound')
    for row in post:
        need(row['authentication_reason']=='worker_process_exited' and row['worker_process_alive_at_guard'] is False
            and row['semantic_callback_invoked'] is False and row['raw_input'] is None and not row['full_cdr_serialized']
            and row['before']==row['after'] and row['after']['worker_unusable']
            and row['after']['lease_last_valid_ns']==last and row['after']['worker_instance']==wm['worker_instance']
            and row['actual_gid']==row['expected_gid'],'queued_old_instance_denied_without_business_change')
    need(not any(r.get('type')=='capability_admission' and r['validation_commit_ns']>t and r['renewed'] for r in source)
        and not any(r['commit_ns']>t for r in witness['submit'])
        and not any(r['accepted'] and r['commit_ns']>t for r in witness['activation']),'no_old_instance_revival')
    d,phase,applied=prefix['decision'],prefix['phase_callback'],prefix['Applied']
    need(d in source and phase in source and d['accepted'] and phase['accepted'] and phase['authentication_reason']==''
        and phase['phase']['decision_sequence']==d['sequence']==stimulus['prefix_decision_sequence']
        and phase['phase']['applied_sequence']==applied['applied_sequence']==stimulus['prefix_Applied_sequence']
        and d['activation_commit_ns']<=applied['applied_publish_end_ns']<=phase['phase']['emitted_ns']<start,
        'actual_healthy_accepted_Applied_phase_before_stimulus')
    need(wm['effective_parameters']['diagnostic_v2_policy']['value']=='none' and wm['effective_parameters']['diagnostic_v2_block_ms']['value']==0
        and om['effective_parameters']['diagnostic_c38_mode']['value']=='worker-gate','only_callback_stimulus_enabled')
    return dict(passed=True,ordinary_lease_case=True,last_valid_receipt_ns=last,actual_terminal_ns=t,
        receipt_age_at_expiry_ns=t-last,pause_ns=start,resume_ns=end,pause_elapsed_ns=end-start,
        monitor_entered_before_terminal_ns=t-entry[0]['monotonic_ns'],actual_capability_publish_returns_while_paused_before_terminal=len(publications),
        post_exit_capability_callbacks=len(caps),post_exit_all_worker_callbacks=len(post),same_run_revival=False,
        queued_payload_full_CDR_identity_claimed=False,source_packet_freshness_proven=False,
        Worker_stop_completed_before_resume=True,native_C_hang_proven=False,stage_qualified=False,execute_qualified=False,research_conclusion=False)
