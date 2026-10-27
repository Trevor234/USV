"""Export only numeric evidence, identities and hashes; keep source bodies on host."""
from pathlib import Path
import json, hashlib, subprocess
ROOT = Path('/home/trevor/USV')
EXP = ROOT / '.sgh-research/experiments/p0_model_consistency_20261004_01'
RUN = 'p0_f3_gate_straight_20261004_03'
PILOT = ROOT / '.sgh-research/experiments' / RUN
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    return json.loads(p.read_text())
def rows(v):
    return v if isinstance(v, list) else v['files']

result = {'schema':'p0-model-reference-quaternion-evidence/1', 'experiment':str(EXP),
          'preflight':load(EXP/'preflight.json'), 'quaternion_patch':load(EXP/'quaternion_patch.json'),
          'cpp_tests':load(EXP/'cpp_test_summary.json'),
          'reference_implementation':load(EXP/'reference_implementation_audit.json'),
          'plant_configuration':load(EXP/'plant_configuration_audit.json'),
          'old_pilot_reference_diagnostics':load(EXP/'reference_bag_diagnostics.json'),
          'software_parity_v2':load(EXP/'parity_results/results.json'),
          'software_parity_v3':load(EXP/'parity_results_v3/results.json'),
          'default_parameter_differences':load(EXP/'parity_results_v3/defaults_difference.json'),
          'dependency_versions':load(EXP/'parity_results_v3/dependency_versions.json')}
assert result['software_parity_v3']['passed']
result['gazebo_installed_versions']=subprocess.run(['dpkg-query','-W','-f=${Package} ${Version}\n','libgz-sim8','libgz-physics7'],capture_output=True,text=True,check=True).stdout.strip().splitlines()
protected=load(EXP/'protected_bag_hashes.json')
for asset in protected:
    assert sha(Path(asset['path']))==asset['sha256']
    assert Path(asset['path']).stat().st_size==asset['bytes']
result['protected_historical_files']={'checked_files':protected,'unchanged':True,'scope':'six files with prior known hashes, not universal historical completeness'}
result['software_parity_v2']['unique_numeric_input_count'] = 285
result['software_parity_v3']['unique_numeric_input_count'] = 291
result['baselines']={}
expected={'F1_20261004_three_repairs_original_01':'fc5da9d219e1eba73326d3f1ca1ee61e101882bace9c49c587709f11dea6e23d',
          'F2_20261004_publisher_contract_01':'6e967d07de4f4232977f7b8fca1d6f6e4582812ea0d6ac1273159566d0214b75'}
for name in list(expected)+['F3_20261004_quaternion_gate_01']:
    base=ROOT/'.sgh-research/baselines'/name
    manifest=load(base/'baseline_manifest.json')
    digest=sha(base/'baseline_manifest.json')
    if name in expected:assert digest==expected[name]
    checks=[]; source=rows(load(base/'source_hashes.json'));installed=rows(load(base/'installed_hashes.json'));models=rows(load(base/'model_assets.json'))
    for folder,assets in [('source_snapshot',source),('installed_snapshot',installed),('model_snapshot',models)]:
        for a in assets:
            if a.get('sha256') and sha(base/folder/a['path'])!=a['sha256']:checks.append(folder+'/'+a['path'])
    assert not checks
    live=[]
    if name=='F3_20261004_quaternion_gate_01':
        for a in source+installed+models:
            if a.get('sha256') and sha(ROOT/a['path'])!=a['sha256']:live.append(a['path'])
        assert not live
    result['baselines'][name]={'manifest_sha256':digest,'source_count':len(source),'installed_count':len(installed),
                              'model_count':len(models),'snapshot_hash_errors':checks,'live_hash_errors':live,
                              'frozen_baseline_verified':manifest['integrity']['frozen_baseline_verified'],
                              'source_hashes':source,'installed_files':installed,'model_files':models,
                              'git_head':manifest['git']['head']['stdout'].strip()}

