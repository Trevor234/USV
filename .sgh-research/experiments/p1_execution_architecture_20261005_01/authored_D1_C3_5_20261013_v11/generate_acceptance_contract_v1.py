#!/usr/bin/env python3
"""Create an immutable, explicit replacement component contract for fixed N10 evidence."""
import hashlib,json,sys
from pathlib import Path
import acceptance_core_v1 as C
import check_acceptance_v1 as A
N=Path(__file__).resolve().parent;D=A.D;BATCH=D.parent/'scheme_A_C3_4_20261013_09';PARENT=A.PARENT
def pin(path):
    p=Path(path);raw=p.read_bytes();return {'path':str(p.absolute()),'sha256':C.digest(raw),'bytes':len(raw)}
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
    manifest_path=BATCH/'final_frozen_snapshot/manifest.json';parent=C.strict_json(manifest_path.read_bytes())
    expected=json.loads((D/'preflight/workspace_initial.json').read_text())['N10_manifest_sha256']
    C.require(pin(manifest_path)['sha256']==expected,'parent_manifest_drift')
    identities={};records={}
    for row in parent['files']:
        p=pin(row['original']);C.require(p['sha256']==row['sha256'],'parent_source_bin_drift');identities[p['path']]=p
    for row in parent['owned_raw']:
        p=pin(row['original']);C.require(p['sha256']==row['sha256'],'parent_raw_drift');records[p['path']]=p
    external_identities,external_records=A.registered_inputs()
    identities={p['path']:p for p in external_identities};records={p['path']:p for p in external_records}
    jobs=[]
    for name,(tool,args,key) in A.registered_jobs().items():
        jobs.append({'id':name,'tool':pin(tool),'args':args,'result_key':key,'budget_seconds':45,
                     'scope':'fresh reanalysis of locked current-version finite component originals; no new runtime or phase qualification'})
    budget=json.loads((D/'budget_scope/result_v1.json').read_text());budget_rules=list(budget['rules'])
    deps={'B4':['identity_closure','record_identity','normal_owned','normal_atomic','config_domain','current_readiness','budget_scope',
                'budget_scope__observed_runtime_budgets','budget_scope__observed_ready_gate','budget_scope__anchor_guard_observed',
                'budget_scope__anchor_execution_contract','budget_scope__current_stress_recovery_failed_close'],
          'M0b':['B4','engineering_execution_time_policy','budget_scope__current_dynamic20s','budget_scope__current_turn_mixed'],
          'B5':['M0b','normal_release','expired_release','preparation_io','immutable_execute_policy_contract'],
          'M4':['B5','new_execute_source_bin','continuous_unique_publisher_handoff','actual_nonzero_and_partial_publish',
                'rho_gap_budget_execution_evidence']}
    deferred={
      'engineering_execution_time_policy':{'status':'not_run','evidence':'current finite observations and failclosed gates exist; engineering guarantee assumptions/domain and out-of-domain policy must be selected before execute',
                                          'scope':'does not require claiming unknown physical WCET or true Master Clock as zero'},
      'immutable_execute_policy_contract':{'status':'not_run','evidence':'this is a bounded evidence acceptance contract; actual unified execute/close/recovery policy remains separate'},
      'new_execute_source_bin':{'status':'not_run','evidence':'no M4 execution version built or launched'},
      'continuous_unique_publisher_handoff':{'status':'not_run','evidence':'no transition from F5 owner to regulator actuator owner performed'},
      'actual_nonzero_and_partial_publish':{'status':'not_run','evidence':'accepted shadow proposal with publish_success=false is not an actuator event'},
      'rho_gap_budget_execution_evidence':{'status':'not_run','evidence':'new execution-level rho/gap/hold policy and actual publish evidence absent'}}
    contract={'schema':'p1-C3.5-bounded-acceptance-contract/v1','profile':C.PROFILE,'author_directory':str(N),
      'runtime_source_root':str(PARENT),'new_runtime_launches':False,'stage_support':[],
      'record_lock_semantics':'retrospective frozen N10 raw records; not independent pre-run qualification',
      'preregister':pin(D/'preregister/execution_scope_v1.json'),'identity_pins':list(identities.values()),
      'record_pins':list(records.values()),'jobs':jobs,'job_rule_adapters':{'budget_scope':budget_rules},
      'required_components':['identity_closure','record_identity',*[j['id'] for j in jobs]],
      'phase_requires':deps,'deferred_rules':deferred,
      'historical_identity_policy':'new explicit replacement components; historical shared-v2 four SHA identities are not restored or impersonated',
      'clock_policy':'same host/boot monotonic observations only; hard Master Clock, plant ACK/hold, and WCET remain separately unknown',
      'current_and_captured_tool_versions':'old runtime snapshot identity checked by readiness separately from current frozen source identity'}
    contract['phase_requires']=A.registered_phase_requires();contract['deferred_rules']=A.registered_deferred_rules();contract['job_rule_adapters']=A.ADAPTERS
    A.validate_contract(contract);path=D/'preregister/acceptance_contract_v3.json';write(path,contract)
    write(D/'preregister/acceptance_contract_pin_v3.json',pin(path));print(json.dumps({'contract':pin(path),'jobs':len(jobs),'identity_pins':len(identities),'record_pins':len(records)}))
if __name__=='__main__':main()
