"""Independent Source, fixed Witness and actual syscall/wait reconstruction."""
import hashlib
import json
from audit_v2_core_base_v1 import terminal_source_cause
def need(v,w):
    if not v:raise ValueError(w)
def check(source,worker,witness,report,ledger,manifests,result,contract,trailing_bytes,prepared):
    terminals=[r for r in source if r.get('type')=='worker_unusable_transition']
    need(len(terminals)==1,'one actual Worker terminal')
    terminal=terminals[0];t=terminal['check_ns'];cause=terminal_source_cause(terminal,source)
    need(cause=='active_watchdog','selected actual ordinary active case')
    om,wm=manifests['observer'],manifests['worker']
    need(terminal['worker_pid']==wm['pid'] and terminal['worker_instance']==wm['worker_instance'], 'Source terminal exact Worker')
    caps=sorted([r for r in source if r.get('type')=='capability_admission' and r['renewed']
                 and r['validation_commit_ns']<t],key=lambda r:r['validation_commit_ns'])
    need(caps,'prior renewed capability')
    active,since=0,0
    for r in caps:
        c=r['capability'];need(r['valid'] and r['identity_valid'] and not r['terminal_run'],'valid preterminal receipt')
        need(c['worker_instance']==wm['worker_instance'] and c['pid']==wm['pid'] and c['run_id']==wm['run_id']
             and c['boot_id']==wm['boot_id'] and c['contract_hash']==wm['contract_sha256'],'capability actual identity')
        if c['active_job']!=active:active=c['active_job'];since=r['validation_commit_ns']
    need(active==terminal['active_job'] and active>0 and t-since>contract['active_watchdog_ns']
         and caps[-1]['validation_commit_ns']==terminal['capability_last_valid_commit_ns']
         and 0<=t-caps[-1]['validation_commit_ns']<=contract['worker_capability_receipt_timeout_ns'],
         'active age expired with live receipt lease')
    startup=[r for r in source if r.get('type')=='startup']
    need(len(startup)==1 and startup[0]['pid']==om['pid'] and startup[0]['run_id']==om['run_id']
         and startup[0]['contract_hash']==om['contract_sha256'] and startup[0]['boot']==om['boot_id']
         and startup[0]['mode']=='shadow','exact owned Source startup')
    cues=[r for r in ledger if r['type']=='ordinary_notice_authenticated']
    dispatched=[r for r in ledger if r['type']=='ordinary_worker_stop_dispatched']
    need(len(cues)==len(dispatched)==1,'one authenticated notice and one dispatch')
    cue,dispatch=cues[0],dispatched[0]
    need(cue['notice']['terminal']==terminal and cue['notice']['cause']==cause
         and cue['run_id']==om['run_id'] and cue['boot_id']==om['boot_id']
         and cue['Source_fd_identity']==om['source_fd'],'notice Source identity and actual cause')
    need(cue['Observer_manifest_sha256']==prepared['roles']['observer']['manifest_sha256']
         and cue['Worker_manifest_sha256']==prepared['roles']['worker']['manifest_sha256'],'notice manifests reauthenticated')
    need(cue['notice']['binding']==dict(run_id=wm['run_id'],boot_id=wm['boot_id'],contract_sha256=wm['contract_sha256'],
         worker_pid=wm['pid'],worker_instance=wm['worker_instance']),'notice exact authenticated instance binding')
    need(t<=cue['read_end_ns']<=cue['parsed_ns']<=cue['authenticated_ns']
         and cue['authenticated_ns']-t<=250_000_000,'measured notification budget')
    key=dict(profile='source-terminal-owned-stop-v1',boot_id=wm['boot_id'],run_id=wm['run_id'],worker_instance=wm['worker_instance'],
             pid=wm['pid'],start_ticks=wm['process_start_ticks'],terminal_check_ns=t)
    digest=hashlib.sha256(json.dumps(key,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    need(dispatch['dispatch_identity']==key and dispatch['dispatch_key']==report['dispatch_key']==digest
         and dispatch['cause']==cause and dispatch['diagnostic_process_pause'] is False,'single exact dispatch key')
    calls=[r for r in ledger if r['type']=='signal_call_result' and r['name']=='worker']
    need(calls and [r['signal'] for r in calls] in [[2],[2,15],[2,15,9]],'ordinary escalation prefix without SIGSTOP')
    need(not any(r.get('signal')==19 for r in ledger),'no process pause anywhere in owned ledger')
    for r in calls:
        need(r['returned'] and not r['process_lookup_error'] and r['error'] is None and r['target_pgid']==wm['pgid']
             and r['call_start_ns']<=r['call_end_ns'],'successful actual killpg on owned group')
        identity=r['registered_identity']
        for mk,ik in [('pid','pid'),('process_start_ticks','start_ticks'),('pgid','pgid'),('sid','sid'),('exe','exe'),('binary_sha256','exe_sha256')]:
            need(wm[mk]==identity[ik],'signal exact registered identity:'+mk)
        need(len(r['members_checked_before_call'])==1,'one owned group member before signal')
        member=r['members_checked_before_call'][0]
        need(all(member[k]==identity[k] for k in ['pid','pgid','sid','start_ticks','exe']),'actual current group identity')
    need(cue['authenticated_ns']<=dispatch['monotonic_ns']<=calls[0]['call_start_ns']
         and calls[0]['call_start_ns']-cue['authenticated_ns']<=100_000_000,'authentication dispatch then immediate actual SIGINT')
    waits=[r for r in ledger if r['type']=='wait_result' and r['name']=='worker']
    expected={'worker_grace':contract['worker_grace_ns'],'term_grace':contract['term_grace_ns'],'kill_postcheck':contract['kill_postcheck_ns']}
    need(expected=={'worker_grace':500_000_000,'term_grace':1_000_000_000,'kill_postcheck':1_000_000_000},'actual diag10 stop waits')
    stages=['natural']+['worker_grace','term_grace','kill_postcheck'][:len(calls)]
    need([r['stage'] for r in waits]==stages,'one wait per actual escalation stage')
    need(waits[0]['budget_ns']==0 and waits[0]['empty'] is False,'original zero natural grace')
    for index,(call,row) in enumerate(zip(calls,waits[1:])):
        need(row['budget_ns']==expected[row['stage']] and row['deadline_ns']==row['started_ns']+row['budget_ns']
             and call['call_end_ns']<=row['started_ns']<=row['returned_ns']<=row['deadline_ns']+100_000_000,
             'contract wait observation and actual signal order')
        if index+1<len(calls):
            need(row['empty'] is False and row['deadline_ns']<=row['returned_ns']<=calls[index+1]['call_start_ns'],
                 'no early escalation before actual wait exhaustion')
        else:need(row['empty'] is True,'last observed wait sees empty group')
    clean=[r for r in ledger if r['type']=='cleanup_result' and r['name']=='worker']
    need(len(clean)==1 and clean[0]['cleanup_complete'] and clean[0]['remaining_members']==[]
         and clean[0]['returncode']==0 and clean[0]['qualification_clean'],'selected ordinary Worker exits normally')
    need(clean[0]['cleanup_started_ns']<=calls[0]['call_start_ns'] and waits[-1]['returned_ns']<=clean[0]['cleanup_finished_ns'],
         'owned stop starts before signal and completes after group observation')
    need(report['signal_calls']==calls and report['wait_results']==waits and report['cue']['notice']==cue['notice']
         and all(cue.get(k)==v for k,v in report['cue'].items())
         and report['cleanup']=={k:v for k,v in clean[0].items() if k not in ['type','monotonic_ns','boot_id']} and report['declared_waits_ns']==dispatch['declared_waits_ns'],
         'report agrees with raw dispatch signal wait and cleanup ledger')
    summary=[r for r in worker if r.get('type')=='worker_summary']
    need(trailing_bytes==0 and len(summary)==1 and worker[-1] is summary[0]
         and summary[0]['normal_source_complete'] and not summary[0]['fatal'] and not summary[0]['source_io_failed']
         and summary[0]['capability_source']['capability_source_complete']
         and summary[0]['source_rows_before_terminal']==summary[0]['source_rows_emitted_before_terminal']==len(worker)-1,
         'actual Worker Source complete after ordinary stop')
    barriers=[r for r in worker if r.get('type')=='diagnostic_v2_pre_native_enter']
    releases=[r for r in worker if r.get('type')=='diagnostic_v2_pre_native_release']
    need(len(barriers)==len(releases)==1 and barriers[0]['job_id']==releases[0]['job_id']==active
         and barriers[0]['actual_native_invoked'] is False and releases[0]['actual_native_invoked'] is False
         and barriers[0]['start_ns']<t and releases[0]['released_ns']>=calls[0]['call_start_ns']
         and releases[0]['stopping'] is True,'stop dispatched before pre-native diagnostic naturally returned')
    need(any(r.get('type')=='pending_expired_before_native' and r['job_id']==active and not r['solver_invoked'] for r in worker)
         and not any(r.get('type')=='candidate' and r['job']['job_id']==active for r in worker),'blocked expired work never invokes native or publishes candidate')
    need(not any(r['commit_ns']>t for r in witness['submit']) and not any(r['accepted'] and r['commit_ns']>t for r in witness['activation']),
         'no new submit or accepted activation after terminal')
    need(all(not r['renewed'] and r['terminal_run'] for r in source if r.get('type')=='capability_admission' and r['validation_commit_ns']>t),
         'same-run late capabilities cannot revive receipt lease')
    need(witness['closed'] and witness['observation_complete'] and not witness['overflow'] and not witness['incomplete'],'Observer Witness complete')
    obs_summary=[r for r in source if r.get('type')=='source_summary']
    need(len(obs_summary)==1 and obs_summary[0]['generated']==obs_summary[0]['emitted'] and obs_summary[0]['dropped']==0,'Observer Source complete')
    decisions=[r for r in source if r.get('type')=='decision' and t<=r['activation_commit_ns']<=clean[0]['cleanup_finished_ns']]
    need(decisions and all(not d['accepted'] and d['skipped_ticks']==0 for d in decisions),'fallback while stop is in progress')
    gaps=[b['start_ns']-a['start_ns'] for a,b in zip(decisions,decisions[1:])]
    jitter=max(max(d['start_ns']-d['planned_ns'],d['activation_commit_ns']-d['planned_ns']) for d in decisions)
    need(max(gaps,default=0)<=240_000_000 and jitter<=20_000_000,'finite tick engineering gates during owned stop')
    need(report['passed'] and not report['diagnostic_SIGSTOP_injected_after_terminal'] and not report['native_C_hang_proven']
         and result['ordinary_supervision_case_completed'] and result['passed'] is False
         and result['V2_case_completed'] is False and result['normal_business_qualified'] is False,'component success and normal business qualifications separated')
    return dict(passed=True,cause=cause,blocked_job_id=active,actual_signal_sequence=[r['signal'] for r in calls],Worker_returncode=0,
        Worker_normal_Source_complete=True,diagnostic_SIGSTOP_injected=False,ordinary_active_stop_case_completed=True,
        actual_lease_ordinary_stop_case_completed=False,notification_to_authenticated_ns=cue['authenticated_ns']-t,
        read_visibility_upper_observation_ns=cue['read_end_ns']-t,authenticated_to_SIGINT_start_ns=calls[0]['call_start_ns']-cue['authenticated_ns'],
        terminal_to_SIGINT_start_ns=calls[0]['call_start_ns']-t,terminal_to_Worker_cleanup_ns=clean[0]['cleanup_finished_ns']-t,
        SIGINT_to_group_empty_observed_ns=waits[-1]['returned_ns']-calls[0]['call_end_ns'],
        used_wait_stages=stages,contract_waits_ns=expected,ongoing_fallback_Decisions=len(decisions),
        max_tick_start_gap_ns=max(gaps,default=0),max_start_or_activation_jitter_ns=jitter,
        native_C_hang_proven=False,universal_notification_WCET_qualified=False,stage_qualified=False)