pilot_result=load(PILOT/'pilot_result.json');assert pilot_result['reason'] is None and pilot_result['check_exit_code']==0
contract=load(PILOT/'reports_initial/contract_report.json');timing=load(PILOT/'reports_initial/timing_report.json')
context=load(PILOT/'run_context.json');assert context['frozen_baseline_verified'] and context['runtime_effective_verified']
import sys,math
sys.path.insert(0,str(ROOT/'usv_mpc_ws/scripts'))
import check_p0_contract as c
bag=ROOT/'data/sim_bags'/RUN;before=c.hash_bag(bag);records,_,_=c.read_bag(bag,c.Config())
groups={k:[r.payload for r in records if r.topic==v] for k,v in c.DEFAULT_TOPICS.items()}
states=[p for p in groups['state'] if p['valid']]
path=next(p for p in reversed(groups['path']) if len(p['poses'])>=2)
points=[(p['pose']['position']['x'],p['pose']['position']['y']) for p in path['poses']]
def distance(s):
    x,y=s[:2];out=[]
    for (a,b),(u,v) in zip(points,points[1:]):
        dx=u-a;dy=v-b;n=dx*dx+dy*dy
        fraction=max(0,min(1,((x-a)*dx+(y-b)*dy)/n)) if n else 0
        out.append(math.hypot(x-a-fraction*dx,y-b-fraction*dy))
    return min(out)
ctes=[distance(p['state_6']) for p in states]
session=load(PILOT/'source/session_summary.json')
metrics={'state_count':len(groups['state']),'valid_state_count':len(states),'applied_count':len(groups['applied']),
         'cycle_count':len(groups['cycle']), 'source_window_wall_s':(session['end_steady_ns']-session['start_steady_ns'])/1e9,
         'state_sim_coverage_s':(states[-1]['odom_stamp_ns']-states[0]['odom_stamp_ns'])/1e9,
         'cte_rmse_m':math.sqrt(sum(x*x for x in ctes)/len(ctes)), 'cte_m':c.distribution(ctes),
         'u_m_s':c.distribution([p['state_6'][3] for p in states]),
         'body_speed_m_s':c.distribution([math.hypot(*p['state_6'][3:5]) for p in states]),
         'controller_cpu_one_core_percent':context['controller_cpu_one_core_percent'],
         'queue_dropped_total':session['queue_dropped_total'], 'bag_hashes':before,
         'raw_bag_unchanged':before==c.hash_bag(bag),'scope':'single normal 60-wall-second regression, whole source window including standby; descriptive only'}
assert metrics['raw_bag_unchanged']
result['f3_pilot']={'run_id':RUN,'experiment':str(PILOT),'result':pilot_result,'contract':contract,'timing':timing,
                    'context':context,'session_summary':session,'metrics':metrics}
result['failed_attempts']={'f3_pilot_01':load(ROOT/'.sgh-research/experiments/p0_f3_gate_straight_20261004_01/run_failure.json'),
                         'f3_pilot_02':load(ROOT/'.sgh-research/experiments/p0_f3_gate_straight_20261004_02/run_failure.json'),
                         'build_01':'test helper steady_now not visible; fixed to identical steady_clock epoch',
                         'build_test_02':'GTests passed; cpplint/uncrustify failed, subsequently fixed',
                         'build_test_03':'57 unique C++ GTests and colcon 376 checks: 0 errors/0 failures/72 skipped'}
result['evidence_files']={}
for folder in [EXP/'parity_results', EXP/'parity_results_v3']:
    for p in folder.iterdir():
        if p.is_file():result['evidence_files'][str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':sha(p)}
for p in EXP.glob('*.log'):
    result['evidence_files'][str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':sha(p)}
processes=[]
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:
            comm=(p/'comm').read_text().strip()
            if comm in ['mpc_node','gz-sim-server','gzserver','gz','ruby']:processes.append({'pid':int(p.name),'comm':comm})
        except OSError:pass
assert not processes
result['final_processes']=processes
result['stage_flags']={'python_cpp_nominal_verified':True,'native_acados_discrete_verified':True,
                      'reference_function_verified':True,'quaternion_admission_fixed':True,
                      'controller_plant_parameter_decoupling_done':False,'plant_equivalence_proven':False,
                      'exact_execution_timing_available':False,'gp_labels_ready':False,'P0_all_complete':False,'P1_complete':False}
target=EXP/'metadata_summary.json';assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':sha(target),
                  'pilot_metrics':metrics,'stage_flags':result['stage_flags']},ensure_ascii=False))
