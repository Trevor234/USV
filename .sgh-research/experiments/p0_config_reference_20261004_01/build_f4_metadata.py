"""Export hashes, reports and numeric evidence only; snapshots stay on Ubuntu."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter

ROOT=Path('/home/trevor/USV')
EXP=ROOT/'.sgh-research/experiments/p0_config_reference_20261004_01'
IDS=['p0_f4_config_baseline_20261005_02','p0_f4_config_plant_mass_20261005_01','p0_f4_config_nominal_mass_20261005_01']
FAILED='p0_f4_config_baseline_20261005_01'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def load(p):
    return json.loads(Path(p).read_text())

def stats(values):
    v=sorted(values)
    if not v:return {'count':0}
    return {'count':len(v),'min':v[0],'max':v[-1],'mean':sum(v)/len(v),
            'median':v[len(v)//2],'p95':v[min(len(v)-1,int(.95*(len(v)-1)))]}

def main():
    spec=importlib.util.spec_from_file_location('f4_readonly_checker',ROOT/'usv_mpc_ws/scripts/check_reference_prediction.py')
    reader=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reader;spec.loader.exec_module(reader)
    result={'schema':'p0-f4-config-reference-evidence/1','date':'2026-10-05','timezone':'Asia/Shanghai',
            'experiment':str(EXP),'stage_flags':{'configuration_isolation_verified':True,
            'four_stream_recording_verified':True,'actual_solve_input_observation_verified':True,
            'plant_acceptance_observed':False,'force_measured':False,'execution_atomicity_proven':False,
            'exact_execution_timing_available':False,'gp_labels_ready':False,'P0_complete':False,'P1_complete':False}}
    result['configuration_comparison']=load(EXP/'actual_config_comparison.json')
    assert result['configuration_comparison']['passed'] is True
    result['build']={'initial_build_log_sha256':sha(EXP/'build.log'),'test_rebuild_log_sha256':sha(EXP/'build_test_final.log'),
                     'installed_import':load(EXP/'installed_import.json')}
    result['tests']={'colcon_result_text':(EXP/'test_result_final.log').read_text(),
        'cpp_functional_cases':[],'python_scripts':{'run_count':178,'passed':177,'skipped':1,
        'skip_reason':'old Windows local-mirror compatibility smoke; old checker additionally passed on all actual F4 bags'},
        'config_tests':22,'telemetry_guard_tests':10,'cross_run_tool_tests':5,
        'collector_mesh_regression_tests':16,'closure_window_boundary_input_cases':8,
        'solver_test_evidence':load(EXP/'solver_test_evidence.json')}
    for p in sorted((ROOT/'usv_mpc_ws/build/usv_mpc_cpp/test_results/usv_mpc_cpp').glob('*.gtest.xml')):
        for suite in ET.parse(p).getroot().findall('testsuite'):
            for case in suite.findall('testcase'):
                result['tests']['cpp_functional_cases'].append({'name':suite.attrib['name']+'.'+case.attrib['name'],
                    'failed':case.find('failure') is not None,'skipped':case.find('skipped') is not None})
    result['tests']['unique_cpp_gtest_count']=len({c['name'] for c in result['tests']['cpp_functional_cases']})
    assert result['tests']['unique_cpp_gtest_count']==62 and not any(c['failed'] or c['skipped'] for c in result['tests']['cpp_functional_cases'])
    for line in (EXP/'colcon_test_final.log').read_text().splitlines():
        if 'reference_telemetry_observational_v1' in line:
            result['observation_benchmark']=json.loads(line[line.index('{'):])
    ev=result['tests']['solver_test_evidence']
    assert sha(ev['test_binary_path'])==ev['compiled_test_binary_sha256'] and sha(ev['gtest_report_path'])==ev['gtest_report_sha256']
    result['baselines']={}
    for baseline in ['F1_20261004_three_repairs_original_01','F2_20261004_publisher_contract_01','F3_20261004_quaternion_gate_01','F4_20261005_config_reference_01']:
        base=ROOT/'.sgh-research/baselines'/baseline;manifest=load(base/'baseline_manifest.json');snapshot_errors=[];live_errors=[];lists={}
        for filename,snapshot in [('source_hashes.json','source_snapshot'),('installed_hashes.json','installed_snapshot'),('model_assets.json','model_snapshot')]:
            document=load(base/filename);assets=document if isinstance(document,list) else document['files']
            lists[filename]=[{k:v for k,v in a.items() if k in ['path','resolved_path','sha256','bytes','valid','symlink']} for a in assets]
            for asset in assets:
                if asset.get('sha256'):
                    if sha(base/snapshot/asset['path'])!=asset['sha256']:snapshot_errors.append(asset['path'])
                    if baseline.startswith('F4_') and sha(ROOT/asset['path'])!=asset['sha256']:live_errors.append(asset['path'])
        item={k:manifest[k] for k in ['baseline_id','source_count','installed_count','model_count','runtime_effective_verified','integrity']}
        item.update(manifest_sha256=sha(base/'baseline_manifest.json'),snapshot_hash_errors=snapshot_errors,current_f4_live_hash_errors=live_errors)
        if baseline.startswith('F4_'):item['inventories']=lists
        result['baselines'][baseline]=item
        assert not snapshot_errors and not live_errors
    result['protected_historical_files']=[]
    for asset in load(EXP/'protected_historical_hashes.json'):
        actual=sha(asset['path']);check={**asset,'current_sha256':actual,'unchanged':actual==asset['sha256']}
        result['protected_historical_files'].append(check);assert check['unchanged']
    result['pilots']=[]
    for run in IDS:
        e=ROOT/'.sgh-research/experiments'/run;context=load(e/'run_context.json');bag=ROOT/'data/sim_bags'/run
        cfg=reader.Config();records,types,reading=reader.read_bag(bag,cfg)
        states=[r.payload for r in records if r.topic==cfg.topics['state']]
        refs=[r.payload for r in records if r.topic==cfg.topics['reference_prediction']]
        applied={r.payload['sequence']:r.payload for r in records if r.topic==cfg.topics['applied']}
        observation={'reference_modes':dict(Counter(r['reference_mode'] for r in refs)),
                     'profile_sync_reasons':dict(Counter(r['profile_sync_reason'] for r in refs)),
                     'reference_first_u_m_s':stats([r['reference_data'][3] for r in refs]),
                     'reference_first_v_m_s':stats([r['reference_data'][4] for r in refs]),
                     'actual_start_minus_nearest':stats([r['start_index']-r['nearest_index'] for r in refs]),
                     'horizon_steps':sorted(set(r['horizon_steps'] for r in refs)),
                     'prediction_dt':sorted(set(r['prediction_dt'] for r in refs)),
                     'prediction_available_count':sum(r['prediction_available'] for r in refs),
                     'controller_ref_state_u_m_s':stats([r['controller_state_6'][3] for r in refs]),
                     'candidate_u0_vs_published_final_absdiff_N':stats([abs(r['u_pred_data'][k]-applied[r['applied_sequence']]['final_n'][k]) for r in refs if r['prediction_available'] for k in range(2)])}
        sim=[s['sim_time_ns'] for s in states if s['clock_status']=='valid']
        observation['valid_state_sim_span_s']=(max(sim)-min(sim))/1e9 if sim else None
        item={'run_id':run,'experiment':str(e),'bag':str(bag),'result':load(e/'pilot_result.json'),
            'session':load(e/'source/session_summary.json'),'publisher_contract':load(e/'reports_initial/contract_report.json'),
            'reference_contract':load(e/'reference_reports/reference_prediction_report.json'),
            'timing':load(e/'reports_initial/timing_report.json'),'context':context,
            'config_runtime':load(e/'config_runtime.json'),'model_report':load(e/'model/model_report.json'),
            'shutdown_gap':load(e/'shutdown_gap_evidence.json'),'observation_metrics':observation}
        assert item['result']['all_required_acceptance_flags'] is True
        assert item['reference_contract']['actual_solve_input_verified'] is True
        assert reader.hash_bag(bag)==item['publisher_contract']['bag_hash_after']
        result['pilots'].append(item)
    e=ROOT/'.sgh-research/experiments'/FAILED
    result['failed_attempts']=[{'run_id':FAILED,'result':load(e/'pilot_result.json'),
        'publisher_contract':load(e/'reports_initial/contract_report.json'),
        'reference_contract':load(e/'reference_reports/reference_prediction_report.json'),
        'session':load(e/'source/session_summary.json'),
        'cause':'timer zero and shutdown zero overlap in fixed 20ms matching window; original bag retained',
        'remedy':'new owned lifecycle observer closes 70-110ms after actual publisher return; matcher unchanged'}]
    result['evidence_files']={}
    for rel in ['preflight.json','preflight_reflection_20261004.md','actual_config_comparison.json','solver_test_evidence.json',
                'run_f4_pilot.py','run_f4_pilot_v2.py','stop_after_publish_gap.py','assets_inventory.json',
                'build.log','build_test_final.log','colcon_test.log','colcon_test_final.log','test_result_final.log',
                'python_tests_2.log','python_tests_final_0.log','python_tests_final_1.log','compare_tool_tests.log','collector_mesh_tests.log']:
        p=EXP/rel;result['evidence_files'][str(p.relative_to(ROOT))]={'sha256':sha(p),'bytes':p.stat().st_size}
    result['final_processes']=subprocess.run(['pgrep','-a','-f','mpc_node|gz sim|gz-sim|ros2 launch usv_bringup|stop_after_publish_gap.py'],capture_output=True,text=True).stdout.strip()
    assert not result['final_processes']
    output=EXP/'metadata_summary.json'
    with output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'metadata_bytes':output.stat().st_size,'metadata_sha256':sha(output),'pilots':len(result['pilots']),'snapshots_and_old_bags_unchanged':True}))

if __name__=='__main__':main()
