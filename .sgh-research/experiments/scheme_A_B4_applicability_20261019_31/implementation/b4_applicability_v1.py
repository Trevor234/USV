#!/usr/bin/env python3
"""B4 register builder and independent fail-closed register checker. No ROS imports."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time

D=Path(__file__).resolve().parents[1]
W=D.parent
N=W/'p1_execution_architecture_20261005_01/authored_D1_deferred_observation_20261019_v29'
R=N/'runs/deferred_s005_01'
H=Path('/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/source_docs')
CONTRACT_SHA='89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72'
PINS={}
ROLE_INDEX={'publisher':0,'worker':1,'synthetic_source':2,'observer':3,'recorder':4}
GROUPS={
 'model_cost': 'N dt hydro Q R Rd Qf_scale backend_rate_n_s nominal_hash',
 'source_domain': 'odom_age_ns imu_age_ns mixed_skew_ns clock_age_ns clock_pause_confirm_ns odom_sim_lag_ns imu_sim_lag_ns source_future_slack_ns expected_child_frame expected_imu_frame expected_pose_frame input_topics rtf_low rtf_high propagation_semantics source_age_semantics target_sim_slack_ns',
 'scheduler_output': 'T_ns deadline_ns tick_jitter_ns publish_gap_ns publish_budget_ns command_min_n command_max_n rho_n_s hold_ns output_topics publisher_max_n map_scale',
 'resources': 'dds_depth history_capacity log_capacity max_candidate_bytes max_job_bytes max_path_frame_bytes max_path_points max_profile_dims max_profile_label_bytes max_profile_rows candidate_cdr_max_bytes job_cdr_max_bytes resource_budget_scope resource_policy',
 'supervision': 'active_watchdog_ns worker_grace_ns term_grace_ns kill_postcheck_ns shutdown_grace_ns recording_ready_timeout_ns worker_capability_lease_policy worker_capability_receipt_timeout_ns worker_capability_source_freshness_available worker_failure_policy',
 'reference': 'cruise_speed reference_start_offset reference_sampling_policy reference_epoch_policy preparation_retry_policy',
 'activation': 'activation_tolerance activation_sensor_history_capacity activation_state_policy activation_validation_attempts cold_start_policy',
 'identity': 'baseline_input clock diagnostic_contract_revision execute_qualified fault_injection_enabled parameters_are_diagnostic_only pending_final_calibration qualification schema',
}
GROUP_OF={k:g for g,s in GROUPS.items() for k in s.split()}
IMPLICIT={
 'reference_pair_retry':('preparation_retry_policy','reference_pair_retry','pair completion retries are not covered by zero actual retries'),
 'deferred_observation':('activation_state_policy','materialize_activation_trace','immutable capture materialized after final commit/publish return; no extra semantic validation in that later trace'),
 'worker_terminal':('worker_failure_policy','terminal_numerical_failure','same run does not restart after invalid numerical result'),
 'slope_and_hold':('hold_ns','last_accepted','hold lifespan is not refreshed by republishing; ramp uses known per-side anchors'),
 'partial_publish':('publish_budget_ns','publish_success','partial API results cannot be rolled back; failed side becomes unknown'),
 'close_and_recovery':('shutdown_grace_ns','shutdown','normal close does not prove fault close or actual zero thrust'),
}


def need(v,why):
    if not v:raise ValueError(why)


def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def sha(b):return hashlib.sha256(b).hexdigest()


def read(p):
    p=Path(p);b=p.read_bytes();v=dict(bytes=len(b),sha256=sha(b),resolved_path=str(p.resolve()))
    need(str(p) not in PINS or PINS[str(p)]==v,'changed_input:'+str(p));PINS[str(p)]=v
    return b


def load(p):
    def pairs(rows):
        d={}
        for k,v in rows:need(k not in d,'duplicate_JSON_key:'+k);d[k]=v
        return d
    return json.loads(read(p),object_pairs_hook=pairs)


def write(rel,data):
    with (D/rel).open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def typed_parameters(rows):
    result={}
    for key,row in rows.items():
        t=row['type'];v=row['value']
        if t==3:
            need(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v),'invalid_double')
            cv=struct.pack('>d',v).hex()
        elif t==8:
            need(all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v),'invalid_double_array')
            cv=[struct.pack('>d',x).hex() for x in v]
        else:cv=v
        need(cv==row['canonical_value'],'typed_value_mismatch:'+key)
        result[key]={'type':t,'canonical_value':cv}
    return sha(canonical(result))


def context():
    cb=read(N/'pair_wakeup_contract_v1.json');need(sha(cb)==CONTRACT_SHA,'wrong_current_contract')
    c=load(N/'pair_wakeup_contract_v1.json');need(set(c)==set(GROUP_OF),'field_group_coverage')
    old=load(H/'P1_M0b_B4_参数来源与冻结决策_2026-10-09.json')
    builds=load(N/'build_manifest_current.json');roles={};sources={}
    for role,idx in ROLE_INDEX.items():
        m=load(R/role/'owned_manifest.json');b=builds[idx]
        need(m['contract_sha256']==CONTRACT_SHA and not m['execute_qualified'],'role_contract_or_qualification:'+role)
        need(m['effective_parameters_immutable'] and m['effective_parameters_digest_encoding']=='p1-typed-ieee754-v1','role_parameters_not_immutable')
        need(typed_parameters(m['effective_parameters'])==m['effective_parameters_sha256'],'role_typed_digest:'+role)
        need(m['binary_sha256']==b['binary_sha256']==sha(read(b['binary'])),'role_binary:'+role)
        sb=load(b['source_bundle']['path']);need(sha(read(b['source_bundle']['path']))==m['source_bundle_sha256']==b['source_bundle']['sha256'],'role_source_bundle:'+role)
        for rel,pin in sb['files'].items():
            path=Path(pin['path']);need(sha(read(path))==pin['sha256'],'source_bundle_member:'+str(path))
            if path.suffix in ['.hpp','.cpp','.h','.c'] and 'test' not in rel:
                sources[str(path)]=dict(role=role,text=read(path).decode())
        if role in ['observer','worker']:need(m['contract_configuration']==c,'actual_contract_configuration:'+role)
        if role=='synthetic_source':need(m['contract_hydro']==c['hydro'] and not m['plant_connected'],'actual_nominal_source')
        roles[role]=dict(manifest=str(R/role/'owned_manifest.json'),manifest_sha256=sha(read(R/role/'owned_manifest.json')),
                         binary=b['binary'],binary_sha256=m['binary_sha256'],source_bundle=b['source_bundle']['path'],
                         source_bundle_sha256=m['source_bundle_sha256'],effective_parameters_sha256=m['effective_parameters_sha256'],
                         effective_parameters=m['effective_parameters'],historical_endpoint_evidence_only=True)
    inputs=load(R/'inputs.json')
    driver=N/inputs['driver_tool_name'];need(sha(read(driver))==inputs['tool_sha256'][inputs['driver_tool_name']],'actual_driver_tool')
    sources[str(driver)]=dict(role='driver',text=read(driver).decode())
    cp=roles['publisher']['effective_parameters']
    mapping={'N':'horizon','dt':'dynamic.dt','Q':'dynamic.Q','R':'dynamic.R','Rd':'dynamic.Rd','Qf_scale':'dynamic.Qf_scale',
             'backend_rate_n_s':'dynamic.dT_max','command_min_n':'dynamic.T_min','command_max_n':'dynamic.T_max',
             'cruise_speed':'cruise_speed','publisher_max_n':'vrx_thrust_cmd_max',
             'map_scale':'vrx_thrust_scale'}
    for k,param in mapping.items():need(cp[param]['value']==c[k],'publisher_configuration:'+k)
    for key,value in c['hydro'].items():need(cp['vehicle.'+key]['value']==value,'publisher_hydro:'+key)
    need(inputs['reference_speed_m_s']==.05 and cp['cruise_speed']['value']==.6,'reference_speed_semantics')
    need(c['reference_start_offset']==0 and cp['reference_start_offset']['value']==2,'distinct_reference_offsets')
    header=json.loads(read(R/'publisher/controlled_source.jsonl').split(b'\n',1)[0])
    need(header['mode']=='C' and header['autonomous_solver_invoked'] is False,'controlled_C_not_autonomous')
    need(any('controlled_cycle_();return;' in row['text'] for row in sources.values()),'actual_autonomous_path_bypass')
    report=load(W/'scheme_A_deferred_observation_20261019_29/runs/s005_01/check_result.json')
    need(not report['passed'] and report['window']['accepted']==101 and report['window']['attempts']==101,'preserved_case_scope')
    return c,old,roles,sources,mapping


def refs(sources,key,limit=16):
    found=[]
    for path,row in sorted(sources.items()):
        for i,line in enumerate(row['text'].splitlines(),1):
            # Baked JSON and contract specs are validation evidence, not uses.
            if 'R"P1BASE' in line or len(line)>5000:continue
            if '"'+key+'"' in line or "'"+key+"'" in line:
                kind='direct_config_access' if re.search(r'(?:\.at|\.value|\.get)\(["\']'+re.escape(key)+r'["\']',line) else 'literal_reference_review_required'
                found.append(dict(path=path,line=i,line_sha256=sha(line.encode()),role=row['role'],kind=kind))
    return found[:limit]


def verify(reg,ctx):
    c,old,roles,sources,mapping=ctx
    need(reg['schema']=='B4-current-applicability/v1','schema')
    need(reg['contract_sha256']==CONTRACT_SHA,'contract_pin')
    need(not reg['stage_qualified'] and not reg['execute_qualified'] and not reg['research_conclusion'],'false_qualification_required')
    need(canonical(reg['actual_roles'])==canonical(roles),'actual_role_binding')
    fields=reg['fields'];need(len(fields)==81 and len({r['key'] for r in fields})==81 and {r['key'] for r in fields}==set(c),'unique_complete_fields')
    for row in fields:
        k=row['key'];need(canonical(row['value'])==canonical(c[k]) and row['group']==GROUP_OF[k],'field_value_or_group:'+k)
        need(row['consumer_references']==refs(sources,k),'consumer_refs:'+k)
        need(row['applicability']=='exact_diag10_nominal_localhost_only' and not row['freeze_condition_satisfied'],'unsupported_freeze_claim:'+k)
        need(row['publisher_effective_parameter']==mapping.get(k),'publisher_mapping:'+k)
    need(reg['pending_original_groups']==c['pending_final_calibration'],'pending_groups_removed')
    need(len(reg['hydro'])==19 and canonical({r['key']:r['value'] for r in reg['hydro']})==canonical(c['hydro']),'hydro_coverage')
    need(reg['policies']==policy_rows(sources),'policy_semantics_or_refs')
    need(reg['mode_scoped_difference']=={'field':'reference_start_offset','observer_contract_value':0,'publisher_configured_value':2,'publisher_autonomous_solver_invoked':False,'scope':'controlled_C only; no qualification for autonomous or M4'},'scoped_difference_erased')
    need(reg['reference_speed_semantics']=={'publisher_configured_cruise':.6,'actual_fixture_reference_speed':.05,'these_are_distinct':True},'reference_domain')
    return dict(passed=True,field_count=81,hydro_count=19,actual_roles=5,
                direct_field_references=sum(any(x['kind']=='direct_config_access' for x in r['consumer_references']) for r in fields),
                fields_without_literal_consumer_reference=[r['key'] for r in fields if not r['consumer_references']],
                typed_parameter_digests_verified=5,stage_qualified=False,execute_qualified=False,research_conclusion=False)


def policy_rows(sources):
    return [dict(name=name,contract_field=field,semantic=semantic,
                 references=[dict(path=p,line=i,line_sha256=sha(s.encode()),role=row['role'])
                             for p,row in sorted(sources.items()) for i,s in enumerate(row['text'].splitlines(),1)
                             if token in s and len(s)<5000][:8],
                 scope='engineering mechanism; not physical safety or final-version fault qualification',
                 final_version_confirmed=False) for name,(field,token,semantic) in IMPLICIT.items()]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['build','check','targeted-checks']);ap.add_argument('--register',type=Path);ap.add_argument('--expected-sha256');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    start=time.monotonic();ctx=context();c,old,roles,sources,mapping=ctx
    if a.mode=='build':
        oldfields={r['key']:r for r in old['fields']}
        fields=[]
        for key,value in c.items():
            original=oldfields.get(key)
            fields.append(dict(key=key,value=value,group=GROUP_OF[key],consumer_references=refs(sources,key),
                publisher_effective_parameter=mapping.get(key),applicability='exact_diag10_nominal_localhost_only',freeze_condition_satisfied=False,
                historical_register_entry_exists=original is not None,
                original_selection_status=None if original is None else original.get('selection_status'),
                original_freeze_condition=None if original is None else original.get('original_freeze_condition'),
                delta_kind='new_vs_formal77' if original is None else 'same_value' if original.get('current_value')==value else 'value_or_profile_changed',
                reference_kind_note='literal matches may be validation-only; no automatic runtime-domain qualification'))
        reg=dict(schema='B4-current-applicability/v1',contract=str(N/'pair_wakeup_contract_v1.json'),contract_sha256=CONTRACT_SHA,
                 fields=fields,hydro=[dict(key=k,value=v,publisher_parameter='vehicle.'+k,global_parameter_layout='existing19',freeze_condition_satisfied=False) for k,v in c['hydro'].items()],
                 actual_roles=roles,policies=policy_rows(sources),pending_original_groups=c['pending_final_calibration'],
                 reference_speed_semantics={'publisher_configured_cruise':.6,'actual_fixture_reference_speed':.05,'these_are_distinct':True},
                 mode_scoped_difference={'field':'reference_start_offset','observer_contract_value':0,'publisher_configured_value':2,'publisher_autonomous_solver_invoked':False,'scope':'controlled_C only; no qualification for autonomous or M4'},
                 stage_qualified=False,execute_qualified=False,research_conclusion=False)
        result=verify(reg,ctx)
        write('implementation/current_B4_applicability_v1.json',reg)
    else:
        need(a.register and re.fullmatch('[0-9a-f]{64}',a.expected_sha256 or ''),'explicit_register_and_expected_SHA_required')
        need(sha(read(a.register))==a.expected_sha256,'register_SHA')
        reg=load(a.register);result=verify(reg,ctx)
        if a.mode=='targeted-checks':
            cases=[]
            mutations=[('missing_field',lambda r:r['fields'].pop()),('wrong_value',lambda r:r['fields'][0].update(value=-1)),
                       ('duplicate_field',lambda r:r['fields'].append(copy.deepcopy(r['fields'][0]))),
                       ('wrong_role_digest',lambda r:r['actual_roles']['worker'].update(effective_parameters_sha256='0'*64)),
                       ('cleared_pending',lambda r:r['pending_original_groups'].clear()),
                       ('fake_freeze',lambda r:r['fields'][0].update(freeze_condition_satisfied=True)),
                       ('fake_stage',lambda r:r.update(stage_qualified=True)),
                       ('wrong_consumer_reference',lambda r:r['fields'][0]['consumer_references'].append(dict(path='/tmp/fake',line=1))),
                       ('cruise_equals_actual',lambda r:r['reference_speed_semantics'].update(actual_fixture_reference_speed=.6)),
                       ('removed_hydro',lambda r:r['hydro'].pop()),
                       ('erased_mode_difference',lambda r:r['mode_scoped_difference'].update(publisher_configured_value=0)),
                       ('bool_as_numeric_one',lambda r:next(x for x in r['fields'] if x['key']=='map_scale').update(value=True)),
                       ('bool_as_hydro_zero',lambda r:next(x for x in r['hydro'] if x['key']=='Nv').update(value=False))]
            for name,mutate in mutations:
                candidate=copy.deepcopy(reg);mutate(candidate)
                try:verify(candidate,ctx)
                except ValueError as e:cases.append(dict(name=name,rejected=True,reason=str(e)))
                else:raise ValueError('mutation_not_rejected:'+name)
            result['targeted_negative_cases']=cases
    before=copy.deepcopy(PINS)
    for path in before:read(path)
    need(before==PINS,'inputs_changed')
    result.update(schema='B4-applicability-check/v1',mode=a.mode,elapsed_seconds=time.monotonic()-start,
                  input_pins=before,all_inputs_unchanged=True,new_ROS_run=False,new_build=False,
                  only_register_integrity_checked_not_B4_phase=True)
    need(result['elapsed_seconds']<=600,'implementation_run_budget')
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['input_pins','targeted_negative_cases']},ensure_ascii=False))


if __name__=='__main__':main()
