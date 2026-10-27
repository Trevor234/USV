#!/usr/bin/env python3
"""Create-only formal profile derivation. Existing v2/v3 recognition is retained."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
P = D.parent / 'scheme_A_B5_contract_parity_20261020_44/implementation'
I = D / 'implementation'
TARGET = 'P1_owned_nominal_execution_20261020_01'


def emit(path, data):
    with path.open('xb') as f:
        f.write(data)


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode()


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    spec = json.loads((P / 'current_contract_spec_v1.json').read_bytes())
    assert pin(P / 'current_contract_spec_v1.json')['sha256'] == '317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798'
    overrides = {
        'baseline_input': 'F5_NOMINAL_SOURCE_OWNED_REGULATOR_20261020_01',
        'preparation_retry_policy': 'owned_reference_pair_completion_before_business_v1',
        'propagation_semantics': 'owned-regulator per-side successful API publish-start history from accepted odom stamp, mixed r retained with separate IMU stamp; future held current command; RK4 nominal point prediction',
    }
    ledger = json.loads((D.parent / 'scheme_A_current_normal_source_20261020_46/implementation/B5_candidate_evidence_ledger_v1.json').read_bytes())
    policy = {
        'schema': 'P1-owned-execution-profile-policy/v1', 'profile_id': TARGET,
        'contract_schema': 'p1-execution-contract-v3', 'contract_fields': 84,
        'physical_execute_release_enabled': False,
        'qualification_scope': 'M0b engineering values and policy freeze before independent M4; no runtime or plant release',
        'contract_overrides_from_diagnostic': overrides,
        'owner': {
            'role': 'p1_owned_execute_regulator', 'sole_job_owner': True,
            'sole_output_owner': True, 'output_writer_count': 2,
            'worker_physical_writers': 0, 'fixture_physical_writers': 0,
            'recorder_physical_writers': 0, 'legacy_output_writers': 0,
            'old_output_owner_exit_required_before_new_run': True,
            'callback_or_worker_output_forbidden': True,
            'run_boot_contract_manifest_and_GID_binding_required': True,
        },
        'source': {
            'asset_basis': 'F5 fixed nominal 19-hydro, original path/profile frames/topics, scheme=B dynamic NMPC',
            'current_calibration': 'batch46 normal_source20s_03; Observer39 Worker35 Publisher18 Fixture19 RecorderC3.4',
            'M4_output_history_owner': 'new regulator only; legacy Applied cannot establish new owner authority',
            'prepare_requires': ['owned identity/graph/GIDs', 'recorder ready', 'worker valid capability callback lease', 'matching path/profile content', 'fresh odom/optional mixed IMU and clock'],
            'reference': 'first successful job submit completion target sim epoch; first-target task-time profile; offset 0',
            'model': 'nominal RK4 point; retained IMU stamp for mixed r',
            'no_new_full_no_output_business_stage': True,
        },
        'bootstrap': {
            'id': 'owned_unknown_then_actual_zero_pair_fixed_tick_v1',
            'initial_anchor_known': [False, False],
            'initial_request_n': [0, 0],
            'initial_numeric_zero_has_no_authority': True,
            'first_pair_start_deadline_from_prepare_grant_ns': 200000000,
            'tick_origin': 'prepare grant monotonic; no one-second quiet lead',
            'cadence_ns': 200000000, 'gap_ns': 240000000,
            'jitter_ns': 20000000, 'pair_span_ns': 5000000,
            'waiting_inputs_or_first_candidate': 'publish zero requests on each absolute tick; no job until both actual zero APIs succeeded and current ready/source gates pass',
            'rho_available_on_first_pair': False,
            'first_success_anchor': 'each side actual API publish-start only',
            'pre_first_API_and_cross_owner_interval': 'unknown; no rate or plant-zero proof',
            'partial_first_pair': 'successful side irreversible; failed side unknown; terminal business stop, bounded close',
            'late_tick': 'skip catch-up bursts; latch timing failure and stop business, continue bounded fallback/close',
            'full_API_stream_includes': ['bootstrap', 'waiting', 'business', 'fallback', 'shutdown'],
        },
        'output': {
            'per_side_anchor': 'update only after returned API, at its actual publish-start; failure marks only that side unknown',
            'both_calls_attempted': True, 'unknown_side_request': 'zero only; rho unavailable',
            'rho_n_s': 80, 'mapped_bounds_n': [-25, 25], 'map_scale': 1,
            'hold_ns': 600000000, 'hold_equality_allowed': True,
            'hold_origin': 'last accepted candidate activation; ordinary republish never renews it',
            'invalid_bypasses_hold': True, 'ramp': 'known side toward zero with rho times its own actual elapsed interval',
            'shutdown_grace_ns': 2500000000,
            'shutdown_outcomes_separate': ['zero requested', 'each API returned', 'owned process exit', 'plant receipt unknown'],
            'timing_failure_after_API': 'successful calls remain in history; never rollback or relabel them',
        },
        'domain': {
            'selected_calibration_domain': 'owned local nominal straight reference 0.05 m/s, no obstacles, near 1:1 sim clock',
            'observed_planar_speed_m_s': [0.011050352621275452, 0.06214294029836156],
            'observed_source_duration_ns': 20002935074,
            'observed_dynamic_jobs': 101, 'observed_mixed_jobs': 2,
            'engineering_source_limits': {'planar_speed_m_s_max': 1.2, 'adjacent_odom_gap_ns_max': 250000000},
            'full_1_2m_s_domain_proven': False, 'general_turn_or_mixed_proven': False,
            'plant_or_6DOF_proven': False, 'WCET_proven': False,
            'full_startup_gap240ms_in_calibration_passed': False,
            'current_full_startup_gap_max_ns': 1537738316,
        },
        'assumptions': ledger['selected_engineering_assumptions'],
        'M4_forward_obligations': ledger['M4_forward_confirmation_stays_separate'],
        'mode_matrix': {
            'diagnostic_v2': ['no_output', 'shadow'],
            'formal_pre_freeze_v3': ['no_output'],
            'formal_frozen_v3_shape': ['no_output', 'execute'],
            'target_entry_preflight': ['no_output'],
            'physical_execute_release': [],
            'old_Observer39_entry': ['diagnostic_v2+shadow only'],
            'formal_prepare45_entry': ['old formal pre-freeze v3+no_output prepare-only'],
        },
    }
    policy_raw = encoded(policy)
    emit(I / 'owned_execution_policy_v1.json', policy_raw)
    spec['formal_profiles'] = {spec['profile_id']: {}, TARGET: overrides}
    spec['target_profile_id'] = TARGET
    spec['target_policy_sha256'] = hashlib.sha256(policy_raw).hexdigest()
    spec['scope'] = 'preserved legacy diag10/formal profile plus owned nominal formal profile; same v3, no physical release'
    emit(I / 'current_contract_spec_v1.json', encoded(spec))
    emit(I / 'current_diag_contract_v1.json', (P / 'current_diag_contract_v1.json').read_bytes())
    emit(I / 'current_pre_freeze_contract_v1.json', (P / 'current_pre_freeze_contract_v1.json').read_bytes())
    target = json.loads((P / 'current_pre_freeze_contract_v1.json').read_bytes())
    target.update(overrides, supported_parameter_profile=TARGET)
    emit(I / 'owned_pre_freeze_contract_v1.json', encoded(target))
    for name in ['p1_resources.hpp.in', 'p1_resource_contract.py.in']:
        emit(I / 'templates' / name, (P / 'templates' / name).read_bytes())
    py = (P / 'templates/p1_full_contract.py.in').read_text()
    py = replace_once(py, '    for key, value in _BASELINE.items():\n',
        '    selected = dict(_BASELINE)\n    if formal:\n        profile = contract["supported_parameter_profile"]\n        if type(profile) is not str or profile not in SPEC["formal_profiles"]:\n            raise ContractError("unsupported parameter profile")\n        selected.update(SPEC["formal_profiles"][profile])\n    for key, value in selected.items():\n')
    py = replace_once(py, '    _match(contract["supported_parameter_profile"], SPEC["profile_id"],\n           "supported_parameter_profile")\n', '')
    emit(I / 'templates/p1_full_contract.py.in', py.encode())
    cpp = (P / 'templates/p1_full_contract.hpp.in').read_text()
    cpp = replace_once(cpp, 'inline const nlohmann::json & candidate_baseline() {',
        'inline constexpr const char * target_parameter_profile = "@TARGET_PROFILE_ID@";\ninline constexpr const char * target_policy_sha256 = "@POLICY_SHA256@";\ninline const nlohmann::json & formal_profile_overrides() {\n  static const auto value=nlohmann::json::parse(R"P1PROFILES(@FORMAL_PROFILES_JSON@)P1PROFILES");return value;\n}\ninline const nlohmann::json & candidate_baseline() {')
    cpp = replace_once(cpp, '  for(auto it=base.begin();it!=base.end();++it) {\n',
        '  auto selected=base;\n  if(formal){\n    contract_require(c.at("supported_parameter_profile").is_string(),"profile string required");\n    const auto profile=c.at("supported_parameter_profile").get<std::string>();\n    const auto & profiles=formal_profile_overrides();\n    contract_require(profiles.contains(profile),"unsupported parameter profile");\n    selected.update(profiles.at(profile));\n  }\n  for(auto it=selected.begin();it!=selected.end();++it) {\n')
    cpp = replace_once(cpp, '  contract_require(c.at("supported_parameter_profile").is_string() && c.at("supported_parameter_profile")==contract_parameter_profile,"unsupported parameter profile");\n', '')
    emit(I / 'templates/p1_full_contract.hpp.in', cpp.encode())
    generator = (P / 'generate_contract_v1.py').read_text()
    generator = replace_once(generator, "        'PROFILE_ID': spec['profile_id'],\n", "        'PROFILE_ID': spec['profile_id'],\n        'TARGET_PROFILE_ID': spec['target_profile_id'],\n        'POLICY_SHA256': spec['target_policy_sha256'],\n        'FORMAL_PROFILES_JSON': json.dumps(spec['formal_profiles'], separators=(',', ':'), sort_keys=True),\n")
    emit(I / 'generate_contract_v1.py', generator.encode())
    probe = (P / 'native/contract_probe_v2.cpp').read_text()
    probe = replace_once(probe, '    result["profile_id"] = p1::contract_parameter_profile;', '    result["profile_id"] = p1::contract_parameter_profile;\n    result["target_profile_id"] = p1::target_parameter_profile;')
    emit(I / 'native/contract_probe_v1.cpp', probe.encode())
    for name in ['p1_admission.hpp', 'publication_result_v1.hpp']:
        parent = D.parent / 'scheme_A_owned_business_start_20261020_39/author/observer/src/shadow' / name
        emit(I / 'native' / name, parent.read_bytes())
    delta = {k: {'old': json.loads((P / 'current_pre_freeze_contract_v1.json').read_bytes())[k], 'target': target[k]} for k in target if target[k] != json.loads((P / 'current_pre_freeze_contract_v1.json').read_bytes())[k]}
    emit(I / 'profile_field_diff_v1.json', encoded({
        'schema': 'P1-formal-profile-field-diff/v1', 'field_count': 84,
        'changed_fields': delta, 'numeric_parameters_changed': False,
        'schema_changed': False, 'physical_release': False,
        'source_policy_sha256': spec['target_policy_sha256'],
        'parent_inputs': {str(p): pin(p) for p in [P / 'current_contract_spec_v1.json', P / 'current_pre_freeze_contract_v1.json', Path(__file__).resolve()]},
    }))
    print(json.dumps({'profile': TARGET, 'field_diff': list(delta), 'numeric_changes': 0}))


if __name__ == '__main__':
    main()
