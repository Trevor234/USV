"""Source-authenticated terminal -> exact-owned finite-stop bridge.

Source observation times are measured, not assumed instantaneous. Diagnostic
SIGSTOP is explicit and occurs only after authentication, to exercise all
escalation stages without changing a role ELF or claiming a native C-call hang.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time
from owned_process_supervisor import proc_identity

PROFILE='source-active-forced-escalation-v1'
NOTIFICATION_BUDGET_NS=250_000_000
AUTH_TO_INT_BUDGET_NS=100_000_000
WAIT_OBSERVATION_SLACK_NS=100_000_000


def need(value, reason):
    if not value:
        raise ValueError(reason)


class SourceCursor:
    def __init__(self, path, identity, max_bytes=16*1024*1024):
        self.path=Path(path);self.identity=identity;self.max_bytes=max_bytes
        self.fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        self.offset=0;self.buffer=b'';self.records=[];self.read_end_by_index=[]
        self.last_read_start_ns=0;self.last_read_end_ns=0
        try:self.verify()
        except BaseException:os.close(self.fd);raise
    def verify(self):
        a=os.fstat(self.fd);b=self.path.lstat()
        need(stat.S_ISREG(a.st_mode) and not stat.S_ISLNK(b.st_mode)
             and a.st_dev==b.st_dev==self.identity['device']
             and a.st_ino==b.st_ino==self.identity['inode'], 'Source_descriptor_or_path_identity_changed')
        need(self.offset<=a.st_size<=self.max_bytes,'Source_truncated_or_read_budget')
        return a.st_size
    def poll(self):
        size=self.verify()
        if size>self.offset:
            self.last_read_start_ns=time.monotonic_ns()
            data=os.pread(self.fd,size-self.offset,self.offset)
            self.last_read_end_ns=time.monotonic_ns()
            need(len(data)==size-self.offset,'Source_short_read')
            self.offset=size;self.buffer+=data
            lines=self.buffer.split(b'\n');self.buffer=lines.pop()
            need(len(self.buffer)<=1024*1024,'Source_line_budget')
            for line in lines:
                need(line and len(line)<=1024*1024,'Source_complete_line_budget')
                self.records.append(json.loads(line))
                self.read_end_by_index.append(self.last_read_end_ns)
            need(len(self.records)<=20000,'Source_record_budget')
        return self.records
    def close(self):os.close(self.fd)


def validate_notice(records, expected):
    startup=[r for r in records if r.get('type')=='startup']
    need(len(startup)==1,'unique_Observer_Source_startup')
    s=startup[0]
    for key,value in [('run_id',expected['run_id']),('boot',expected['boot_id']),
                      ('pid',expected['observer_pid']),('contract_hash',expected['contract_sha256']),('mode','shadow')]:
        need(type(s.get(key)) is type(value) and s.get(key)==value,'Source_startup_binding:'+key)
    terminals=[r for r in records if r.get('type')=='worker_unusable_transition']
    if not terminals:return None
    need(len(terminals)==1,'unique_terminal_notice')
    terminal=terminals[0];t=terminal['check_ns']
    need(type(t) is int and expected['prepare_start_ns']<=t<=time.monotonic_ns(),'terminal_time_domain')
    need(type(terminal['worker_pid']) is int and terminal['worker_pid']==expected['worker_pid']
         and terminal['worker_instance']==expected['worker_instance'],'terminal_exact_Worker')
    need(terminal['candidate_after'] is False and terminal['pending_after'] is False,'terminal_invalidates_uncommitted_work')
    raw=terminal['reason']
    if raw=='legacy_ready_invalidated:worker_unusable:active_watchdog':
        links=[r for r in records if r.get('type')=='legacy_ready_invalidated'
               and r.get('check_ns')==t and r.get('reason')=='worker_unusable:active_watchdog']
        need(len(links)==1 and links[0]['terminal'] is True and links[0]['measurement_eligible'] is False
             and records.index(links[0])<records.index(terminal),'paired_causal_readiness_invalidation')
    else:need(raw=='active_watchdog','unexpected_terminal_cause')
    valid=sorted([r for r in records if r.get('type')=='capability_admission' and r.get('renewed') is True
                  and r['validation_commit_ns']<t],key=lambda r:r['validation_commit_ns'])
    need(valid,'prior_valid_capability')
    active,since=0,0
    for r in valid:
        need(r['valid'] is True and r['identity_valid'] is True,'capability_validity')
        if r['capability']['active_job']!=active:active=r['capability']['active_job'];since=r['validation_commit_ns']
    last=valid[-1]['validation_commit_ns']
    need(active==terminal['active_job'] and active>0 and since>0 and t-since>1_000_000_000
         and last==terminal['capability_last_valid_commit_ns'] and 0<=t-last<=600_000_000,
         'active_watchdog_with_live_receipt_lease')
    return {'terminal':terminal,'raw_reason':raw,'cause':'active_watchdog',
            'active_origin_ns':since,'last_valid_receipt_ns':last}


def supervise(root, *, roles, owned, sup, authenticate, source_fd_matches, contract,
              prepare_start_ns, overall_deadline_ns, spin, bound, create_only_json,
              profile):
    need(profile==PROFILE,'explicit_supervision_profile')
    root=Path(root);started=time.monotonic_ns();deadline=min(started+8_000_000_000,overall_deadline_ns-15_000_000_000)
    om,wm=roles['observer']['manifest'],roles['worker']['manifest']
    source_path=root/'observer/source.jsonl'
    current=authenticate('observer');source_fd_matches(current,source_path)
    need(current['sha256']==roles['observer']['sha256'],'initial_Observer_manifest_changed')
    expected={'run_id':om['run_id'],'boot_id':sup.boot,'observer_pid':om['pid'],
              'contract_sha256':om['contract_sha256'],'worker_pid':wm['pid'],
              'worker_instance':wm['worker_instance'],'prepare_start_ns':prepare_start_ns}
    cursor=SourceCursor(source_path,om['source_fd'])
    try:
        notice=None
        while time.monotonic_ns()<deadline:
            bound();records=cursor.poll();notice=validate_notice(records,expected)
            if notice:break
            spin(.005)
        need(notice is not None,'terminal_notification_deadline')
        parsed_ns=time.monotonic_ns();index=records.index(notice['terminal'])
        visible_read_end_ns=cursor.read_end_by_index[index]
        current=authenticate('observer');source_fd_matches(current,source_path);cursor.verify()
        worker_current=authenticate('worker')
        need(current['sha256']==roles['observer']['sha256'] and worker_current['sha256']==roles['worker']['sha256'],
             'notification_role_manifest_changed')
        authenticated_ns=time.monotonic_ns()
        cue={'schema':'owned-Source-terminal-notice/v1','run_id':om['run_id'],'boot_id':sup.boot,
             'Observer_manifest_sha256':current['sha256'],'Worker_manifest_sha256':worker_current['sha256'],
             'Source_fd_identity':om['source_fd'],'notice':notice,'read_end_ns':visible_read_end_ns,
             'parsed_ns':parsed_ns,'authenticated_ns':authenticated_ns,
             'notification_budget_ns':NOTIFICATION_BUDGET_NS,'actual_Source_flush_time_known':False}
        sup.event('bridge_notice_authenticated',name='worker',**cue)
        # This explicit diagnostic pause forces escalation after a genuine,
        # independently authenticated active watchdog. It is not a C-call hang.
        sup.send(owned['worker'],signal.SIGSTOP)
        stopped_deadline=time.monotonic_ns()+50_000_000
        observed=None
        while time.monotonic_ns()<stopped_deadline:
            observed=proc_identity(owned['worker'].process.pid,hash_exe=False)
            if observed and observed['state']=='T':break
            time.sleep(.001)
        need(observed is not None and observed['state']=='T','diagnostic_SIGSTOP_not_observed')
        need(observed['start_ticks']==owned['worker'].identity['start_ticks'],'paused_Worker_identity')
        stopped_ns=time.monotonic_ns()
        sup.event('diagnostic_Worker_stopped_after_terminal',name='worker',observed_ns=stopped_ns,
                  observed_identity=observed,diagnostic_only=True,native_C_hang_proven=False)
        waits={k:contract[k] for k in ['worker_grace_ns','term_grace_ns','kill_postcheck_ns']}
        stop_called_ns=time.monotonic_ns()
        cleanup=sup.stop(owned['worker'],waits['worker_grace_ns']/1e9,
                         waits['term_grace_ns']/1e9,waits['kill_postcheck_ns']/1e9)
        events=[r for r in sup.memory_tail if r.get('name')=='worker']
        calls=[r for r in events if r['type']=='signal_call_result']
        stages=[r for r in events if r['type']=='wait_result']
        stage_map={r['stage']:r for r in stages}
        wait_checks=all(stage in stage_map and stage_map[stage]['budget_ns']==waits[key]
          and stage_map[stage]['empty'] is expected_empty
          and stage_map[stage]['returned_ns']<=stage_map[stage]['deadline_ns']+WAIT_OBSERVATION_SLACK_NS
          for stage,key,expected_empty in [('worker_grace','worker_grace_ns',False),
            ('term_grace','term_grace_ns',False),('kill_postcheck','kill_postcheck_ns',True)])
        first_int=next((r for r in calls if r['signal']==signal.SIGINT),None)
        passed=bool(first_int and [r['signal'] for r in calls]==[19,2,15,9]
          and all(r['returned'] and not r['process_lookup_error'] for r in calls)
          and cleanup['cleanup_complete'] and cleanup['remaining_members']==[] and cleanup['returncode']==-9
          and not cleanup['qualification_clean'] and not sup.evidence_failed and not sup.unexpected_descendants
          and wait_checks and time.monotonic_ns()<=deadline
          and authenticated_ns-notice['terminal']['check_ns']<=NOTIFICATION_BUDGET_NS
          and first_int['call_start_ns']-authenticated_ns<=AUTH_TO_INT_BUDGET_NS)
        report={'schema':'V2-Source-to-owned-supervisor-bridge/v1','profile':PROFILE,'passed':passed,
          'cue':cue,'diagnostic_stopped_ns':stopped_ns,'stop_called_ns':stop_called_ns,
          'declared_waits_ns':waits,'signal_calls':calls,'wait_results':stages,'cleanup':cleanup,
          'finished_ns':time.monotonic_ns(),'deadline_ns':deadline,
          'notification_delay_ns':authenticated_ns-notice['terminal']['check_ns'],
          'notification_budget_ns':NOTIFICATION_BUDGET_NS,'authenticated_to_INT_budget_ns':AUTH_TO_INT_BUDGET_NS,
          'normal_Worker_Source_complete':False,'diagnostic_SIGSTOP_injected_after_terminal':True,
          'native_C_hang_proven':False,'WCET_or_universal_notification_bound_proven':False,
          'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
        create_only_json(root/'supervision_bridge.json',report)
        need(passed,'supervisor_bridge_case_criteria_not_met')
        return report
    finally:cursor.close()
