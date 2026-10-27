#!/usr/bin/env python3
"""Declare exactly one same-ELF normal source run after difference checks."""
import ast
import hashlib
import json
import os
from pathlib import Path
import time

D=Path(__file__).resolve().parent.parent;A=D/'author'
P=D.parent/'scheme_A_post_lease_fresh_recovery_20261020_42'


def pin(path):
    raw=Path(path).read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(p):return json.loads(Path(p).read_bytes())
def create(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')


def main():
    for name in ['normal_source_window_cases_v1.json','independent_window_cases_v1.json']:assert read(D/'verification'/name)['passed']
    assert read(D/'preflight/protection_initial_v1.json')['passed']
    matrix=read(D/'implementation/original_freeze_difference_matrix_v1.json');assert matrix['extra_full_no_output_business_stage_is_not_original_M0b_requirement']
    source=(A/'prepare_pair_wakeup_v1.py').read_text();ast.parse(source)
    assert 'overall_deadline=prepare_start+60_000_000_000' in source and "'measurement_seconds':20" in source
    assert 'observe_normal_source(R,' in source and "return 0 if result['normal20_source_case_completed'] else 2" in source
    assert (A/'pair_wakeup_contract_v1.json').read_bytes()==(P/'author/pair_wakeup_contract_v1.json').read_bytes()
    c=read(A/'pair_wakeup_contract_v1.json');assert len(c)==81 and c['diagnostic_contract_revision']==10 and c['execute_qualified'] is False
    builds=read(A/'build_manifest_current.json');parent=read(P/'author/build_manifest_current.json');assert builds==parent
    before={}
    def capture(path,expected=None):
        path=Path(path);p=pin(path)
        if expected is not None:assert all(p[k]==expected[k] for k in ['bytes','sha256'] if k in expected),str(path)
        if str(path) in before:assert before[str(path)]==p
        before[str(path)]=p
    for role in builds:
        capture(role['binary'],{'sha256':role['binary_sha256']});capture(role['source_bundle']['path'],role['source_bundle'])
        b=read(role['source_bundle']['path'])
        for r in b['files'].values():capture(r['path'],r)
    # Current-role compiler/library inputs are already preserved by42 and old
    # protection; reread exactly the parent lock as an additional affected lock.
    parent_lock=read(P/'preflight/prerun_source_lock_v1.json')
    for path,row in parent_lock['files'].items():capture(path,row)
    for path in sorted(A.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():capture(path)
    for path in [D/'audit_normal_actual_v1.py',D/'audit_normal_source_core_v1.py',D/'audit_business_start_v1.py',D/'audit_fresh_core_v2.py',
      D/'verification/normal_source_window_cases_v1.json',D/'verification/independent_window_cases_v1.json',
      D/'implementation/original_freeze_difference_matrix_v1.json',Path(__file__).resolve(),D/'run_normal_source_v2.py']:capture(path)
    visible=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if b'ROS_DOMAIN_ID=199' in (p/'environ').read_bytes().split(b'\0'):visible.append(int(p.name))
        except OSError:pass
    assert not visible,'DDS199 already has a visible process'
    worker=next(b for b in builds if b['role']=='worker')
    lock={'schema':'current-normal-source20s-source-lock-v1','files':before,'worker_binary_sha256':worker['binary_sha256'],
          'registered_ns':time.monotonic_ns(),'visible_DDS199_processes':visible,'stage_qualified':False}
    lockpath=D/'preflight/prerun_source_lock_v2.json';create(lockpath,lock)
    plan={'schema':'current-normal-source20s-preregistration-v1','verdict':'GO','run_id':'normal_source20s_02','domain':199,
      'run_limit':1,'CXX_builds':0,'same_five_ELFs_as42':True,'reference_speed_m_s':.05,'controlled_case':'C','mode':'positive',
      'contract_sha256':pin(A/'pair_wakeup_contract_v1.json')['sha256'],'diag_revision':10,'nominal_hydro_fields':19,
      'measurement_policy':'first actual moving Job+nonzero known legacy anchor to first complete contiguous >=20s steady+sim source',
      'source_minimum_span_ns':20_000_000_000,'source_max_gap_ns':250_000_000,'planar_speed_limit_m_s':1.2,
      'prepare_budget_ns':20_000_000_000,'monitor_budget_ns':26_000_000_000,'overall_driver_budget_ns':60_000_000_000,
      'close_budget_ns':15_000_000_000,'max_output_bytes':128*1024*1024,'close_policy':'publisher-first',
      'Observer_physical_Writers':0,'legacy_controlled_Publisher':'isolated localhost DDS only, exactly owned nominal Fixture feedback',
      'controlled_fault_injections':False,'all_hooks_zero':True,'V1':'none','V2':'none/0','V3':'none/0','c38_gate':'none',
      'fault_permission_in_existing_diagnostic_contract':True,'regulator_physical_execute_release_enabled':False,
      'all_prepare_and_tail_preserved':True,'do_not_clip_startup_API_gap':True,'halfRMSE_is_not_acceptance_gate':True,
      'runner':pin(D/'run_normal_source_v2.py'),'source_lock':pin(lockpath),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
      'scope':'current selected owned nominal straight normal20s source component, full raw/Source/Witness/Stored and affected normal close',
      'not_qualified':['general_D1','plant','turn_mixed_full_domain','hard_clock_bound','B5_freeze','M0b','M4','F6','P1'],
      'stage_qualified':False,'execute_qualified':False,'research_conclusion':False}
    create(D/'preflight/normal_source_preregistration_v2.json',plan)
    print(json.dumps({'passed':True,'source_pins':len(before),'same_ELFs':5,'run_id':plan['run_id'],'domain':199}))


if __name__=='__main__':main()
