#!/usr/bin/env python3
"""Independent scope/boundary cases for the new observation selector, no ROS."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(D/'author'));sys.path.insert(0,str(D/'author/runtime'))
from normal_source_window_v1 import select_window


def dataset():
    return [{'type':'job','job':{'job_id':i+1,'frozen_state':[.01*i,0.,0.,.05,0.,0.],
      'anchor_known':[True,True],'anchor_source':'legacy_publisher','anchor_n':[.2,.2],
      'freeze_ns':1_000_000_000+i*200_000_000,'odom_stamp_ns':100_000_000_000+i*200_000_000,
      'frozen_clock_sim_ns':100_000_000_000+i*200_000_000,'frozen_clock_receive_ns':999_000_000+i*200_000_000,
      'odom_receive_ns':999_000_000+i*200_000_000,'run_id':'seeded_monitor_case','worker_instance':'fixture_worker',
      'contract_hash':'a'*64,'r_from_imu':False}} for i in range(101)]


def main():
    outcomes=[]
    def case(name,mutate,expected):
        rows=dataset();mutate(rows)
        try:result=select_window(rows);status='complete' if result and result['passed'] else 'incomplete'
        except (ValueError,KeyError,TypeError):status='reject'
        outcomes.append({'name':name,'expected':expected,'actual':status,'passed':status==expected})
    case('exact20s_boundary',lambda r:None,'complete')
    case('under20s',lambda r:r.pop(),'incomplete')
    case('missingMiddle_not_contiguous',lambda r:r.pop(20),'reject')
    case('v_component_not_only_u',lambda r:r[8]['job']['frozen_state'].__setitem__(4,1.21),'reject')
    case('speed_above1_2',lambda r:r[1]['job']['frozen_state'].__setitem__(3,1.200001),'reject')
    case('source_order_backward',lambda r:r[8]['job'].__setitem__('odom_stamp_ns',r[7]['job']['odom_stamp_ns']-1),'reject')
    case('freeze_gap_above250ms',lambda r:r[8]['job'].__setitem__('freeze_ns',r[7]['job']['freeze_ns']+250000001),'reject')
    case('unknown_anchor',lambda r:r[8]['job'].__setitem__('anchor_known',[False,False]),'reject')
    case('virtual_anchor_not_actual',lambda r:r[8]['job'].__setitem__('anchor_source','virtual_shadow'),'reject')
    case('different_run_no_splicing',lambda r:r[60]['job'].__setitem__('run_id','other_run'),'reject')
    case('different_Worker_no_splicing',lambda r:r[60]['job'].__setitem__('worker_instance','other_worker'),'reject')
    case('nonfinite_source',lambda r:r[8]['job']['frozen_state'].__setitem__(3,float('nan')),'reject')
    case('out_of_range_command',lambda r:r[8]['job'].__setitem__('anchor_n',[25.001,0.]),'reject')
    case('source_job_boolean',lambda r:r[8]['job'].__setitem__('job_id',True),'reject')
    def static_tail(rows):
        for row in rows[80:]:row['job']['anchor_n']=[0.,0.];row['job']['frozen_state'][3]=0.
    case('cannot_fill20_with_zero_tail',static_tail,'reject')
    def zero_prefix(rows):
        rows[0]['job']['anchor_n']=[0.,0.];rows[0]['job']['frozen_state'][3]=0.
    case('first_dynamic_origin_fixed_not_first_row',zero_prefix,'incomplete')
    case('exactSpeed1_2_allowed',lambda r:[v['job']['frozen_state'].__setitem__(3,1.2) for v in r],'complete')
    result={'schema':'current-normal-source-selector-cases-v1','passed':all(v['passed'] for v in outcomes),'case_count':len(outcomes),
            'cases':outcomes,'seeded_component_only':True,'stage_qualified':False,'execute_qualified':False}
    with (D/'verification/normal_source_window_cases_v1.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'passed':result['passed'],'cases':len(outcomes),'failed':[r['name'] for r in outcomes if not r['passed']]}))
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
