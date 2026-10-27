#!/usr/bin/env python3
"""Additional checks for actual mixed snapshots and full API timing population."""
import copy
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent.parent
R=D/'author_r2/runs/normal_source20s_03'


def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(p):return json.loads(p.read_bytes())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]


def mixed_checks(jobs,c):
    selected=[]
    for j in jobs:
        if not j['r_from_imu']:continue
        clock=j['frozen_clock_sim_ns']+j['freeze_ns']-j['frozen_clock_receive_ns']
        assert 0<=j['freeze_ns']-j['imu_receive_ns']<=c['imu_age_ns'],'mixed receipt age'
        assert -c['source_future_slack_ns']<=clock-j['imu_stamp_ns']<=c['imu_sim_lag_ns'],'mixed source lag/future'
        assert abs(j['imu_stamp_ns']-j['odom_stamp_ns'])<=c['mixed_skew_ns'],'mixed stamp skew'
        selected.append({'job_id':j['job_id'],'imu_receipt_age_ns':j['freeze_ns']-j['imu_receive_ns'],
            'imu_estimated_source_lag_ns':clock-j['imu_stamp_ns'],'mixed_skew_ns':abs(j['imu_stamp_ns']-j['odom_stamp_ns'])})
    return selected


def main():
    paths=[R/'observer/source.jsonl',R/'publisher/controlled_source.jsonl',R/'normal_source_observation.json',
           D/'author_r2/pair_wakeup_contract_v1.json',D/'postrun/current_normal_source20s_audit_v1.json',Path(__file__).resolve()]
    before={str(p):pin(p) for p in paths};source=rows(paths[0]);publisher=rows(paths[1]);proof=read(paths[2]);c=read(paths[3])
    jobs=[r['job'] for r in source if r.get('type')=='job'];mixed=mixed_checks(jobs,c)
    negative=[]
    for label,key,value in [('receipt','imu_receive_ns',0),('future','imu_stamp_ns',10**15),('skew','odom_stamp_ns',1)]:
        changed=copy.deepcopy(jobs);target=next(j for j in changed if j['r_from_imu']);target[key]=value
        try:mixed_checks(changed,c);rejected=False
        except AssertionError:rejected=True
        negative.append({'case':label,'rejected':rejected})
    assert all(r['rejected'] for r in negative)
    applied=[r for r in publisher if r.get('type')=='controlled_Applied_emitted']
    timings={}
    for side in ['left','right']:
        starts=[r[side+'_start_ns'] for r in applied];gaps=[b-a for a,b in zip(starts,starts[1:])]
        assert gaps and all(g>0 for g in gaps)
        business=[r for r in applied if r['control_source'] not in ['controlled_initial_zero','shutdown_zero']]
        bgaps=[b[side+'_start_ns']-a[side+'_start_ns'] for a,b in zip(business,business[1:])]
        timings[side]={'full_API_pair_count':len(applied),'full_stream_gap_max_ns':max(gaps),'initial_to_first_business_gap_ns':gaps[0],
            'full_stream_gap240ms_passed':max(gaps)<=c['publish_gap_ns'],
            'business_population_gap_max_ns':max(bgaps) if bgaps else None,
            'decomposition_not_exclusion':'full startup/business/shutdown population retained; business subset is separately labeled'}
    decisions=[r for r in source if r.get('type')=='decision']
    jitter=[r['start_ns']-r['planned_ns'] for r in decisions]
    summary={'schema':'current-normal-source-actual-scope-supplement-v1','passed':True,'mixed_frozen_jobs':mixed,
      'mixed_cases_actual_count':len(mixed),'general_mixed_or_turning_qualified':False,'negative_altered_mixed_evidence':negative,
      'API_gap_population':timings,'tick_observed_start_lateness_min_ns':min(jitter),'tick_observed_start_lateness_max_ns':max(jitter),
      'hard_clock_or_WCET_proven':False,'source_window_span_ns':proof['source_span_ns'],'input_sha256_before':before,
      'input_sha256_after':{str(p):pin(p) for p in paths},'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    assert summary['input_sha256_before']==summary['input_sha256_after']
    with (D/'postrun/observed_domain_timing_supplement_v1.json').open('x') as f:json.dump(summary,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'passed':True,'actual_mixed_jobs':len(mixed),'full_API_gap_max_ns':{s:timings[s]['full_stream_gap_max_ns'] for s in timings},'max_tick_lateness_ns':max(jitter)}))


if __name__=='__main__':main()
