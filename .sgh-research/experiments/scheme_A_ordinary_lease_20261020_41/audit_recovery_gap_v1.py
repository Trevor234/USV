"""Read-only cross-run identity evidence inventory; does not claim post-lease41 recovery."""
from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent;W=D.parent;PINS={}
def raw(p):
    p=Path(p);b=p.read_bytes();v=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());assert str(p) not in PINS or PINS[str(p)]==v;PINS[str(p)]=v;return b
def load(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines()]
def main():
    specs=[(39,W/'scheme_A_owned_business_start_20261020_39','business_active_01','postrun/business_ordinary_actual_audit_v1.json'),
        (40,W/'scheme_A_final_V1_gate_confirmation_20261020_40','final_V1_01','postrun/current_V1_actual_audit_v1.json'),
        (41,D,'ordinary_lease_01','postrun/ordinary_lease_actual_audit_v1.json')]
    cases=[]
    for batch,B,run,audit_name in specs:
        audit=load(B/audit_name);assert audit['passed'] and audit['input_sha256_before']==audit['input_sha256_after']
        R=B/'author/runs'/run;r=load(R/'result.json');ledger=lines(R/'owned_process_ledger.jsonl');source=lines(R/'observer/source.jsonl');witness=load(R/'observer/witness.json')
        manifests={role:load(R/role/'owned_manifest.json') for role in ['observer','worker','publisher','synthetic_source','recorder']}
        cleans=[x for x in ledger if x['type']=='cleanup_result'];assert len(cleans)==5 and all(x['cleanup_complete'] and not x['remaining_members'] for x in cleans)
        accepted=[x for x in source if x.get('type')=='decision' and x['accepted']];assert accepted
        callbacks=[x for x in source if x.get('type')=='controlled_phase_callback' and x.get('accepted') and any(d['sequence']==x['phase']['decision_sequence'] for d in accepted)];assert callbacks
        wm=manifests['worker'];assert witness['header']['worker_instance']==wm['worker_instance']
        renewed=[x for x in source if x.get('type')=='capability_admission' and x['renewed']];assert renewed
        assert all(x['capability']['run_id']==run and x['capability']['worker_instance']==wm['worker_instance'] and x['capability']['pid']==wm['pid'] for x in renewed)
        grant=[x for x in source if x.get('type')=='business_start_authorized'];assert len(grant)==1 and grant[0]['decision_sequence_before']==grant[0]['job_id_before']==0
        cases.append(dict(batch=batch,run_id=run,boot_id=wm['boot_id'],prepare_start_ns=r['prepare_start_ns'],
            all_owned_cleanup_observed_ns=max(x['monotonic_ns'] for x in cleans),manifests=manifests,
            first_healthy_accepted_decision_sequence=accepted[0]['sequence'],first_healthy_accepted_commit_ns=accepted[0]['activation_commit_ns'],
            fresh_native_Worker_instance=wm['worker_instance'],new_gate_zero_business_counters=True,independent_raw_audit_passed=True))
    links=[]
    for old,new in zip(cases,cases[1:]):
        assert old['boot_id']==new['boot_id'] and old['all_owned_cleanup_observed_ns']<new['prepare_start_ns'] and old['run_id']!=new['run_id']
        role_changes={}
        for role,m in old['manifests'].items():
            n=new['manifests'][role];assert m['binary_sha256']==n['binary_sha256'] and m['source_bundle_sha256']==n['source_bundle_sha256']
            assert (m['pid'],m['process_start_ticks'])!=(n['pid'],n['process_start_ticks']) and m['run_id']!=n['run_id']
            role_changes[role]=dict(same_registered_ELF=True,same_source_bundle=True,old_pid=m['pid'],new_pid=n['pid'],old_start_ticks=m['process_start_ticks'],new_start_ticks=n['process_start_ticks'])
        assert old['fresh_native_Worker_instance']!=new['fresh_native_Worker_instance']
        links.append(dict(from_batch=old['batch'],to_batch=new['batch'],old_all_owned_groups_closed_before_new_prepare=True,
            role_changes=role_changes,Worker_instance_changed=True,new_gate_and_healthy_accepted_prefix=True,
            delta_to_new_prepare_ns=new['prepare_start_ns']-old['all_owned_cleanup_observed_ns']))
    before=dict(PINS)
    for p in before:raw(p)
    assert PINS==before
    report=dict(schema='current-cross-run-recovery-evidence-gap/v1',inventory_audit_passed=True,links=links,
        current_same_ELF_fresh_identity_start_after_active39_and_V1_40_observed=True,
        exact_lease41_then_new_run_observed=False,new_actual_runs_for_this_audit=0,
        selected_following_lease_recovery_qualified=False,
        remaining_exact_fact='if final V2 requires recovery specifically after current lease41: one fresh run after its fully closed owned groups, healthy new identity and finite normal resource close',
        no_old_run_revival_already_proven=True,do_not_rerun_active_V1_or_lease_stimulus=True,
        input_sha256_before=before,input_sha256_after=PINS,stage_qualified=False,execute_qualified=False,research_conclusion=False)
    with (D/'postrun/recovery_evidence_gap_v1.json').open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(inventory_audit_passed=True,existing_current_same_ELF_identity_links=len(links),exact_post_lease41_run_observed=False,inputs=len(PINS),new_actual_runs=0)))
if __name__=='__main__':main()
