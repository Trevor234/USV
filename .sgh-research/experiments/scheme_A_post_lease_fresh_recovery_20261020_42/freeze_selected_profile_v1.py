"""Freeze actual closed-profile evidence and explicit diagnostic differences, not B5 authority."""
from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent;W=D.parent
PINS={}
def raw(p):
 p=Path(p);b=p.read_bytes();f=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());assert str(p) not in PINS or PINS[str(p)]==f;PINS[str(p)]=f;return b
def load(p):return json.loads(raw(p))
def pin(p):b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def dump(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
def main():
 specs=[(39,W/'scheme_A_owned_business_start_20261020_39','business_active_01','postrun/business_ordinary_actual_audit_v1.json','ordinary active stimulus'),
  (40,W/'scheme_A_final_V1_gate_confirmation_20261020_40','final_V1_01','postrun/current_V1_actual_audit_v1.json','actual V1 Sink failure'),
  (41,W/'scheme_A_ordinary_lease_20261020_41','ordinary_lease_01','postrun/ordinary_lease_actual_audit_v1.json','ordinary receipt lease stimulus'),
  (42,D,'fresh_after_lease_01','postrun/fresh_recovery_actual_audit_v2.json','healthy fresh identity after lease41')]
 profiles=[]
 for batch,B,run,auditpath,scope in specs:
  a=load(B/auditpath);assert a['passed'] and a['input_sha256_before']==a['input_sha256_after'];R=B/'author/runs'/run;inputs=load(R/'inputs.json')
  roles={k:load(R/k/'owned_manifest.json') for k in ['observer','worker','publisher','synthetic_source','recorder']}
  profiles.append(dict(batch=batch,run_id=run,scope=scope,root=str(R),audit=dict(path=str(B/auditpath),**pin(B/auditpath)),
   roles=roles,complete_expected_parameters=inputs['expected_parameters'],contract_sha256=inputs['contract_sha256'],
   source_bundles=inputs['source_bundles'],normal_business_qualified=False,stage_qualified=False,execute_qualified=False))
 current=profiles[-1];registry=load(D/'author/build_manifest_current.json');registry={r['role']:r for r in registry}
 role_pins={}
 for role,m in current['roles'].items():
  key='fixture' if role=='synthetic_source' else role;reg=registry[key]
  assert pin(m['exe'])['sha256']==m['binary_sha256']==reg['binary_sha256']
  assert m['source_bundle_sha256']==reg['source_bundle']['sha256'];bundle=load(reg['source_bundle']['path']);assert pin(reg['source_bundle']['path'])['sha256']==m['source_bundle_sha256']
  for f in bundle['files'].values():assert pin(f['path'])==dict(bytes=f['bytes'],sha256=f['sha256'])
  role_pins[role]=dict(binary=dict(path=m['exe'],**pin(m['exe'])),bundle=reg['source_bundle'],
   manifest=dict(path=str(Path(current['root'])/role/'owned_manifest.json'),**pin(Path(current['root'])/role/'owned_manifest.json')),
   effective_parameters_sha256=m['effective_parameters_sha256'],effective_parameters=m['effective_parameters'],
   endpoints_are_historical_closed_run_evidence=True)
 changes=[]
 for prior in profiles[:-1]:
  diff={}
  for role,m in current['roles'].items():
   old=prior['roles'][role]
   assert old['binary_sha256']==m['binary_sha256'] and old['source_bundle_sha256']==m['source_bundle_sha256']
   oldp,newp=old['effective_parameters'],m['effective_parameters'];assert set(oldp)==set(newp)
   diff[role]={k:dict(old=oldp[k],current=newp[k]) for k in oldp if oldp[k]!=newp[k]}
  changes.append(dict(from_batch=prior['batch'],to_batch=42,all_five_ELFs_and_bundles_identical=True,exact_typed_parameter_differences=diff))
 contract=load(D/'author/pair_wakeup_contract_v1.json');assert pin(D/'author/pair_wakeup_contract_v1.json')['sha256']==current['contract_sha256']
 # Bind correction authority to the actual registered Observer compilation bundle.
 ob=registry['observer'];source_bundle=load(ob['source_bundle']['path']);authority=next(f for f in source_bundle['files'].values() if Path(f['path']).name=='phase_protocol.hpp')
 assert raw(authority['path'])==raw(D/'author/phase_protocol.hpp')
 text=raw(authority['path']).decode().splitlines();assert 'j.deadline_ns!=j.origin_ns+ready_ns' in text[229] and 'j.target_ns!=j.origin_ns+period_ns' in text[229]
 dump(D/'verification/deadline_registered_source_binding_v1.json',dict(passed=True,registered_Observer_ELF_sha256=ob['binary_sha256'],
  registered_source_bundle=ob['source_bundle'],authority=authority,copied_header_identical=True,
  strict_lines={str(i):text[i-1] for i in [229,230,231]},
  interpretation='per-job origin=previous accepted Decision planned_ns; fixed deadline origin+150ms and target origin+200ms',
  actual_run_rerun=False,stage_qualified=False))
 before=dict(PINS)
 for p in before:raw(p)
 assert before==PINS
 report=dict(schema='selected-closed-shadow-profile-evidence-freeze/v1',evidence_freeze_completed=True,current_run='fresh_after_lease_01',
  selected_domain='synthetic nominal localhost, controlled C, reference0.05m/s, current gated shadow, diagnostic comparison cases explicitly separate',
  current_role_pins=role_pins,contract=dict(path=str(D/'author/pair_wakeup_contract_v1.json'),**pin(D/'author/pair_wakeup_contract_v1.json'),fields=contract),
  current_complete_expected_parameters=current['complete_expected_parameters'],diagnostic_profile_register=profiles,
  exact_profile_differences=changes,complete_loader=load(D/'preflight/loader_environment_v2.json'),
  same_five_current_ELFs_confirmed_across39_40_41_42=True,
  old_run_ids_PIDs_instances_and_paths_not_normalized_away=True,input_sha256_before=before,input_sha256_after=before,
  formal_B5_freeze=False,M0b_formal_qualification=False,M4_qualified=False,B4_all_groups_qualified=False,
  normal_business_qualified=False,stage_qualified=False,execute_qualified=False,true_plant_qualified=False,research_conclusion=False)
 dump(D/'postrun/selected_profile_evidence_freeze_v1.json',report)
 print(json.dumps(dict(evidence_freeze_completed=True,roles=5,diagnostic_profiles=4,contract_fields=len(contract),read_inputs=len(PINS),formal_B5_freeze=False)))
if __name__=='__main__':main()
