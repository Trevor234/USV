"""Independent Source/ledger reconstruction of the explicit forced escalation case."""
from audit_v2_core_base_v1 import terminal_source_cause


def need(value, why):
    if not value:
        raise ValueError(why)


def check(source,worker,witness,report,ledger,manifests,result,contract,trailing_bytes,prepared):
    terminals=[r for r in source if r.get('type')=='worker_unusable_transition']
    need(len(terminals)==1,'one_actual_terminal')
    terminal=terminals[0];t=terminal['check_ns']
    need(terminal_source_cause(terminal,source)=='active_watchdog','actual_active_watchdog_causal_chain')
    caps=sorted([r for r in source if r.get('type')=='capability_admission' and r['renewed']
                 and r['validation_commit_ns']<t],key=lambda r:r['validation_commit_ns'])
    active,since=0,0
    for r in caps:
        if r['capability']['active_job']!=active:active=r['capability']['active_job'];since=r['validation_commit_ns']
    need(active==terminal['active_job'] and active>0 and t-since>contract['active_watchdog_ns']
         and 0<=t-caps[-1]['validation_commit_ns']<=contract['worker_capability_receipt_timeout_ns'],
         'real_active_expiry_with_live_receipt_lease')
    cue=[r for r in ledger if r['type']=='bridge_notice_authenticated']
    need(len(cue)==1,'one_authenticated_notice')
    cue=cue[0];om,wm=manifests['observer'],manifests['worker']
    startup=[r for r in source if r.get('type')=='startup']
    need(len(startup)==1 and startup[0]['pid']==om['pid'] and startup[0]['boot']==om['boot_id']
         and startup[0]['run_id']==om['run_id'] and startup[0]['contract_hash']==om['contract_sha256']
         and startup[0]['mode']=='shadow','actual_Source_Observer_startup')
    need(cue['run_id']==om['run_id'] and cue['boot_id']==om['boot_id']
         and cue['notice']['terminal']==terminal and cue['Source_fd_identity']==om['source_fd']
         and cue['Observer_manifest_sha256']==report['cue']['Observer_manifest_sha256']
         and cue['Worker_manifest_sha256']==report['cue']['Worker_manifest_sha256'], 'notice_identity_and_real_Source')
    need(cue['Observer_manifest_sha256']==prepared['roles']['observer']['manifest_sha256']
         and cue['Worker_manifest_sha256']==prepared['roles']['worker']['manifest_sha256'], 'notice_prepared_manifest_binding')
    need(t<=cue['read_end_ns']<=cue['parsed_ns']<=cue['authenticated_ns']
         and cue['authenticated_ns']-t<=250_000_000, 'measured_notification_not_assumed_zero')
    stopped=[r for r in ledger if r['type']=='diagnostic_Worker_stopped_after_terminal']
    need(len(stopped)==1,'explicit_diagnostic_pause')
    stopped=stopped[0]
    need(stopped['observed_identity']['state']=='T'
         and stopped['observed_identity']['pid']==wm['pid']
         and stopped['observed_identity']['start_ticks']==wm['process_start_ticks'], 'actual_stopped_exact_Worker')
    calls=[r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker']
    need([r['signal'] for r in calls]==[19,2,15,9], 'actual_full_diagnostic_escalation_chain')
    for r in calls:
        need(r['returned'] is True and r['process_lookup_error'] is False and r['error'] is None
             and r['call_start_ns']<=r['call_end_ns'] and r['target_pgid']==wm['pgid'],'actual_successful_killpg_call')
        ident=r['registered_identity']
        for mk,ik in [('pid','pid'),('process_start_ticks','start_ticks'),('pgid','pgid'),('sid','sid'),('exe','exe'),('binary_sha256','exe_sha256')]:
            need(wm[mk]==ident[ik],'signal_registered_identity:'+mk)
        need(len(r['members_checked_before_call'])==1,'one_expected_group_member')
        member=r['members_checked_before_call'][0]
        need(all(member[k]==ident[k] for k in ['pid','pgid','sid','start_ticks','exe']),'signal_checked_current_group_identity')
    pause,interrupt,term,kill=calls
    need(cue['authenticated_ns']<=pause['call_start_ns']<=pause['call_end_ns']<=stopped['observed_ns']
         <=interrupt['call_start_ns'] and interrupt['call_start_ns']-cue['authenticated_ns']<=100_000_000,
         'authenticate_then_pause_then_prompt_SIGINT')
    outcomes=[r for r in ledger if r['type']=='wait_result' and r['name']=='worker']
    by={r['stage']:r for r in outcomes}
    expected={'worker_grace':contract['worker_grace_ns'],'term_grace':contract['term_grace_ns'],
              'kill_postcheck':contract['kill_postcheck_ns']}
    need(expected=={'worker_grace':500_000_000,'term_grace':1_000_000_000,'kill_postcheck':1_000_000_000},
         'actual_diag10_wait_sources')
    for stage,budget in expected.items():
        row=by[stage]
        need(row['budget_ns']==budget and row['deadline_ns']==row['started_ns']+budget
             and row['started_ns']<=row['returned_ns']<=row['deadline_ns']+100_000_000,
             'declared_wait_and_observed_scheduler_slack:'+stage)
    need(by['worker_grace']['empty'] is False and by['term_grace']['empty'] is False
         and by['kill_postcheck']['empty'] is True,'required_escalation_is_not_skipped')
    need(interrupt['call_end_ns']<=by['worker_grace']['started_ns']
         and by['worker_grace']['deadline_ns']<=by['worker_grace']['returned_ns']<=term['call_start_ns']
         and term['call_end_ns']<=by['term_grace']['started_ns']
         and by['term_grace']['deadline_ns']<=by['term_grace']['returned_ns']<=kill['call_start_ns']
         and kill['call_end_ns']<=by['kill_postcheck']['started_ns'],'each_signal_wait_escalation_causal_order')
    cleanup=[r for r in ledger if r['type']=='cleanup_result' and r['name']=='worker']
    need(len(cleanup)==1 and cleanup[0]['returncode']==-9 and cleanup[0]['cleanup_complete']
         and cleanup[0]['remaining_members']==[] and not cleanup[0]['qualification_clean'],'forced_exit_resource_vs_qualification')
    need(not any(r.get('type')=='worker_summary' for r in worker),'killed_Worker_Source_not_falsely_complete')
    barriers=[r for r in worker if r.get('type')=='diagnostic_v2_pre_native_enter']
    need(len(barriers)==1 and barriers[0]['job_id']==active and barriers[0]['actual_native_invoked'] is False
         and barriers[0]['start_ns']<t and not any(r.get('type')=='diagnostic_v2_pre_native_release' for r in worker),
         'controlled_pre_native_work_then_diagnostic_process_pause_not_native_C_hang')
    need(not any(r['commit_ns']>t for r in witness['submit'])
         and not any(r['accepted'] and r['commit_ns']>t for r in witness['activation']),'no_new_authorization_after_terminal')
    need(all(not r['renewed'] and r['terminal_run'] for r in source if r.get('type')=='capability_admission'
             and r['validation_commit_ns']>t),'terminal_lease_does_not_revive')
    need(witness['closed'] and witness['observation_complete'] and not witness['overflow'] and not witness['incomplete'],
         'Observer_Witness_closes_independently_of_forced_Worker')
    summary=[r for r in source if r.get('type')=='source_summary']
    need(len(summary)==1 and summary[0]['generated']==summary[0]['emitted'] and summary[0]['dropped']==0,'Observer_Source_complete')
    decisions=[r for r in source if r.get('type')=='decision' and t<=r['start_ns']<=cleanup[0]['cleanup_finished_ns']]
    need(len(decisions)>=5 and all(not r['accepted'] and r['skipped_ticks']==0 for r in decisions),'tick_fallback_continues_during_supervision')
    gaps=[b['start_ns']-a['start_ns'] for a,b in zip(decisions,decisions[1:])]
    jitter=max(max(r['start_ns']-r['planned_ns'],r['activation_commit_ns']-r['planned_ns']) for r in decisions)
    need(max(gaps)<=240_000_000 and jitter<=20_000_000,'finite_tick_engineering_gate_during_escalation')
    need(result['supervision_case_completed'] and result['passed'] is False and result['evidence_qualification_clean'] is False
         and report['passed'] and not report['normal_Worker_Source_complete'],'separate_diagnostic_and_normal_status')
    return {'passed':True,'first_raw_reason':terminal['reason'],'first_cause':'active_watchdog','blocked_job_id':active,
            'notification_to_authenticated_ns':cue['authenticated_ns']-t,'read_visibility_upper_observation_ns':cue['read_end_ns']-t,
            'authenticated_to_SIGINT_start_ns':interrupt['call_start_ns']-cue['authenticated_ns'],
            'terminal_to_SIGINT_start_ns':interrupt['call_start_ns']-t,
            'SIGINT_to_TERM_start_ns':term['call_start_ns']-interrupt['call_end_ns'],
            'TERM_to_KILL_start_ns':kill['call_start_ns']-term['call_end_ns'],
            'KILL_return_to_group_empty_observed_ns':by['kill_postcheck']['returned_ns']-kill['call_end_ns'],
            'terminal_to_Worker_cleanup_ns':cleanup[0]['cleanup_finished_ns']-t,
            'contract_waits_ns':expected,'Worker_returncode':-9,'Worker_normal_Source_qualified':False,
            'Worker_source_trailing_bytes_preserved':trailing_bytes,'diagnostic_SIGSTOP_after_real_terminal':True,
            'ongoing_fallback_Decisions':len(decisions),'max_tick_start_gap_ns':max(gaps),
            'max_start_or_activation_jitter_ns':jitter,'native_C_hang_proven':False,
            'universal_notification_WCET_or_stage_qualification':False}
