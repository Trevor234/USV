"""Explicit Source causes -> one authenticated registered Worker stop, without pause."""
import hashlib
import json
from pathlib import Path
import signal
import time
from supervision_bridge_v1 import SourceCursor

PROFILE='source-terminal-owned-stop-v1'
CAUSES=('active_watchdog','worker_capability_expired')
NOTICE_BUDGET_NS=250_000_000
AUTH_TO_INT_BUDGET_NS=100_000_000
WAIT_OBSERVATION_SLACK_NS=100_000_000

def need(value,why):
    if not value:raise ValueError(why)

def equal(value,expected,why):
    need(type(value) is type(expected) and value==expected,why)

def validate_notice(records,expected,contract,now_ns=None):
    """Pure causal dispatch selection. It never authorizes a signal by itself."""
    startup=[r for r in records if r.get('type')=='startup']
    need(len(startup)==1,'unique_Observer_Source_startup')
    start=startup[0]
    for k,v in [('run_id',expected['run_id']),('boot',expected['boot_id']),('pid',expected['observer_pid']),
                ('contract_hash',expected['contract_sha256']),('mode','shadow'),('clock','CLOCK_MONOTONIC'),
                ('physical_publisher_endpoints',0)]:equal(start.get(k),v,'Source_startup_binding:'+k)
    terminals=[r for r in records if r.get('type')=='worker_unusable_transition']
    if not terminals:return None
    need(len(terminals)==1,'unique_terminal_notice')
    terminal=terminals[0];t=terminal['check_ns'];now=time.monotonic_ns() if now_ns is None else now_ns
    need(type(t) is int and expected['prepare_start_ns']<=t<=now,'terminal_time_domain')
    equal(terminal['worker_pid'],expected['worker_pid'],'terminal_exact_Worker_pid')
    equal(terminal['worker_instance'],expected['worker_instance'],'terminal_exact_Worker_instance')
    need(terminal['candidate_after'] is False and terminal['pending_after'] is False,'terminal_invalidates_uncommitted_work')
    timeout=contract['worker_capability_receipt_timeout_ns']
    equal(terminal['capability_timeout_ns'],timeout,'terminal_exact_receipt_timeout')
    raw=terminal['reason'];cause=raw
    wrapped={('legacy_ready_invalidated:worker_unusable:'+c):c for c in CAUSES}
    if raw in wrapped:
        cause=wrapped[raw]
        links=[r for r in records if r.get('type')=='legacy_ready_invalidated'
               and r.get('check_ns')==t and r.get('reason')=='worker_unusable:'+cause]
        need(len(links)==1 and links[0]['terminal'] is True and links[0]['measurement_eligible'] is False
             and records.index(links[0])<records.index(terminal),'paired_causal_readiness_invalidation')
    need(cause in CAUSES,'unsupported_terminal_cause')
    caps=[r for r in records if r.get('type')=='capability_admission' and r.get('renewed') is True
          and r['validation_commit_ns']<t]
    need(caps,'prior_valid_capability')
    need(all(a['validation_commit_ns']<b['validation_commit_ns'] for a,b in zip(caps,caps[1:])),
         'Source_renewal_commit_order')
    active,since=0,0
    for r in caps:
        need(r['valid'] is True and r['identity_valid'] is True and r['terminal_run'] is False,'capability_validity')
        c=r['capability']
        for k,v in [('run_id',expected['run_id']),('boot_id',expected['boot_id']),
                    ('pid',expected['worker_pid']),('worker_instance',expected['worker_instance']),
                    ('contract_hash',expected['contract_sha256']),('nominal_hash',expected['nominal_hash'])]:
            equal(c.get(k),v,'capability_exact_identity:'+k)
        need(type(c['active_job']) is int and c['active_job']>=0,'active_job_domain')
        if c['active_job']!=active:active=c['active_job'];since=r['validation_commit_ns']
    last=caps[-1]['validation_commit_ns']
    equal(last,terminal['capability_last_valid_commit_ns'],'terminal_last_renewal_binding')
    equal(active,terminal['active_job'],'terminal_active_job_binding')
    if cause=='active_watchdog':
        need(active>0 and since>0 and t-since>contract['active_watchdog_ns'] and 0<=t-last<=timeout,
             'active_watchdog_requires_active_age_and_live_receipt_lease')
    else:need(t-last>timeout,'receipt_lease_expiration_requires_actual_elapsed_age')
    binding={k:expected[k] for k in ['run_id','boot_id','contract_sha256','worker_pid','worker_instance']}
    return dict(terminal=terminal,cause=cause,raw_reason=raw,active_origin_ns=since,last_valid_receipt_ns=last,
                binding=binding,action='stop_registered_Worker')

