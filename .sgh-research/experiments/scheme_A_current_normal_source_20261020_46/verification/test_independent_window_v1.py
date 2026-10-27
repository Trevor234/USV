#!/usr/bin/env python3
"""Independent offline checker positives and semantic alterations, no ROS."""
from pathlib import Path
import sys,copy,json
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D));sys.path.insert(0,str(D/'verification'))
from audit_normal_source_core_v1 import check_window
from test_normal_source_window_v1 import dataset


def fixture():
    source=dataset()
    for r in source:
        j=r['job'];j['tick_origin_ns']=j['freeze_ns']-50_000_000;j['target_ns']=j['tick_origin_ns']+200_000_000;j['deadline_ns']=j['tick_origin_ns']+150_000_000
    first,last=source[0]['job'],source[-1]['job']
    for n in [4,70]:source.append({'type':'decision','activation_commit_ns':1_000_000_000+n*200_000_000,'accepted':True,'reason':'accepted'})
    proof={'passed':True,'finished_ns':last['freeze_ns']+1_000_000,'deadline_ns':last['freeze_ns']+5_000_000,
        'first_job_id':1,'last_job_id':101,'first_freeze_ns':first['freeze_ns'],'last_freeze_ns':last['freeze_ns'],
        'jobs_in_window':101,'source_span_ns':20_000_000_000,'odom_sim_span_ns':20_000_000_000}
    return {'source':source,'worker':[],'publisher':[{'type':'controlled_Applied_emitted','applied_publish_end_ns':2_000_000_000,'final_n':[.2,.2]}],
        'proof':proof,'inputs':{'measurement_seconds':20,'validation_recipe_revision':'current-normal-source20s-v1','reference_speed_m_s':.05,'contract_sha256':'a'*64},
        'result':{'normal20_source_case_completed':True}}


def main():
    rows=[]
    def run(name,mutate,expected):
        f=fixture();mutate(f)
        try:check_window(**f);accepted=True
        except (ValueError,KeyError,TypeError):accepted=False
        rows.append({'name':name,'expected_accept':expected,'accepted':accepted,'passed':accepted==expected})
    run('independent20s_positive',lambda f:None,True)
    run('no_short_segment_promote',lambda f:f['proof'].__setitem__('source_span_ns',19_900_000_000),False)
    run('origin_reselection_denied',lambda f:f['proof'].__setitem__('first_job_id',2),False)
    run('planar_v_not_only_u',lambda f:f['source'][10]['job']['frozen_state'].__setitem__(4,1.3),False)
    run('source_gap_cannot_hide',lambda f:f['source'].pop(20),False)
    run('wrong_absolute_deadline',lambda f:f['source'][30]['job'].__setitem__('deadline_ns',f['source'][30]['job']['deadline_ns']+1),False)
    run('receipt_age_exceeded',lambda f:f['source'][10]['job'].__setitem__('odom_receive_ns',1),False)
    run('wrong_Worker',lambda f:f['source'][30]['job'].__setitem__('worker_instance','foreign'),False)
    run('no_actual_nonzero_commands',lambda f:f['publisher'][0].__setitem__('final_n',[0.,0.]),False)
    run('fault_transition_not_normal',lambda f:f['source'].append({'type':'worker_unusable_transition'}),False)
    run('no_performance_gate_in_recipe',lambda f:f['inputs'].__setitem__('reference_speed_m_s',.6),False)
    result={'schema':'independent-normal20s-checker-cases-v1','passed':all(r['passed'] for r in rows),'case_count':len(rows),'cases':rows,
            'seeded_component_only':True,'stage_qualified':False}
    with (D/'verification/independent_window_cases_v1.json').open('x') as s:json.dump(result,s,indent=2);s.write('\n')
    print(json.dumps({'passed':result['passed'],'cases':len(rows),'failed':[r['name'] for r in rows if not r['passed']]}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
