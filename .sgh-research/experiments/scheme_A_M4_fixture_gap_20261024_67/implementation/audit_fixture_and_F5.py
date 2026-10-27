#!/usr/bin/env python3
"""Bind F5's prior regression and actual nominal/source differences explicitly."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
AUTHOR = ROOT / 'implementation/current_author'
INPUTS = {}


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return INPUTS[str(path)]


def load(path):
    pin(path)
    return json.loads(Path(path).read_text())


oracle_root = BASE / 'p1_execution_architecture_20261005_01/m1_equivalence_01'
oracle = load(oracle_root / 'oracle_manifest.json')
oracle_inputs = {}
for key, row in oracle['inputs'].items():
    path = Path(row['path'])
    oracle_inputs[key] = {'path': str(path), 'expected_sha256': row['sha256'],
                          'actual': pin(path), 'matches': pin(path)['sha256'] == row['sha256']}
required_math_inputs = ['f5_backup', 'core_header', 'core_source', 'model_source', 'utils_source',
                        'model_header', 'utils_header', 'public_fixture']
assert all(oracle_inputs[key]['matches'] for key in required_math_inputs)
for name, digest in oracle['outputs'].items():
    assert pin(oracle_root / name)['sha256'] == digest
oracle_xml = oracle_root / 'gtest.xml'
pin(oracle_xml)
xml = ET.parse(oracle_xml).getroot()
assert int(xml.attrib['tests']) == 9 and all(int(xml.attrib[key]) == 0
    for key in ('failures', 'errors', 'disabled'))
oracle_cases = [case.attrib['name'] for suite in xml.findall('testsuite') for case in suite.findall('testcase')]

frozen = BASE / 'p1_atomic_freeze_20261005_01'
atomic_evidence = load(frozen / 'atomic_freeze_test_evidence.json')
atomic_xml = frozen / 'frozen_test_evidence/test_research_contract.gtest.xml'
assert pin(atomic_xml)['sha256'] == atomic_evidence['gtest_report_sha256']
assert atomic_evidence['source_node_sha256'] == oracle['inputs']['f5_backup']['sha256']
x = ET.parse(atomic_xml).getroot()
assert int(x.attrib['failures']) == int(x.attrib['errors']) == int(x.attrib['disabled']) == 0
logging_names = ['LoggingOffAndOnPreserveIdenticalCommandSelection',
                 'LoggingOffAndOnPreserveSameReferenceAndCommands',
                 'NormalFrozenInputEqualsActualBuilderLoggingOffAndOn']
logging_cases = {case.attrib['name']: case.attrib for suite in x.findall('testsuite')
                 for case in suite.findall('testcase') if case.attrib['name'] in logging_names}
assert set(logging_cases) == set(logging_names)
assert all(row.get('status') == 'run' and row.get('result') == 'completed' for row in logging_cases.values())
frozen_binary = frozen / 'frozen_test_evidence/test_research_contract'
binary_evidence = {'path': str(frozen_binary), 'present': frozen_binary.is_file()}
if frozen_binary.is_file():
    binary_evidence.update(actual=pin(frozen_binary),
        matches=pin(frozen_binary)['sha256'] == atomic_evidence['compiled_test_binary_sha256'])

f5 = BASE / 'p1_f5_atomic_baseline_20261005_02'
runtime = load(f5 / 'config_runtime.json')
pilot = load(f5 / 'pilot_result.json')
reference_report = load(f5 / 'reference_reports/reference_prediction_report.json')
publisher_report = load(f5 / 'reports_initial/contract_report.json')
assert pilot['all_required_acceptance_flags'] and reference_report['passed'] and publisher_report['passed']
c = load(BASE / 'scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json')
nominal = runtime['controller_effective_vehicle']
assert set(nominal) == set(c['hydro']) and len(nominal) == 19
hydro_rows = {key: {'F5': value, 'current': c['hydro'][key], 'equal': value == c['hydro'][key]}
              for key, value in nominal.items()}
assert all(row['equal'] for row in hydro_rows.values())
assert runtime['nominal_effective_yaml_sha256'] == c['nominal_hash']
assert runtime['solver_input_constraints']['T_min'] == c['command_min_n']
assert runtime['solver_input_constraints']['T_max'] == c['command_max_n']

fixture_path = AUTHOR / 'fixture/synthetic_source_m4.cpp'
pin(fixture_path)
fixture = fixture_path.read_text()
# These are capability inventory checks, not behavioural tests of absent hooks.
assert 'mode_=="C"&&reference_speed_==.05' in fixture
assert '100000000000LL+target-start_' in fixture
assert 'if(count_%25==0)' in fixture
capabilities = {
    'current_source': 'actual-owned-Applied-driven nominal RK4 point model, .05 straight',
    'source_domain_changed_from_F5': 'F5 uses VRX/plant sensor stream; current fixture is an isolated nominal source',
    'reference_kind': '201 fixed straight points, dt .2, 40s; rebuilt target uses shared F5 math',
    'publishes_sensors_hz': 50, 'reference_every_sensor_samples': 25,
    'clock_mapping': '100s + steady elapsed from fixture start, one-to-one',
    'current_fault_schedule_interface': False,
    'reference_clear_replace_mismatch_stimuli': False,
    'stale_future_skew_clock_pause_reset_jump_stimuli': False,
    'candidate_forgery_owner': 'must be a diagnostic Worker or source-linked callback fixture; synthetic_source owns no candidate writer',
    'output_publishers': 0,
    'cannot_fix_gap_by_adding_foreign_writer': True,
    'required_extension': 'finite predeclared action schedule on the already-owned Fixture writers, with raw Source events and exact case audit; ordinary .05 default unchanged',
}
result = {
    'schema': 'M4-F5-and-current-Fixture-applicability-v67',
    'F5_original_pilot_qualified_at_original_scope': True,
    'F5_pilot_plant_acceptance': reference_report['plant_acceptance_observed'],
    'F5_shared_math_inputs': oracle_inputs,
    'F5_shared_math_inputs_unchanged': True, 'F5_original_equivalence_gtests': oracle_cases,
    'F5_equivalence_fixture_pairs': oracle['reference_fixture_pairs'],
    'F5_logging_regression': {'source_and_xml_pins_match': True, 'cases': logging_cases,
                              'binary_readback': binary_evidence,
                              'scope': 'Original synchronous F5 regression, not a claim that current owned Source/Witness can be disabled'},
    'hydro19_equal': True, 'hydro19_rows': hydro_rows,
    'nominal_file_identity_equal': True, 'command_bounds_equal': True,
    'current_actual_legacy_wrapper_unchanged': oracle_inputs['actual_legacy_wrapper']['matches'],
    'whole_legacy_wrapper_reuse_claimed': False,
    'current_fixture': capabilities,
    'scope_resolution': 'Retain original F5 source/reference/mapping and logging regression at its tested layer; map identical nominal19/core math and declare new .05 target-reference/source domain. Do not demand or claim plant equivalence for the isolated component.',
    'original_F5_plant_reference_identity_transferred': False,
    'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False,
    'new_ROS_or_owned_run': False,
}
for relative, value in [('evidence/F5_fixture_applicability_v1.json', result),
                         ('evidence/F5_fixture_inputs_v1.json', {'files': INPUTS, 'count': len(INPUTS)})]:
    with (ROOT / relative).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'hydro19_equal': True, 'F5_math_gtests_reusable': len(oracle_cases),
                  'logging_regression_cases': len(logging_cases),
                  'actual_legacy_wrapper_unchanged': result['current_actual_legacy_wrapper_unchanged'],
                  'fixture_fault_schedule_exists': False}))