class DispatchOnce:
    """A synchronous one-shot action for the exact supervisor registry entry."""
    def __init__(self):self.key=None
    def run(self,*,sup,item,notice,current_worker,contract):
        need(self.key is None,'terminal_dispatch_already_consumed')
        need(notice['cause'] in CAUSES and notice['action']=='stop_registered_Worker','explicit_supported_stop_action')
        need(sup.owned.get('worker') is item,'registered_Worker_object_required')
        manifest,actual=current_worker['manifest'],current_worker['actual']
        equal(manifest['role'],'worker','authenticated_role_must_be_Worker')
        equal(manifest['boot_id'],sup.boot,'authenticated_boot_binding')
        for k in ['run_id','boot_id','contract_sha256','worker_instance']:
            equal(manifest[k],notice['binding'][k],'notice_authenticated_binding:'+k)
        equal(manifest['pid'],notice['binding']['worker_pid'],'notice_authenticated_binding:pid')
        for mk,ik in [('pid','pid'),('process_start_ticks','start_ticks'),('pgid','pgid'),('sid','sid'),
                      ('exe','exe'),('binary_sha256','exe_sha256')]:
            equal(manifest[mk],item.identity[ik],'manifest_registered_identity:'+mk)
            equal(actual[ik],item.identity[ik],'authenticated_registered_identity:'+ik)
        equal(notice['terminal']['worker_pid'],manifest['pid'],'notice_registered_Worker_pid')
        equal(notice['terminal']['worker_instance'],manifest['worker_instance'],'notice_registered_Worker_instance')
        waits={k:contract[k] for k in ['worker_grace_ns','term_grace_ns','kill_postcheck_ns']}
        need(all(type(v) is int and 0<=v<=60_000_000_000 for v in waits.values()),'finite_contract_stop_waits')
        key=dict(profile=PROFILE,boot_id=sup.boot,run_id=manifest['run_id'],worker_instance=manifest['worker_instance'],
                 pid=manifest['pid'],start_ticks=manifest['process_start_ticks'],terminal_check_ns=notice['terminal']['check_ns'])
        self.key=hashlib.sha256(json.dumps(key,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        # Consumed before stop: a stop exception cannot replay the notification.
        sup.event('ordinary_worker_stop_dispatched',name='worker',dispatch_key=self.key,
                  dispatch_identity=key,cause=notice['cause'],declared_waits_ns=waits,diagnostic_process_pause=False)
        cleanup=sup.stop(item,waits['worker_grace_ns']/1e9,waits['term_grace_ns']/1e9,waits['kill_postcheck_ns']/1e9)
        return cleanup

def supervise(root,*,roles,owned,sup,authenticate,source_fd_matches,contract,prepare_start_ns,
              overall_deadline_ns,spin,bound,create_only_json,profile):
    need(profile==PROFILE,'explicit_ordinary_supervision_profile')
    root=Path(root);started=time.monotonic_ns();deadline=min(started+8_000_000_000,overall_deadline_ns-15_000_000_000)
    om,wm=roles['observer']['manifest'],roles['worker']['manifest'];path=root/'observer/source.jsonl'
    current=authenticate('observer');source_fd_matches(current,path)
    need(current['sha256']==roles['observer']['sha256'],'initial_Observer_manifest_changed')
    expected=dict(run_id=om['run_id'],boot_id=sup.boot,observer_pid=om['pid'],contract_sha256=om['contract_sha256'],
        worker_pid=wm['pid'],worker_instance=wm['worker_instance'],nominal_hash=wm['nominal_hash'],prepare_start_ns=prepare_start_ns)
    cursor=SourceCursor(path,om['source_fd']);dispatch=DispatchOnce()
    try:
        notice=None
        while time.monotonic_ns()<deadline:
            bound();records=cursor.poll();notice=validate_notice(records,expected,contract)
            if notice:break
            spin(.005)
        need(notice is not None,'ordinary_terminal_notification_deadline')
        parsed_ns=time.monotonic_ns();read_end_ns=cursor.read_end_by_index[records.index(notice['terminal'])]
        current=authenticate('observer');source_fd_matches(current,path);cursor.verify()
        worker=authenticate('worker')
        need(current['sha256']==roles['observer']['sha256'] and worker['sha256']==roles['worker']['sha256'],
             'notification_role_manifest_changed')
        authenticated_ns=time.monotonic_ns()
        cue=dict(schema='ordinary-owned-Source-terminal-notice/v1',profile=PROFILE,run_id=om['run_id'],boot_id=sup.boot,
            Observer_manifest_sha256=current['sha256'],Worker_manifest_sha256=worker['sha256'],Source_fd_identity=om['source_fd'],
            notice=notice,read_end_ns=read_end_ns,parsed_ns=parsed_ns,authenticated_ns=authenticated_ns,
            notification_budget_ns=NOTICE_BUDGET_NS,actual_Source_flush_time_known=False)
        sup.event('ordinary_notice_authenticated',name='worker',**cue)
        stop_called_ns=time.monotonic_ns()
        cleanup=dispatch.run(sup=sup,item=owned['worker'],notice=notice,current_worker=worker,contract=contract)
        events=[r for r in sup.memory_tail if r.get('name')=='worker']
        calls=[r for r in events if r['type']=='signal_call_result'];stages=[r for r in events if r['type']=='wait_result']
        signals=[r['signal'] for r in calls];waits={k:contract[k] for k in ['worker_grace_ns','term_grace_ns','kill_postcheck_ns']}
        stage_key={'worker_grace':'worker_grace_ns','term_grace':'term_grace_ns','kill_postcheck':'kill_postcheck_ns'}
        stage_checks=all(r['stage']=='natural' or (r['stage'] in stage_key and r['budget_ns']==waits[stage_key[r['stage']]]
            and r['returned_ns']<=r['deadline_ns']+WAIT_OBSERVATION_SLACK_NS) for r in stages)
        first=calls[0] if calls else None
        passed=bool(first and signals in [[2],[2,15],[2,15,9]]
            and all(r['returned'] and not r['process_lookup_error'] and r['error'] is None for r in calls)
            and cleanup['cleanup_complete'] and cleanup['remaining_members']==[]
            and not sup.evidence_failed and not sup.unexpected_descendants and stage_checks
            and authenticated_ns-notice['terminal']['check_ns']<=NOTICE_BUDGET_NS
            and first['call_start_ns']-authenticated_ns<=AUTH_TO_INT_BUDGET_NS and time.monotonic_ns()<=deadline)
        report=dict(schema='ordinary-Source-owned-stop/v1',profile=PROFILE,passed=passed,cue=cue,
            dispatch_key=dispatch.key,stop_called_ns=stop_called_ns,declared_waits_ns=waits,signal_calls=calls,
            wait_results=stages,cleanup=cleanup,finished_ns=time.monotonic_ns(),deadline_ns=deadline,
            notification_delay_ns=authenticated_ns-notice['terminal']['check_ns'],notification_budget_ns=NOTICE_BUDGET_NS,
            authenticated_to_INT_budget_ns=AUTH_TO_INT_BUDGET_NS,diagnostic_SIGSTOP_injected_after_terminal=False,
            Worker_Source_complete_claimed_by_dispatcher=False,native_C_hang_proven=False,
            WCET_or_universal_notification_bound_proven=False,all_terminal_causes_supported=False,
            supported_causes=list(CAUSES),stage_qualified=False,execute_qualified=False,research_conclusion=False)
        create_only_json(root/'ordinary_supervision.json',report)
        need(passed,'ordinary_stop_case_criteria_not_met')
        return report
    finally:cursor.close()
