#!/usr/bin/env python3
"""Compare explicit source ranges and pin the exact historical evidence used."""
from pathlib import Path
import difflib
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
CURRENT = ROOT / 'implementation/current_author'
INPUTS = {}


def pin_bytes(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = pin_bytes(data)
    return data


def load(path):
    return json.loads(raw(path))


def create(relative, value):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


def masked(text):
    # Preserve positions while ignoring braces in comments and quoted literals.
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27',
                  lambda m: ' ' * len(m.group()), text)


def body(text, name):
    match = re.search(r'^  (?:static )?[\w:<>,*&]+[ \t]+' + re.escape(name) + r'\(', text, re.M)
    if not match:
        return None
    mask = masked(text)
    start = mask.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (mask[end] == '{') - (mask[end] == '}')
        end += 1
    return {'text': text[start:end], 'start_line': text.count('\n', 0, start) + 1,
            'end_line': text.count('\n', 0, end) + 1}


def fragment(text, start, end):
    assert text.count(start) == 1, start
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def method_report(old, new, names):
    rows = {}
    for name in names:
        x, y = body(old, name), body(new, name)
        rows[name] = {'found_both': bool(x and y),
                      'byte_identical': bool(x and y and x['text'] == y['text']),
                      'historical': {**pin_bytes(x['text'].encode()), 'line': x['start_line']} if x else None,
                      'current': {**pin_bytes(y['text'].encode()), 'line': y['start_line']} if y else None}
    return rows


reg_path = 'observer/src/shadow/regulator_owned_execute.cpp'
worker_path = 'worker/solver_worker_m4.cpp'
bundle66 = load(BASE / 'scheme_A_W2_owned_takeover_20261023_66/evidence/freeze_and_build/source_bundle.json')
current_reg = raw(CURRENT / reg_path).decode()
current_worker = raw(CURRENT / worker_path).decode()
comparisons = {}
reg_names = ['prepare_loop', 'candidate', 'activate_candidate', 'predict', 'odom', 'imu', 'path',
             'profile', 'clock', 'snapshot_locked', 'snapshot_source_locked',
             'capture_final_source_locked', 'materialize_activation_trace', 'check_worker_locked',
             'mark_worker_unusable_locked', 'finish_tick', 'publish', 'owned_pair_record',
             'owned_input', 'receive_worker', 'eligible', 'tick_loop', 'invalidate_locked']
worker_names = ['receive', 'work', 'publish_capability', 'close_source', 'wait_recording_ready', 'event']
for number, directory in [
    (49, 'scheme_A_M4_recorder_bootstrap_20261021_49'),
    (53, 'scheme_A_M4_owned_faults_20261021_53'),
    (56, 'scheme_A_M4_diagnostic_worker_20261021_56')]:
    old_author = BASE / directory / 'author'
    files = {}
    for relative in bundle66['files']:
        old_file, new_file = old_author / relative, CURRENT / relative
        if old_file.is_file():
            x, y = raw(old_file), raw(new_file)
            files[relative] = {'historical': pin_bytes(x), 'current': pin_bytes(y),
                               'byte_identical': x == y}
            if x != y and relative in (reg_path, worker_path, 'worker/owned_cold_backend.hpp',
                    'fixture/synthetic_source_m4.cpp', 'common/p1_full_contract.hpp',
                    'observer/src/shadow/owned_execution_policy_native_v1.hpp'):
                diff = ''.join(difflib.unified_diff(x.decode().splitlines(True), y.decode().splitlines(True),
                    fromfile=str(old_file), tofile=str(new_file)))
                create(f'evidence/source_deltas/from{number}/{relative}.diff', diff)
        else:
            files[relative] = {'historical_absent': True, 'current': pin_bytes(raw(new_file))}
    old_reg, old_worker = raw(old_author / reg_path).decode(), raw(old_author / worker_path).decode()
    comparisons[str(number)] = {
        'historical_author': str(old_author), 'current_author': str(CURRENT), 'files': files,
        'same_files': sum(x.get('byte_identical', False) for x in files.values()),
        'modified_existing_files': [p for p, x in files.items()
                                    if not x.get('historical_absent') and not x['byte_identical']],
        'new_files': [p for p, x in files.items() if x.get('historical_absent')],
        'Regulator_methods': method_report(old_reg, current_reg, reg_names),
        'Worker_methods': method_report(old_worker, current_worker, worker_names),
    }
    if number == 56:
        fragments = {}
        for name, start, end in [
            ('native_result_to_candidate_delivery', '      result.success=answer.second.success;',
             '    }catch(const std::exception & e){'),
            ('normal_completion_and_numerical_failure', '    completed_++;active_=0;',
             '  uint64_t cap_generated_')]:
            x, y = fragment(old_worker, start, end), fragment(current_worker, start, end)
            fragments[name] = {'byte_identical': x == y, 'historical': pin_bytes(x.encode()),
                               'current': pin_bytes(y.encode()), 'start_anchor': start, 'end_anchor': end}
        comparisons['56']['Worker_successful_path_fragments'] = fragments

