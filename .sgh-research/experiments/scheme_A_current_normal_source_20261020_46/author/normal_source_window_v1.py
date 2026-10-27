"""Current-source observation only; does not change a role or authorize output."""
import math
import time
from pathlib import Path
from supervision_bridge_v1 import SourceCursor

MIN_SPAN_NS=20_000_000_000
MAX_OBSERVATION_NS=26_000_000_000
MAX_GAP_NS=250_000_000
SPEED_LIMIT=1.2
PRESENCE_EPS=1e-9


def need(value,why):
    if not value:raise ValueError(why)


def valid_job(row):
    j=row['job'];state=j['frozen_state']
    need(len(state)==6 and all(type(v) in (int,float) and math.isfinite(v) for v in state),'finite source state')
    need(type(j['job_id']) is int and j['job_id']>0,'source job ID')
    need(all(type(j[k]) is int for k in ['freeze_ns','odom_stamp_ns','frozen_clock_sim_ns','frozen_clock_receive_ns','odom_receive_ns']),'source time integer types')
    need(all(j['anchor_known']) and j['anchor_source']=='legacy_publisher','actual known legacy anchor')
    need(len(j['anchor_n'])==2 and all(type(n) in (int,float) and math.isfinite(n) and -25<=n<=25 for n in j['anchor_n']),'finite actual anchor')
    speed=math.hypot(state[3],state[4]);need(speed<=SPEED_LIMIT,'planar speed exceeds unchanged1.2 domain')
    return speed


def select_window(source):
    """First dynamic Job fixes the origin; no later search for a nicer segment."""
    jobs=[r for r in source if r.get('type')=='job']
    eligible=[]
    for row in jobs:
        speed=valid_job(row);j=row['job']
        if not eligible:
            if speed>PRESENCE_EPS and any(abs(n)>PRESENCE_EPS for n in j['anchor_n']):eligible.append(row)
        else:eligible.append(row)
    if not eligible:return None
    first=eligible[0]['job'];last=eligible[-1]['job'];previous=None
    dynamic_states=nonzero_anchors=mixed=0;max_speed=0.;max_gap=0
    for row in eligible:
        j=row['job'];speed=valid_job(row);max_speed=max(max_speed,speed)
        dynamic_states+=speed>PRESENCE_EPS;nonzero_anchors+=any(abs(n)>PRESENCE_EPS for n in j['anchor_n']);mixed+=bool(j['r_from_imu'])
        need(j['run_id']==first['run_id'] and j['worker_instance']==first['worker_instance'] and j['contract_hash']==first['contract_hash'],'single-run/source identity')
        if previous:
            gap=j['odom_stamp_ns']-previous['odom_stamp_ns'];freeze_gap=j['freeze_ns']-previous['freeze_ns']
            need(0<gap<=MAX_GAP_NS and 0<freeze_gap<=MAX_GAP_NS,'contiguous source or freeze gap')
            max_gap=max(max_gap,gap,freeze_gap)
        previous=j
    span=last['freeze_ns']-first['freeze_ns'];sim_span=last['odom_stamp_ns']-first['odom_stamp_ns']
    complete=span>=MIN_SPAN_NS and sim_span>=MIN_SPAN_NS
    # A zero-action/static tail is not evidence for this dynamic source window.
    # This is scope selection, not a new tracking-performance acceptance gate.
    if complete:
        need(dynamic_states==len(eligible) and nonzero_anchors==len(eligible),'dynamic source window cannot be filled with static/zero-command tail')
    return {'schema':'current-normal-source-contiguous-window-v1','passed':complete,
        'first_job_id':first['job_id'],'last_job_id':last['job_id'],'first_freeze_ns':first['freeze_ns'],
        'last_freeze_ns':last['freeze_ns'],'source_span_ns':span,'odom_sim_span_ns':sim_span,
        'jobs_in_window':len(eligible),'dynamic_state_jobs':dynamic_states,'nonzero_actual_anchor_jobs':nonzero_anchors,
        'max_planar_speed_m_s':max_speed,'max_source_or_freeze_gap_ns':max_gap,'mixed_jobs':mixed,
        'selected_origin':'first actual moving Job with actual nonzero known legacy anchor',
        'all_prepare_and_tail_retained':True,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}


def observe(root,*,roles,spin,bound,create_only_json,overall_deadline_ns):
    root=Path(root);started=time.monotonic_ns();deadline=min(started+MAX_OBSERVATION_NS,overall_deadline_ns-15_000_000_000)
    cursor=SourceCursor(root/'observer/source.jsonl',roles['observer']['manifest']['source_fd'])
    try:
        while time.monotonic_ns()<deadline:
            bound();source=cursor.poll()
            need(not any(r.get('type') in ['worker_unusable_transition','legacy_ready_failed','legacy_ready_invalidated',
              'diagnostic_v1_armed_after_ack','diagnostic_v3_wait_started','diagnostic_c38_gate_paused'] for r in source),
              'unexpected fault/invalidation in current normal source observation')
            result=select_window(source)
            if result and result['passed']:
                result.update(started_ns=started,finished_ns=time.monotonic_ns(),deadline_ns=deadline,
                    observation_policy='one current continuous nominal source window; no ELF/parameter changes')
                create_only_json(root/'normal_source_observation.json',result);return result
            spin(.01)
        raise RuntimeError('one continuous current dynamic source20s deadline')
    finally:cursor.close()
