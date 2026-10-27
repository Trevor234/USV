"""Minimal predicate-only A counterexamples, derived from 75 passing fixture. No claim about P01."""
import importlib.util,sys,json
from pathlib import Path
sys.dont_write_bytecode=True
base=Path('/home/trevor/USV/.sgh-research/experiments')
p=base/'scheme_A_M4_t2_r0_protocol_20261024_75/implementation/test_r0.py'
spec=importlib.util.spec_from_file_location('r0_helper_a',p);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
p=base/'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/audit_t2.py'
spec=importlib.util.spec_from_file_location('current_audit_a',p);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def run_case(name,mutate=None):
    table=helper.table_t2a();fixture,regulator,witness=helper.t2a_streams()
    if mutate:mutate(table,fixture,regulator,witness)
    root=helper.t2a_run_dir(fixture,regulator,witness)
    out=audit.audit_run(root,table,driver_result=helper.driver_result_ok(table,fixture))
    return {'case':name,'run':str(root),'passed':out['passed'],'checks':out['checks'],'failures':out['failures'], 'accepted_after_resume':sum(r.get('type')=='candidate_registration' and r.get('accepted_registration') and r.get('ready_commit_ns',0)>fixture[1]['executed_ns'] for r in regulator), 'clock_sim_values':[r['sim_ns'] for r in regulator if r['type']=='clock']}

def no_clock_during(table,f,rows,w):
    hold,resume=f[0]['executed_ns'],f[1]['executed_ns']
    rows[:]=[r for r in rows if r.get('type')!='clock' or not hold<=r.get('receive_ns',0)<=resume]

def valid_new_schedule_same_task(table,f,rows,w):
    rows.append({'type':'candidate_registration','accepted_registration':True,'ready_commit_ns':f[1]['executed_ns']+20000000,'job':{'job_id':2,'task_generation':1,'schedule_generation':2}})

def mode_claim_only(table,f,rows,w):
    table['actions'][0]['parameters']['mode']='same_stamp';f[0]['parameters']['mode']='same_stamp'

out={'scope':'audit predicate-only synthetic controls from the actual 75 test helper; no P01 data changed or asserted wrong', 'cases':[run_case('original_75_positive_has_no_resumed_accepted_job'),run_case('silent_hold_has_zero_received_clock_rows',no_clock_during),run_case('new_schedule_same_task_wrongly_called_old_revival',valid_new_schedule_same_task),run_case('same_stamp_label_but_every_observed_sim_value_advances',mode_claim_only)]}
Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/evidence/replay01/protocol/probe_t2a_predicates_result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
