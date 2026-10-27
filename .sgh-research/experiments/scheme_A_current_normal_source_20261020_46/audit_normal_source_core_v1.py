"""Independent reconstruction of current20s source and actual nominal inputs."""
import math


def need(value,why):
    if not value:raise ValueError(why)


def check_window(source,worker,publisher,proof,inputs,result):
    need(proof['passed'] is True and proof['finished_ns']<=proof['deadline_ns'],'live normal-source observation completed in budget')
    need(inputs['measurement_seconds']==20 and inputs['validation_recipe_revision']=='current-normal-source20s-v1'
         and inputs['reference_speed_m_s']==.05 and result['normal20_source_case_completed'],'exact registered normal recipe')
    jobs=[r['job'] for r in source if r.get('type')=='job'];need(jobs,'actual source jobs')
    need(not any(r.get('type') in ['worker_unusable_transition','diagnostic_v1_armed_after_ack','diagnostic_v3_wait_started','diagnostic_c38_gate_paused'] for r in source),'no normal-window fault stimulus')
    moving=[j for j in jobs if math.hypot(j['frozen_state'][3],j['frozen_state'][4])>1e-9
            and all(j['anchor_known']) and any(abs(n)>1e-9 for n in j['anchor_n'])]
    need(moving,'actual moving and nonzero input source exists');first=moving[0]
    need(proof['first_job_id']==first['job_id'] and proof['first_freeze_ns']==first['freeze_ns'],'first dynamic origin cannot be reselected')
    selected=[j for j in jobs if first['freeze_ns']<=j['freeze_ns']<=proof['last_freeze_ns']]
    need(selected and selected[-1]['job_id']==proof['last_job_id'] and len(selected)==proof['jobs_in_window'],'exact contiguous Job population')
    span=selected[-1]['freeze_ns']-selected[0]['freeze_ns'];sim_span=selected[-1]['odom_stamp_ns']-selected[0]['odom_stamp_ns']
    need(span>=20_000_000_000 and sim_span>=20_000_000_000 and span==proof['source_span_ns'] and sim_span==proof['odom_sim_span_ns'],'two actual continuous source clocks >=20s')
    gaps=[];speeds=[];mixed=0
    for index,j in enumerate(selected):
        need(len(j['frozen_state'])==6 and all(type(v) in (int,float) and math.isfinite(v) for v in j['frozen_state']),'finite whole state')
        speed=(j['frozen_state'][3]**2+j['frozen_state'][4]**2)**.5;speeds.append(speed)
        need(1e-9<speed<=1.2 and any(abs(n)>1e-9 for n in j['anchor_n']) and all(j['anchor_known']),'no static/zero tail in dynamic window')
        need(j['anchor_source']=='legacy_publisher' and j['contract_hash']==inputs['contract_sha256'] and j['worker_instance']==first['worker_instance'],'actual same origin/model/Worker')
        need(j['target_ns']==j['tick_origin_ns']+200_000_000 and j['deadline_ns']==j['tick_origin_ns']+150_000_000 and j['freeze_ns']<=j['deadline_ns'],'original per-job absolute target/deadline')
        for key,limit in [('odom_receive_ns',100_000_000),('frozen_clock_receive_ns',100_000_000)]:
            need(0<=j['freeze_ns']-j[key]<=limit,'actual frozen receipt ages')
        clock=j['frozen_clock_sim_ns']+j['freeze_ns']-j['frozen_clock_receive_ns']
        need(-20_000_000<=clock-j['odom_stamp_ns']<=100_000_000,'separate actual source lag/future')
        mixed+=bool(j['r_from_imu'])
        if index:
            a=selected[index-1];pair=[j['freeze_ns']-a['freeze_ns'],j['odom_stamp_ns']-a['odom_stamp_ns']]
            need(all(0<g<=250_000_000 for g in pair),'whole source gap without splicing');gaps.extend(pair)
    decisions=[r for r in source if r.get('type')=='decision'];window_decisions=[d for d in decisions if proof['first_freeze_ns']<=d['activation_commit_ns']<=proof['finished_ns']]
    generated=[r for r in worker if r.get('type')=='candidate'];accepted=[d for d in window_decisions if d['accepted']]
    need(len(accepted)>=2,'at least prior registered healthy chain continues; no all-rejected normal evidence')
    emitted=[r for r in publisher if r.get('type')=='controlled_Applied_emitted']
    actual_commands=[r for r in emitted if proof['first_freeze_ns']<=r['applied_publish_end_ns']<=proof['finished_ns']]
    need(actual_commands and any(any(abs(n)>1e-9 for n in r['final_n']) for r in actual_commands),'actual nonzero commands are Source facts')
    return dict(passed=True,source_span_ns=span,odom_sim_span_ns=sim_span,jobs=len(selected),
        first_job_id=selected[0]['job_id'],last_job_id=selected[-1]['job_id'],max_source_or_freeze_gap_ns=max(gaps),
        min_planar_speed_m_s=min(speeds),max_planar_speed_m_s=max(speeds),mixed_jobs=mixed,
        window_Decisions=len(window_decisions),accepted_in_window=len(accepted),actual_command_pairs_in_window=len(actual_commands),
        whole_run_Jobs=len(jobs),whole_run_Candidates=len(generated),whole_run_Decisions=len(decisions),
        whole_run_rejection_reasons={r:sum(d['reason']==r for d in decisions) for r in sorted({d['reason'] for d in decisions})},
        separate_prepare_and_tail_not_removed=True,scope='selected current owned nominal straight0.05 source window; not plant/general turn/mixed',
        full_D1_stage_qualified=False,B5_formal_freeze_qualified=False,stage_qualified=False,research_conclusion=False)
