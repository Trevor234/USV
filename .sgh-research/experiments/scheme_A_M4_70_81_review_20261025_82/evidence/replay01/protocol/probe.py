import importlib.util,json,sys,copy
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/home/trevor/USV/.sgh-research/experiments')
test_path=root/'scheme_A_M4_t2_r0_protocol_20261024_75/implementation/test_r0.py'
spec=importlib.util.spec_from_file_location('r0_tests',test_path); helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
latest=root/'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3/audit_t2.py'
spec=importlib.util.spec_from_file_location('latest_audit',latest);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def run_case(name, mutate=None):
    driver_rows,regs=helper.AuditT2CCounterexamples().streams(guard_ns=3000)
    table=helper.table_t2c()
    record=helper.command_record('a1',driver_rows[0]['command'],driver_rows[0]['command_sha256'])
    result={'closed_roles':[{'role':r,'returncode':0,'group_empty':True} for r in ('regulator','fixture','worker','recorder')], 't2_command_records':[record]}
    witness={'observation_complete':True}
    if mutate: mutate(driver_rows,regs,result,witness)
    path=helper.write_run({'fixture/nominal_steps.jsonl':[], 'driver_events.jsonl':driver_rows,
       'regulator/source.jsonl':regs,'regulator/witness.json':[witness]})
    outcome=audit.audit_run(path,table,driver_result=result)
    return {'case':name,'passed':outcome['passed'],'failures':outcome['failures'],'run':str(path),'checks':outcome['checks']}

def late_accept(d,r,o,w):
    r.append({'type':'decision','sequence':4,'accepted':True,'job_id':2,'ready_commit_ns':1000,'activation_commit_ns':4000,'publish_success':[False,False]})
def bad_group(d,r,o,w):o['closed_roles'][0]['group_empty']=False
def bad_trigger(d,r,o,w):d[0]['trigger']={'phase':'job_received','job':{'job_id':999},'observed_ns':1000,'source_role':'worker'}
def bad_sha(d,r,o,w):
    d[0]['command_sha256']='not-a-sha';o['t2_command_records'][0]['command_sha256']='not-a-sha'
def valid_same_tick_stop(d,r,o,w):
    r[2]['reason']='shutdown';r[2]['end_ns']=3500
    r[3]['end_ns']=3600
    r.append({'type':'witness_phase','phase':'StoppingObserved','observed_ns':2500})

out=[run_case('baseline_synthetic_no_stored_artifacts'),run_case('accepted_after_request_using_actual_activation_time',late_accept),run_case('regulator_group_not_empty',bad_group),run_case('receipt_trigger_wrong_job_phase_role',bad_trigger),run_case('command_sha_not_recomputed_from_bytes',bad_sha),run_case('actual_stop_before_guard_but_same_tick_end_after_guard',valid_same_tick_stop)]
Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_70_81_review_20261025_82/evidence/replay01/protocol/probe_result.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