old_policy = raw(BASE / 'scheme_A_formal_execute_profile_20261020_47/implementation/native/owned_execution_entry_v2.hpp').decode()
new_policy = raw(CURRENT / 'observer/src/shadow/owned_execution_policy_native_v1.hpp').decode()
authority = {'OutputAuthority': {
    'byte_identical': fragment(old_policy, 'class OutputAuthority {', '}  // namespace') ==
                      fragment(new_policy, 'class OutputAuthority {', '}  // namespace'),
    'historical': pin_bytes(fragment(old_policy, 'class OutputAuthority {', '}  // namespace').encode()),
    'current': pin_bytes(fragment(new_policy, 'class OutputAuthority {', '}  // namespace').encode()),
    'excluded': 'context_gate outside the class differs: v4 diagnostic entry and native 32hex GID'},
    'admission_core_byte_identical_to47': raw(CURRENT / 'observer/src/shadow/p1_admission.hpp') ==
        raw(BASE / 'scheme_A_formal_execute_profile_20261020_47/implementation/native/p1_admission.hpp')}
create('evidence/source_applicability_v1.json', {'schema': 'M4-source-range-applicability-v67',
    'comparisons': comparisons, 'original47_policy': authority,
    'qualification_scope': 'Source identity/range comparison only; affected integration and case sufficiency evaluated separately',
    'M4_stage_qualified': False})

evidence = {}
selected = {
    '47_policy92': 'scheme_A_formal_execute_profile_20261020_47/verification/entry_policy_cases_v2.json',
    '49_components': 'scheme_A_M4_recorder_bootstrap_20261021_49/verification/component_verification_v1.json',
    '49_source_core': 'scheme_A_M4_recorder_bootstrap_20261021_49/verification/source_core_reuse_v1.json',
    '49_normal': 'scheme_A_M4_recorder_bootstrap_20261021_49/postrun/actual_normal_audit_v1.json',
    '49_F5_scope': 'scheme_A_M4_recorder_bootstrap_20261021_49/evidence/F5_and_calibrated_nominal_scope_v1.json',
    '50_publication16': 'scheme_A_M4_publication_faults_20261021_50/postrun/publication_fault_audit_v1.json',
    '53_components': 'scheme_A_M4_owned_faults_20261021_53/verification/component_verification_v5.json',
    '53_R1': 'scheme_A_M4_owned_faults_20261021_53/postrun/R1_audit_v1.json',
    '53_R2': 'scheme_A_M4_owned_faults_20261021_53/postrun/R2_audit_v1.json',
    '53_R3': 'scheme_A_M4_owned_faults_20261021_53/postrun/R3_audit_v1.json',
    '53_matrix': 'scheme_A_M4_owned_faults_20261021_53/postrun/M4_fault_coverage_v1.json',
    '56_W1': 'scheme_A_M4_diagnostic_worker_20261021_56/postrun/W1_audit_v1.json',
    '56_W3': 'scheme_A_M4_diagnostic_worker_20261021_56/postrun/W3_audit_v1.json',
    '56_W4': 'scheme_A_M4_diagnostic_worker_20261021_56/postrun/W4_audit_v1.json',
    '66_W2': 'scheme_A_W2_owned_takeover_20261023_66/evidence/owned_audit_v1.json',
}
for key, relative in selected.items():
    path = BASE / relative
    data = load(path)
    evidence[key] = {'path': str(path), **INPUTS[str(path.resolve())],
        'original_schema': data.get('schema'), 'passed_field': data.get('passed'),
        'top_level_keys': list(data)}

