"""Read-only finite interleave checks, independent of the runtime wait class."""
import hashlib

POLICY='await_actual_odom_once_before_commit_v1'
def need(v,why):
    if not v:raise ValueError(why)

def check(source,fixture_manifest,contract):
    decisions=[r for r in source if r.get('type')=='decision']
    waits=[]
    for d in decisions:
        trace=d['d0_observation']['activation_alignment'];attempts=trace['attempts']
        need(trace['capacity']==32 and trace['maximum_attempts']==2 and 1<=len(attempts)<=2,'finite history and attempt bound')
        need(trace['decision_commit_ns']==d['activation_commit_ns']<=trace['observer_publish_return_ns']<=d['end_ns']<=trace['materialized_start_ns']<=trace['materialized_end_ns'],'deferred trace order')
        for a in attempts:
            need(a['frame_count']<=32 and a['frames_scanned']<=32,'history capacity')
            if 'diagnostic_interleave' in a:waits.append((d,trace,a))
    need(len(waits)==1,'exactly one actual diagnostic interleave')
    d,trace,a=waits[0];w=a['diagnostic_interleave'];old=a['raw_snapshot'];guard=a['guard_snapshot']
    need(w['policy']==POLICY and w['wait_budget_ns']==25000000 and w['deadline_ns']==w['begin_ns']+25000000,'fixed explicit wait budget')
    need(w['changed'] is True and w['cancelled'] is False and w['business_mutex_held_during_wait'] is False and w['original_jitter_budget_unchanged'] is True,'actual input completed while wait allowed callback')
    need(a['sample_ns']<=a['copy_capture_ns']<=w['begin_ns']<=w['end_ns']<=a['commit_check_ns']<=d['activation_commit_ns'],'snapshot wait guard commit order')
    need(w['end_ns']<=w['deadline_ns']+5000000,'finite observed diagnostic wait with declared 5ms scheduling observation slack')
    need(w['captured_odom_sequence']==old['odom_sequence']<w['observed_after']<=guard['odom_sequence'],'actual odom sequence changed')
    need(a['attempt']==1 and a['input_change_gate_ran'] is True and a['input_change_gate_unchanged'] is False
         and a['input_gate_reads']['input_version_equal'] is True and a['input_gate_reads']['input_odom_equal'] is False,'original first guard rejects stale snapshot')
    need(old['version']==guard['version'] and all(old['ref_selection'].get(k)==guard['ref_selection'].get(k) for k in ['path_fingerprint','profile_fingerprint']) and not any(r.get('type')=='activation_sensor_history_reset' and a['sample_ns']<r['reset_ns']<=a['commit_check_ns'] for r in source),'same version and history for source-only interleave')
    topic='/wamv/sensors/position/ground_truth_odometry'
    gids=[e['gid'] for e in fixture_manifest['endpoints'] if e['kind']=='publisher' and e['topic']==topic]
    need(len(gids)==1,'one exact owned odom Writer')
    callbacks=[r for r in source if r.get('type')=='odom_admission' and r['valid']
        and old['odom_sequence']<r['accepted_sequence']<=w['observed_after']
        and old['input_commit_ordinal']<r['input_commit_ordinal']<=guard['input_commit_ordinal']]
    need(callbacks,'actual admitted callback after snapshot ordinal')
    callback=max(callbacks,key=lambda r:r['input_commit_ordinal']);rr=callback['raw_input'];blob=bytes.fromhex(rr['cdr_hex'])
    need(rr['topic']==topic and rr['publisher_gid']==gids[0] and rr['cdr_bytes']==len(blob)
        and hashlib.sha256(blob).hexdigest()==rr['cdr_sha256'],'actual callback CDR and owned GID')
    need(a['sample_ns']<=callback['diagnostic_v3_commit_ns']<=w['end_ns'],'actual callback mutation completed between snapshot and guard')
    need(any(v['accepted'] and v['activation_commit_ns']<a['sample_ns'] for v in decisions),'one healthy accepted activation before arming')
    attempts=trace['attempts']
    if a['retry']:
        need(len(attempts)==2 and a['reason']=='activation_input_changed_during_validation'
            and a['commit_check_ns']-d['planned_ns']<=contract['tick_jitter_ns'],'retry only within original jitter budget')
        fresh=attempts[1]
        need(fresh['sample_ns']>=a['commit_check_ns'] and fresh['raw_snapshot']['odom_sequence']>=w['observed_after']
            and fresh['raw_snapshot']['input_commit_ordinal']>old['input_commit_ordinal'],'second attempt copied new actual source')
        need(not fresh['retry'] and 'diagnostic_interleave' not in fresh,'one revalidation maximum and wait one-shot')
        if d['accepted']:
            need(fresh['input_change_gate_unchanged'] is True and fresh['reason']=='' and d['activation_commit_ns']-d['planned_ns']<=contract['tick_jitter_ns'],'accepted only after fresh final guard within unchanged budget')
    else:
        need(len(attempts)==1 and not d['accepted'] and a['reason']==d['reason']=='activation_input_changed_during_validation','exhausted original budget cannot accept old source')
        need(a['commit_check_ns']-d['planned_ns']>contract['tick_jitter_ns'],'selected healthy source-only no-retry is original time refusal')
    need(attempts[-1]['reason']==d['reason'] and attempts[-1]['final_commit_ns']==d['activation_commit_ns'],'single final decision')
    return dict(passed=True,decision_sequence=d['sequence'],job_id=d['job_id'],wait_ns=w['end_ns']-w['begin_ns'],
        callback_sequence=callback['accepted_sequence'],raw_odom_sequence=old['odom_sequence'],
        callback_commit_ns=callback['diagnostic_v3_commit_ns'],callback_raw_cdr_sha256=rr['cdr_sha256'],
        attempts=len(attempts),retry=a['retry'],accepted_after_final_guard=d['accepted'],reason=d['reason'],
        start_jitter_ns=d['start_ns']-d['planned_ns'],activation_jitter_ns=d['activation_commit_ns']-d['planned_ns'],
        actual_source_input_interleave=True,actual_clock_epoch_interleave=False,stage_qualified=False)
