#!/usr/bin/env python3
"""Explicit boot transition for unchanged archived bytes; no run/PID authority transfer."""
from pathlib import Path
import argparse,json,os,sys,time
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent;sys.path.insert(0,str(D));import protection_v3 as P
C=P.C;V=P.V
TRANSITION=D/'preflight/boot_transition_v4.json'
def without_boot(value):
 x=P.projection(value);x.pop('boot_id');return x

def raw_protect(transition):
 anchor=C.Reader().json(P.ANCHOR);C.require(P.stable_sha(P.ROSTER)['sha256']==anchor['roster_sha256'],'original_flat_roster_changed')
 roster=C.Reader().json(P.ROSTER)
 C.require(P.stable_sha(P.ANCHOR)['sha256']==transition['original_anchor_sha256'] and anchor['roster_sha256']==transition['original_roster_sha256'],'boot_transition_original_anchor')
 C.require(P.stable_sha(Path(__file__))['sha256']==transition['helper_sha256'],'boot_transition_helper_changed')
 C.require(roster['parent_inventory_sha256']==V.PIN['archive_inventory_v1.json'] and roster['parent_QA_sha256']==V.PIN['postrun/final_QA_current.json'] and roster['parent_proof_sha256']==anchor['parent_proof_sha256'],'parent_semantic_anchor_identity')
 for path,sha in anchor['provenance_file_sha256'].items():C.require(P.stable_sha(path)['sha256']==sha,'capture_provenance_changed:'+path)
 before=V.workspace();C.require(before['boot_id']==transition['resumed_boot_id'],'resumed_boot_changed_again')
 C.require(without_boot(before)==transition['preserved_workspace_projection_without_boot']==without_boot(roster['initial_workspace_projection']),'non_boot_workspace_changed')
 for path,target in roster['legacy_symlink_targets'].items():C.require(Path(path).is_symlink() and os.readlink(path)==target,'legacy_symlink_changed:'+path)
 for path,target in roster['legacy_symlink_logical_aliases'].items():C.require(str(Path(path).resolve(strict=True))==target,'legacy_alias_changed:'+path)
 for path,pin in roster['files'].items():C.require(P.stable_sha(path,pin)==pin,'old_raw_file_changed:'+path)
 for path,entries in roster['directories'].items():C.require(V.directory_entries(path)==entries,'old_population_changed:'+path)
 C.require(P.projection(V.workspace())==P.projection(before),'workspace_changed_during_recheck')
 proof=P.proof_value(roster,anchor,before)
 proof.update(schema='C3.10-preservation/v4',boot_transition_record_sha256=P.stable_sha(TRANSITION)['sha256'],semantic_capture_boot_id=transition['original_capture_boot_id'],current_asset_recheck_boot_id=transition['resumed_boot_id'],old_run_or_endpoint_qualification_transferred=False,recomputed_historical_semantics_after_reboot=False,complete_raw_bytes_rechecked_after_reboot=True)
 return proof

def protect():return raw_protect(C.Reader().json(TRANSITION))
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['resume','verify']);p.add_argument('--output',type=Path,required=True);a=p.parse_args();C.require(a.output.is_absolute() and a.output.parent==D/'preflight','new_preflight_only');began=time.monotonic();before=V.workspace()
 try:
  if a.mode=='resume':
   old=C.Reader().json(P.ROSTER)['initial_workspace_projection'];C.require(old['boot_id']!=before['boot_id'],'actual_new_boot_required');C.require(without_boot(old)==without_boot(before),'other_workspace_change_before_resume')
   transition={'schema':'C3.10-boot-transition/v4','old_original_semantic_and_data_preservation_records_retained':True,'original_capture_boot_id':old['boot_id'],'resumed_boot_id':before['boot_id'],'original_roster_sha256':P.stable_sha(P.ROSTER)['sha256'],'original_anchor_sha256':P.stable_sha(P.ANCHOR)['sha256'],'helper_sha256':P.stable_sha(Path(__file__))['sha256'],'preserved_workspace_projection_without_boot':without_boot(before),'workspace_full_at_resume':before,'old_run_or_endpoint_qualification_transferred':False,'known_actual02_already_completed_before_full_resume_recheck':True,'phase_qualified':False,'research_conclusion':False}
   V.write_new(TRANSITION,transition)
  proof=protect();result={'schema':'C3.10-resumed-asset-preflight/v4','passed':True,'protection':proof,'workspace_before':before,'workspace_after':V.workspace(),'old_semantic_proof_retained':True,'current_endpoints_checked':False,'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
 except Exception as e:result={'passed':False,'error':repr(e),'workspace_before':before,'workspace_after':V.workspace(),'stage_qualified':False,'research_conclusion':False}
 result['elapsed_seconds']=time.monotonic()-began;V.write_new(a.output,result);print(json.dumps({'passed':result['passed'],'error':result.get('error'),'elapsed_seconds':result['elapsed_seconds'],'output':str(a.output)}));return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