identities = {}
batch56 = BASE / 'scheme_A_M4_diagnostic_worker_20261021_56'
for case in ('W1', 'W3', 'W4'):
    reg_file = batch56 / 'implementation' / f'{case}_registration_v1.json'
    registration = load(reg_file)
    registry_file = Path(registration['registry'])
    registry = load(registry_file)
    old_audit = load(batch56 / 'postrun' / f'{case}_audit_v1.json')
    result = load(Path(registration['output']) / 'driver_result.json')
    row = {'registration': {'path': str(reg_file), **INPUTS[str(reg_file)]},
           'run_id': registration['run_id'], 'audit_run_id_equal': old_audit['run_id'] == registration['run_id'],
           'registration_pin_in_audit_matches': old_audit['registration_sha256'] == INPUTS[str(reg_file)]['sha256'],
           'registry_pin_matches': registration['registry_sha256'] == INPUTS[str(registry_file)]['sha256'],
           'driver_passed_claim': result.get('passed'), 'historical_audit_passed': old_audit['passed'],
           'roles': {}}
    for role, role_row in registry['roles'].items():
        binary = Path(role_row['binary'])
        source_bundle = Path(role_row['source_bundle']['path'])
        role_bundle = load(source_bundle)
        rows = role_bundle.get('files', {})
        if isinstance(rows, list):
            rows = {str(i): x for i, x in enumerate(rows)}
        current_source_changes = []
        for name, item in rows.items():
            if not isinstance(item, dict) or 'path' not in item or 'sha256' not in item:
                continue
            source_path = Path(item['path'])
            if not source_path.is_file() or pin_bytes(raw(source_path))['sha256'] != item['sha256']:
                current_source_changes.append(str(source_path))
        row['roles'][role] = {
            'binary_pin_matches': pin_bytes(raw(binary))['sha256'] == role_row['binary_sha256'],
            'bundle_pin_matches': INPUTS[str(source_bundle)]['sha256'] == role_row['source_bundle']['sha256'],
            'bundle_files_currently_changed': current_source_changes,
            'source_bundle': str(source_bundle)}
    row['immutable_identity_chain_matches_now'] = (row['registration_pin_in_audit_matches'] and
        row['registry_pin_matches'] and all(r['binary_pin_matches'] and r['bundle_pin_matches'] and
            not r['bundle_files_currently_changed'] for r in row['roles'].values()))
    identities[case] = row
create('evidence/historical_case_identity_v1.json', {
    'schema': 'M4-historical-diagnostic-case-identity-v67', 'cases': identities,
    'qualification_scope': 'Identity readback, not a new execution or a rerun of the old auditor'})
create('evidence/historical_evidence_catalog_v1.json', {'schema': 'M4-evidence-catalog-v67', 'evidence': evidence})
create('evidence/source_audit_inputs_v1.json', {'files': INPUTS, 'count': len(INPUTS)})
print(json.dumps({'source_file_matches': {k: v['same_files'] for k, v in comparisons.items()},
                  'regulator_unchanged_methods': {k: [n for n, m in v['Regulator_methods'].items() if m['byte_identical']]
                                                 for k, v in comparisons.items()},
                  'Worker56_fragments': comparisons['56']['Worker_successful_path_fragments'],
                  'OutputAuthority_identical': authority['OutputAuthority']['byte_identical'],
                  'old_diagnostic_identity_matches': {k: v['immutable_identity_chain_matches_now']
                                                      for k, v in identities.items()},
                  'inputs': len(INPUTS)}, ensure_ascii=False))
