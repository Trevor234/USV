from pathlib import Path
import datetime, json, os, subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_matrix import ROOT, pin, save

REPO=ROOT.parents[2]
inputs=json.loads((ROOT/'evidence/inputs/manifest_v1.json').read_text())
def drift(records):
    return [p for p,v in records.items()if not Path(p).is_file()or pin(p)!=v]
input_drift=drift(inputs['files'])
previous_drift=drift(inputs['previous127_files'])
library_drift=drift(inputs['runtime_libraries'])
previous126=ROOT.parent/'scheme_A_M4_offline_hardening_20261026_126'
pop=json.loads((previous126/'evidence/delivery_population_v1.json').read_text())
protected126={str(previous126/p):record for p,record in pop['files'].items()}
protected126.update({str(previous126/r['path']):{'bytes':r['bytes'],'sha256':r['sha256']}for r in pop['excluded_build_files']})
drift126=drift(protected126)
workspace=[]
for name,record in inputs['workspace_files'].items():
    p=REPO/name
    now={'kind':'file',**pin(p)}if p.is_file()else{'kind':'directory'if p.is_dir()else'absent'}
    if now!=record:workspace.append({'path':name,'before':record,'now':now})
current_git=subprocess.check_output(['git','-c','core.quotepath=false','status','--porcelain=v1','-z','-uall'],cwd=REPO).decode()
required={}
for directory in ['abi_probe01','characterization03','validation01','mutations01','parity_and_recipe01','patch_replay01']:
    data=json.loads((ROOT/'evidence'/directory/'verification.json').read_text());required[directory]=data
matrix=required['validation01']
runtime_drift=drift(matrix['runtime_shared_objects'])
patch=json.loads((ROOT/'postrun/patch_v1.json').read_text())
patch_pins_ok=(pin(patch['candidate_factory']['path'])==patch['candidate_factory']['pin'] and
               pin(ROOT/'patches/01_factory_shared_parameter_admission.patch')==patch['patch'])
artifacts={str(p.relative_to(ROOT)):pin(p)for p in (ROOT/'implementation').rglob('*')if p.is_file()}
save(ROOT/'evidence/final_source_identity_v1.json',{'files':artifacts,'recorded_after_tests':True,
    'note':'Component delivery identity, not a pre-registered owned source bundle'})
statistics={'rows':0,'successful_solves':0,'casadi_successful_solves':0,'acados_successful_solves':0,'disabled_direct_api_cases':0}
for p in (ROOT/'evidence/validation01/cases').rglob('result.json'):
    r=json.loads(p.read_text());statistics['rows']+=1
    statistics['disabled_direct_api_cases']+=not r['available']
    for s in r['rows']:
        statistics['successful_solves']+=s['success']
        if s['success']:statistics[s['backend']+'_successful_solves']+=1
checks={'inputs_unchanged':not input_drift,'previous127_all_786_preserved':not previous_drift,
        'previous126_delivery_population_preserved':not drift126,'declared_runtime_libraries_unchanged':not library_drift,
        'actual_loaded_libraries_still_match':not runtime_drift,'all_six_evidence_groups_complete':all(r['complete']for r in required.values()),
        'expected_78_matrix_rows':matrix['case_count']==78 and statistics['rows']==78 and matrix['failures']==[],
        'four_prepared_runtime_mutations_caught':required['mutations01']['prepared_count']==4 and required['mutations01']['caught_count']==4,
        '16_finite_parity_cases':len(required['parity_and_recipe01']['finite_parity_cases'])==16,
        'patch_pin_still_current':patch_pins_ok,
        'copied_codegen_archive_identity':pin(ROOT/'implementation/libgenerated_current.a')==inputs['files'][inputs['generated_archive_origin']]}
qualification={k:False for k in ['M4','F6','P1','plant','hard_realtime']}
result={'schema':'factory-routing128-final-v1','recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'complete':all(checks.values()),'status':'COMPONENT_REVIEW_COMPLETE_LANDING_AND_OWNED_GATES_OPEN'if all(checks.values())else'FAIL_STOP',
        'checks':checks,'statistics':statistics,'input_population':len(inputs['files']),'input_drift':input_drift,
        'previous127_population':len(inputs['previous127_files']),'previous127_drift':previous_drift,
        'previous126_population':len(protected126),'previous126_drift':drift126,'runtime_library_drift':library_drift,
        'actual_runtime_drift':runtime_drift,'workspace_entry_population_before':len(inputs['workspace_files']),
        'workspace_drift':workspace,'git_porcelain_z_before':inputs['git_porcelain_z'],'git_porcelain_z_after':current_git,
        'concurrent_workspace_changes':'Preserved and recorded; never restored, reset or included in candidate patch',
        'component_factory_gate':'CLOSED_FOR_REGISTERED_MATRIX_ONLY','full_ROS_CMake_build_qualification':False,
        'historical_failures':['characterization01 link chose the wheel HPIPM','characterization02 all 52 processes loader-exited 127; no solver entry'],
        'production_edits':0,'ROS_initialized':False,'new_owned_runs':0,'qualification':qualification,'production_B_mode':'MANUAL+RC override'}
save(ROOT/'evidence/final_verification_v1.json',result)
save(ROOT/'postrun/next_plan_v1.json',{
    'next_step':'RawBackend common-header reuse draft and cold/native policy regression',
    'ordered_steps':[
       {'id':'R1','do':'Pin the actual RawBackend, native policy and current Worker call graph; derive a new isolated author tree',
        'accept':'All frozen inputs and workspace state recorded; separate current native failure policies enumerated',
        'limits':'No production edit, no Worker owner or model/reference policy redesign'},
       {'id':'R2','do':'Replace only duplicated parameter packing/setter admission with batch127 shared headers',
        'accept':'Pure packing parity first; checked setter rejection separately consumes result and preserves capsule cleanup and cold policy',
        'limits':'No hot-update API, no generation commit, no deadline extension or fallback relaxation'},
       {'id':'R3','do':'Replay real cold/native policy and target boundary tests with normal and named fault controls',
        'accept':'Normal/stop/deadline/nonfinite/reported-error branches, resource balance and API facts agree; meaningful runtime mutations caught',
        'limits':'Compile error, timeout or missing event never counts as correct rejection; all failed evidence retained'},
       {'id':'R4','do':'Write separate patch inventory, protection report and MPC exact readback',
        'accept':'Component result distinct from M4/F6/P1 and production eligibility',
        'limits':'Stop this package after review; no automatic production landing or owned run'},
       {'id':'R5','do':'Then design Worker unique-owner creation/use/destruction and immutable capability readiness',
        'accept':'Explicit lifecycle, bootstrap/discovery and stop/exception protocol with negative controls',
        'limits':'Design and bounded component work before runtime adoption'},
       {'id':'R6','do':'Then define model/reference binding and target-tick activation, then separately review landing/freeze/owned needs',
        'accept':'Registered model table, full binding, pending job policy and activation evidence clear',
        'limits':'No GP collection, plant or RT activity inferred from continue'}],
    'automatic_production_landing':False,'automatic_owned_runs':0,'qualification':qualification})
print(json.dumps({'complete':result['complete'],'checks':checks,'statistics':statistics,
                  'workspace_drift':len(workspace),'previous127':len(inputs['previous127_files']),'previous126':len(protected126)},ensure_ascii=False))
raise SystemExit(0 if result['complete']else 2)
