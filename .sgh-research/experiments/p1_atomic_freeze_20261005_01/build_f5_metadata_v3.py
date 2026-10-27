"""Summarize actual reports and hashes only; private snapshots and bags stay local."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import importlib.util
from collections import Counter

ROOT=Path('/home/trevor/USV')
EXP=ROOT/'.sgh-research/experiments/p1_atomic_freeze_20261005_01'
BASE='F5_20261005_atomic_freeze_01'
RUN='p1_f5_atomic_baseline_20261005_02'
OLD=ROOT/'.sgh-research/experiments/p0_config_reference_20261004_01'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def items(base,name):
    doc=read(base/name)
    return doc if isinstance(doc,list) else doc['files']

def main():
    assert sha(OLD/'metadata_summary_v2.json')=='ddb60bf3164fe56a4fe16ef10dc57bc3b26e4b61179fe638a0e27e434f3fb758'
    previous=read(OLD/'metadata_summary_v2.json')
    result={'schema':'p1-f5-atomic-freeze-evidence/1','date':'2026-10-05','experiment':str(EXP),
        'preflight':read(EXP/'preflight.json'),'build':read(EXP/'build_result.json'),
        'test':read(EXP/'test_result.json'),'cpp_tests':read(EXP/'cpp_gtest_summary.json'),
        'colcon_test_result':(EXP/'colcon_test_result.log').read_text(),
        'source_capture_evidence':read(EXP/'solver_test_evidence.json'),
        'atomic_freeze_evidence':read(EXP/'atomic_freeze_test_evidence.json'),
        'stage_flags':{'dynamic_B_atomic_eligibility_and_input_freeze_verified':True,
            'independent_solver_worker_implemented':False,'fixed_execution_tick_implemented':False,
            'task_clear_cancels_inflight_solve':False,'plant_acceptance_observed':False,
            'force_measured':False,'execution_atomicity_proven':False,
            'exact_execution_timing_available':False,'gp_labels_ready':False,
            'P0_complete':False,'P1_complete':False}}
    assert result['build']['returncode']==0 and result['test']['returncode']==0
    assert result['cpp_tests']['unique_count']==67 and result['cpp_tests']['all_passed']
    for ev in [result['source_capture_evidence'],result['atomic_freeze_evidence']]:
        assert ev['baseline_id']==BASE and ev['all_required_passed'] and ev['exit_code']==0
        assert sha(ev['test_binary_path'])==ev['compiled_test_binary_sha256']
        assert sha(ev['gtest_report_path'])==ev['gtest_report_sha256']
    result['baselines']={}
    old_name='F4_20261005_config_reference_01'
    for name in list(previous['baselines'])+[BASE]:
        b=ROOT/'.sgh-research/baselines'/name;m=read(b/'baseline_manifest.json');errors=[];live_errors=[]
        for file,folder in [('source_hashes.json','source_snapshot'),('installed_hashes.json','installed_snapshot'),('model_assets.json','model_snapshot')]:
            for a in items(b,file):
                if a.get('sha256'):
                    if sha(b/folder/a['path'])!=a['sha256']:errors.append(a['path'])
                    if name==BASE and sha(ROOT/a['path'])!=a['sha256']:live_errors.append(a['path'])
        assert not errors and not live_errors
        result['baselines'][name]={k:m[k] for k in ['baseline_id','source_count','installed_count','model_count','runtime_effective_verified','integrity']}
        result['baselines'][name].update(manifest_sha256=sha(b/'baseline_manifest.json'),snapshot_hash_errors=errors,current_f5_live_hash_errors=live_errors)
    result['f4_to_f5_asset_differences']={}
    old_base=ROOT/'.sgh-research/baselines'/old_name;new_base=ROOT/'.sgh-research/baselines'/BASE
    for name in ['source_hashes.json','installed_hashes.json','model_assets.json']:
        a={x['path']:x.get('sha256') for x in items(old_base,name)}
        b={x['path']:x.get('sha256') for x in items(new_base,name)}
        result['f4_to_f5_asset_differences'][name]=[{'path':p,'F4':a.get(p),'F5':b.get(p)} for p in sorted(set(a)|set(b)) if a.get(p)!=b.get(p)]
    expected={'usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp','usv_mpc_ws/src/usv_mpc_cpp/test/test_deadline_control.cpp','usv_mpc_ws/src/usv_mpc_cpp/test/test_research_contract.cpp'}
    assert {a['path'] for a in result['f4_to_f5_asset_differences']['source_hashes.json']}==expected
    assert not result['f4_to_f5_asset_differences']['model_assets.json']
    result['protected_historical_files']=[]
    for a in previous['protected_historical_files']:
        h=sha(a['path']);assert h==a['sha256'];result['protected_historical_files'].append({'path':a['path'],'sha256':h,'unchanged':True})
    failed=ROOT/'.sgh-research/experiments/p1_f5_atomic_baseline_20261005_01'
    failed_bag=ROOT/'data/sim_bags/p1_f5_atomic_baseline_20261005_01'
    result['failed_attempts']=[{'run_id':failed.name,'failure':read(failed/'run_failure.json'),
        'arm_log':(failed/'logs/arm.log').read_text(),'shutdown_failure':read(failed/'shutdown_gate_failure.json'),
        'bag_hash':{str(p.relative_to(failed_bag)):sha(p) for p in failed_bag.rglob('*') if p.is_file()},
        'launch_log_sha256':sha(failed/'logs/launch.log'),'acceptance_passed':False,
        'runner_v2_change':'arm CLI directly discovers ROS node using --no-daemon --spin-time 3 --timeout 10; production and matching thresholds unchanged'}]
    result['protected_f4_runs']=[]
    for item in previous['pilots']+previous['failed_attempts']:
        bag=ROOT/'data/sim_bags'/item['run_id'];actual={str(p.relative_to(bag)):sha(p) for p in bag.rglob('*') if p.is_file()}
        assert actual==item['publisher_contract']['bag_hash_after']
        result['protected_f4_runs'].append({'run_id':item['run_id'],'bag_hash':actual,'unchanged':True})
    e=ROOT/'.sgh-research/experiments'/RUN;context=read(e/'run_context.json');pub=read(e/'reports_initial/contract_report.json');ref=read(e/'reference_reports/reference_prediction_report.json')
    assert ref['passed'] and ref['combined_recording_contract_verified'] and ref['frozen_solver_test_evidence_verified'] and ref['actual_solve_input_verified']
    assert read(e/'pilot_result.json')['all_required_acceptance_flags'] and context['atomic_freeze_contract']['compiled_test_evidence_verified']
    pilot_result=read(e/'pilot_result.json');assert pilot_result['reason'] is None and pilot_result['check_exit_code']==0 and pilot_result['reference_check_exit_code']==0
    exclude={'research_baseline_id','research_run_id','research_output_dir','research_config_hash'}
    old_params={k:v for k,v in previous['pilots'][0]['context']['runtime_effective_parameters'].items() if k not in exclude}
    new_params={k:v for k,v in context['runtime_effective_parameters'].items() if k not in exclude}
    assert old_params==new_params
    assert context['reference_prediction_contract']['nominal_config_hash']==previous['pilots'][0]['context']['reference_prediction_contract']['nominal_config_hash']
    model=read(e/'model/model_report.json')
    mesh=e/'model/hull.dae';assert sha(mesh)==previous['configuration_comparison']['runs']['baseline']['model_identity']['mesh_sha256_by_relative_path']['hull.dae']
    result['metadata_assembly_attempts']=[{'script':'build_f5_metadata_v2.py','passed':False,'reason':'F4/F5 baseline ID was omitted from identity-field comparison; only baseline/run/output/config identity differs; no report was written'}]
    result['same_config_comparison']={'actual_parameters_equal_except_identity':True,'identity_fields_excluded_exactly':sorted(exclude),
        'nominal_effective_hash_equal':True,'plant_default_mesh_hash_equal':True,'mesh_sha256':sha(mesh),
        'performance_improvement_proven':False,'plant_equivalence_proven':False}
    spec=importlib.util.spec_from_file_location('f5_readonly_checker',ROOT/'usv_mpc_ws/scripts/check_reference_prediction.py')
    reader=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reader;spec.loader.exec_module(reader)
    bag=ROOT/'data/sim_bags'/RUN;cfg=reader.Config();records,types,reading=reader.read_bag(bag,cfg);assert reader.hash_bag(bag)==pub['bag_hash_after']
    states=[r.payload for r in records if r.topic==cfg.topics['state']];refs=[r.payload for r in records if r.topic==cfg.topics['reference_prediction']]
    epochs={}
    for state in states:
        if state['valid'] and state['clock_status']!='not_received':epochs.setdefault(state['clock_epoch'],[]).append(state['sim_time_ns'])
    spans={str(k):{'count':len(v),'start_ns':min(v),'end_ns':max(v),'span_s':(max(v)-min(v))/1e9} for k,v in epochs.items()}
    observation={'reference_modes':dict(Counter(r['reference_mode'] for r in refs)),'profile_sync_reasons':dict(Counter(r['profile_sync_reason'] for r in refs)),
        'clock_status_counts':dict(Counter(s['clock_status'] for s in states)),'valid_state_sim_epoch_spans':spans,
        'valid_state_sim_span_s':next(iter(spans.values()))['span_s'] if len(spans)==1 else None,
        'reference_eligibility_anomaly_count':ref['reference_path_eligibility_anomaly_count'],
        'prediction_available_count':sum(r['prediction_available'] for r in refs),'no_cross_epoch_aggregation':True}
    result['pilot']={'run_id':RUN,'bag':str(bag),'experiment':str(e),'result':read(e/'pilot_result.json'),
        'context':context,'session':read(e/'source/session_summary.json'),'publisher_contract':pub,'reference_contract':ref,
        'timing':read(e/'reports_initial/timing_report.json'),'shutdown_gap':read(e/'shutdown_gap_evidence.json'),
        'config_runtime':read(e/'config_runtime.json'),'model_report':model,'observation':observation}
    result['evidence_files']={}
    for name in ['production_patch_dryrun.log','production_patch_apply.log','production_diff_final.patch','build.log','build_result.json','colcon_test.log','colcon_test_result.log','cpp_gtest_summary.json','format.log','format_check.log','solver_test_evidence.json','atomic_freeze_test_evidence.json','commands.jsonl','run_f5_pilot.py','run_f5_pilot_v2.py','stop_after_publish_gap.py','assets_inventory_stage1.json','assets_inventory_stage2.json']:
        p=EXP/name;result['evidence_files'][name]={'sha256':sha(p),'bytes':p.stat().st_size}
    result['production_diff']=(EXP/'production_diff_final.patch').read_text()
    result['active_processes']=subprocess.run(['pgrep','-a','-f','mpc_node|gz sim|gz-sim|ros2 launch usv_bringup|stop_after_publish_gap.py'],capture_output=True,text=True).stdout.strip()
    assert not result['active_processes']
    p=EXP/'metadata_summary.json'
    with p.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    h=sha(p);print('F5_METADATA_BYTES',p.stat().st_size);print(h[:32]);print(h[32:])

if __name__=='__main__':main()
