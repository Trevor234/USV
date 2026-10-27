#!/usr/bin/env python3
"""Submit a non-circular, create-only engineering contract freeze.

Index pins a frozen-state template with an empty evidence marker. The exact
index digest is then inserted into the final v3 contract. A separately pinned
contract digest closes the binding without any self-hash or invented digest.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
B = D.parent
F = D / 'freeze'
sys.path.insert(0, str(D / 'implementation/python'))
import freeze_binding_v1 as binding
import p1_full_contract as full


def raw(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def emit(p, value):
    with p.open('xb') as f:
        f.write(value if type(value) is bytes else raw(value))


def load(p):
    return binding.parse(p.read_bytes())


def main():
    conditions = load(F / 'freeze_conditions_v1.json')
    assert conditions['passed'] and all(conditions['checks'].values())
    frozen = load(D / 'implementation/owned_pre_freeze_contract_v1.json')
    frozen.update(qualification='execution_frozen', execute_qualified=True,
                  parameters_are_diagnostic_only=False, pending_final_calibration=[],
                  freeze_evidence_sha256='')
    template = F / 'contract_template_without_evidence_marker_v1.json'
    emit(template, binding.template_bytes(frozen))
    old46 = B / 'scheme_A_current_normal_source_20261020_46'
    source_bundles = load(old46 / 'author_r2/source_bundles_current.json')
    role_assets = []
    for directory in ['publisher', 'worker', 'observer', 'synthetic_source', 'recorder']:
        p = old46 / 'author_r2/runs/normal_source20s_03' / directory / 'owned_manifest.json'
        manifest = load(p)
        role = manifest['role']
        source_key = 'fixture' if directory == 'synthetic_source' else directory
        role_assets.append({'role': role, 'manifest_path': str(p), 'exe': manifest['exe'],
                            'binary_sha256': manifest['binary_sha256'], 'source_bundle': source_bundles[source_key],
                            'scope': 'calibration role under old diagnostic/shadow entry, not new execute owner qualification'})
    assets = {'schema': 'P1-M0b-calibration-and-policy-assets/v1', 'calibration_roles': role_assets,
              'nominal_hash': frozen['nominal_hash'], 'calibration_contract_sha256': '89caaaf36783463a1e1d789bda41f7f90dc398981ddb4b3b8cd6037114333f72',
              'formal_prepare_contract_sha256': '1faedd4bbf7338ffbd3bc1f9b049285e58d7c3605816d416ac2b83fbfd5365fb',
              'selected_new_policy_entry_source': str(D / 'implementation/native/owned_execution_entry_v2.hpp'),
              'selected_new_policy_entry_probe_binary': str(D / 'build/components_attempt02/entry_probe'),
              'selected_profile_validator_probe_binary': str(D / 'build/components_attempt01/contract_probe'),
              'new_execute_runtime_binary_qualified': False,
              'M4_derived_runtime_binding': 'future run manifest must bind this frozen index/contract, exact new source/bin/config and owned graph/GIDs; no backdating calibration role identity',
              'old_pre_freeze_and_failed_runs_retained': True, 'physical_execute_release_enabled': False}
    emit(F / 'calibration_and_policy_assets_v1.json', assets)
    files = {}
    deadline = time.monotonic() + binding.MAX_SECONDS

    def add(path, expected=None, roles=('evidence',)):
        original = Path(path)
        canonical = original.resolve(strict=True)
        key = str(canonical)
        if expected is not None and type(expected) is str:
            expected = {'sha256': expected}
        if key in files:
            current = files[key]
            if expected:
                assert all(current[k] == expected[k] for k in ['sha256', 'bytes'] if k in expected), key
            current['roles'] = sorted(set(current['roles']) | set(roles))
            return
        got = binding.stable_read(canonical, binding.MAX_FILE_BYTES, deadline=deadline)
        if expected:
            assert all(got[k] == expected[k] for k in ['sha256', 'bytes'] if k in expected), key
        labels = set(roles)
        if canonical.suffix in {'.hpp', '.h', '.cpp', '.c', '.in'}:labels.add('source')
        if canonical.suffix in {'.json', '.yaml', '.yml'}:labels.add('config')
        if canonical.suffix in {'.py', '.cmake'} or canonical.name == 'CMakeLists.txt':labels.add('tool')
        if canonical.suffix == '.so' or 'usv_model_dynamic' in key or 'acados_solver' in key:labels.add('model')
        with canonical.open('rb') as f:
            if f.read(4) == b'\x7fELF':labels.add('binary')
        files[key] = {'path': key, **got, 'roles': sorted(labels)}

    def references(value):
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is str and key.startswith('/'):
                    if type(item) is dict and type(item.get('sha256')) is str:
                        add(key, item)
                    elif binding.hash_shape(item):
                        add(key, item)
                references(item)
            if type(value.get('path')) is str and value['path'].startswith('/') and binding.hash_shape(value.get('sha256')):
                add(value['path'], value)
        elif type(value) is list:
            for item in value:references(item)

    seeds = [old46 / 'postrun/final_input_evidence_recheck_v1.json',
             old46 / 'postrun/current_normal_source20s_audit_v1.json',
             old46 / 'implementation/B5_candidate_evidence_ledger_v1.json',
             B / 'scheme_A_B4_finite_scope_review_20261020_43/postrun/review_evidence_audit_v1.json',
             B / 'scheme_A_B5_contract_parity_20261020_44/postrun/component_evidence_audit_v1.json',
             B / 'scheme_A_owned_formal_prepare_20261020_45/postrun/final_input_lock_recheck_v1.json',
             B / 'scheme_A_owned_formal_prepare_20261020_45/postrun/actual_prepare_audit_v2.json',
             B / 'scheme_A_V2_watchdog_lease_20261019_35/build/v2_worker_attempt01/build_result_v1.json',
             old46 / 'author_r2/source_bundles_current.json',
             old46 / 'author_r2/build_manifest_current.json']
    for p in seeds:
        add(p);references(load(p))
    for p in D.rglob('*'):
        if p.is_file() and p.parts[len(D.parts)] in {'implementation', 'build', 'verification', 'freeze'}:
            add(p, roles=('source',) if 'implementation' in p.relative_to(D).parts else ('evidence',))
    for p in D.glob('*.py'):add(p, roles=('tool',))
    for p in [D / 'preflight/component_input_lock_v1.json', D / 'preflight/preflight_reflection_v1.md', D / 'preflight/workspace_initial_v1.json']:
        add(p)
    handoff = B.parent / 'handoffs/scheme_A_20261010_01'
    for p in [handoff / 'handoff_manifest.json', handoff / '方案A_UbuntuCodex交接与全面推进计划_2026-10-10.md', handoff / 'source_docs/P1_时间与候选接纳契约及独立执行架构_最小实施计划_2026-10-05.md']:
        add(p, roles=('evidence',))
    special = {'owned_execution_policy_v1.json': 'policy', 'M4_fault_matrix_v1.json': 'fault_matrix',
               'parameter_sources_v1.json': 'parameter_sources', 'freeze_conditions_v1.json': 'freeze_conditions',
               template.name: 'contract_template'}
    for name, role in special.items():add(F / name, roles=(role,))
    ledger = load(old46 / 'implementation/B5_candidate_evidence_ledger_v1.json')
    index = {'schema': 'P1-M0b-engineering-freeze-index/v1', 'profile_id': full.SPEC['target_profile_id'],
             'qualification_scope': 'original M0b selected finite engineering values/policy; independent M4 execution confirmation remains unqualified',
             'physical_execute_release_enabled': False,
             'contract_template_path': str(template), 'contract_template_sha256': files[str(template)]['sha256'],
             'policy_path': str(F / 'owned_execution_policy_v1.json'), 'policy_sha256': full.SPEC['target_policy_sha256'],
             'spec_sha256': full.SPEC_SHA256, 'parameter_sources_path': str(F / 'parameter_sources_v1.json'),
             'fault_matrix_path': str(F / 'M4_fault_matrix_v1.json'), 'fault_matrix_sha256': files[str(F / 'M4_fault_matrix_v1.json')]['sha256'],
             'conditions_path': str(F / 'freeze_conditions_v1.json'),
             'evidence_ledger_path': str(old46 / 'implementation/B5_candidate_evidence_ledger_v1.json'),
             'artifacts': [files[k] for k in sorted(files)], 'artifact_count': len(files),
             'total_bytes': sum(v['bytes'] for v in files.values()),
             'M4_forward_obligations': ledger['M4_forward_confirmation_stays_separate'],
             'limitations': ['no current new-regulator actual output/ownership proof', 'no plant/6DOF/control-performance or GP data qualification', 'no general 1.2m/s/turning/mixed/WCET claim', 'calibration full startup gap240ms=false remains; new predeclared bootstrap must be confirmed in M4', 'offline context/API event tests do not prove live graph or physical publication', 'future derived M4 entry must re-pin exact runtime assets and old-owner absence; new policy/threshold semantics require a new preserved freeze version'],
             'stage_status': {'B5_contract_freeze': True, 'M0b_selected_engineering_freeze': True, 'M4': False, 'F6': False, 'P1': False, 'plant': False},
             'committed_before_M4': True}
    assert len(files) <= binding.MAX_FILES and index['total_bytes'] <= binding.MAX_TOTAL_BYTES
    index_raw = raw(index)
    assert len(index_raw) <= binding.MAX_INDEX_BYTES
    index_sha = hashlib.sha256(index_raw).hexdigest()
    index_path = F / 'freeze_index_v1.json'
    emit(index_path, index_raw)
    frozen['freeze_evidence_sha256'] = index_sha
    full.validate_fields(frozen)
    contract_path = F / 'p1_execution_contract_v1.json'
    contract_raw = raw(frozen)
    emit(contract_path, contract_raw)
    contract_sha = hashlib.sha256(contract_raw).hexdigest()
    record = {'schema': 'P1-M0b-engineering-freeze-submit/v1', 'freeze_index_path': str(index_path),
              'freeze_index_sha256': index_sha, 'contract_path': str(contract_path), 'contract_sha256': contract_sha,
              'template_sha256': index['contract_template_sha256'], 'spec_sha256': full.SPEC_SHA256,
              'policy_sha256': full.SPEC['target_policy_sha256'], 'artifact_count': len(files), 'artifact_bytes': index['total_bytes'],
              'submission_is_not_independent_verification': True, 'physical_execute_release_enabled': False,
              'M4_qualified': False, 'P1_qualified': False}
    emit(F / 'freeze_submission_v1.json', record)
    print(json.dumps({k: record[k] for k in ['freeze_index_sha256', 'contract_sha256', 'artifact_count', 'artifact_bytes']}))


if __name__ == '__main__':
    main()
