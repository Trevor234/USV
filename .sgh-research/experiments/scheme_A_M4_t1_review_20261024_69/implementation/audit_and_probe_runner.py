#!/usr/bin/env python3
"""Read original evidence and replay failure-control flow in a private folder."""
from pathlib import Path
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import types

ROOT = Path(__file__).resolve().parents[1]
B68 = ROOT.parent / 'scheme_A_M4_t1_component_wiring_20261024_68'
OUT = ROOT / 'evidence/runner_review02'


def pin(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(data, (dict, list)) else data)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases(doc):
    return {f'{suite["name"]}.{case["name"]}': case
            for suite in doc['testsuites'] for case in suite['testsuite']}


OUT.mkdir()
verification = json.loads((B68 / 'evidence/t1_wiring/verification_v1.json').read_text())
nominal_dir = Path(verification['nominal_run']['run_dir'])
nominal = json.loads((nominal_dir / 'gtest.json').read_text())
nominal_cases = cases(nominal)
assert nominal['tests'] == 25 and nominal['failures'] == nominal['errors'] == nominal['disabled'] == 0
assert all(not case.get('failures') and case['status'] == 'RUN' and case.get('result') == 'COMPLETED'
           for case in nominal_cases.values())
mutation_rows = []
mutation_raw = {}
for row in verification['mutations']:
    folder = Path(row['run_dir'])
    doc = json.loads((folder / 'gtest.json').read_text())
    actual_cases = cases(doc)
    assertions = {name for name, case in actual_cases.items() if case.get('failures')}
    assert set(row['expected_subset']) <= assertions
    assert row['mutation_test_exit'] == 1 and doc['failures'] > 0 and doc['errors'] == 0
    original = Path(verification['source_under_test']['regulator']).read_text()
    mutated = B68 / 'evidence/t1_mutations' / row['name'] / 'regulator_owned_execute.cpp'
    assert original.count(row['find']) == 1
    assert mutated.read_text() == original.replace(row['find'], row['replace'], 1)
    assert pin(mutated)['sha256'] == row['mutated_sha256']
    mutation_rows.append({'name': row['name'], 'actual_assertion_failures': sorted(assertions),
                          'source_exact_mutation': True, 'gtest': pin(folder / 'gtest.json')})
    mutation_raw[row['name']] = (1, {name: {'status': case['status'],
        'failures': [item['failure'] for item in case.get('failures', [])]}
        for name, case in actual_cases.items()}, folder)

pads = []
for path in sorted((nominal_dir / 'cases').rglob('source.jsonl')):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    summary = [row for row in rows if row.get('type') == 'source_summary']
    assert len(summary) == 1 and summary[0]['dropped'] == 0
    for row in rows:
        if row.get('type') == 't1_component_flush_pad':
            assert isinstance(row.get('filler'), str) and len(row['filler']) == 8200
            pads.append({'case': path.parent.name, 'filler_bytes': len(row['filler'].encode()),
                          'serialized_bytes': len(json.dumps(row).encode())})
assert pads
baseline_binary = Path(verification['nominal_run']['build_dir']) / 'test_current_candidate_reference_clock'
create(OUT / 'artifact_readback_v1.json', {
    'schema': 'T1-original-evidence-independent-readback-v69',
    'nominal_tests': 25, 'nominal_assertion_failures': 0,
    'mutation_evidence': mutation_rows, 'flush_pad': pads,
    'flush_pad_payload_is_real_8200_byte_string': True,
    'baseline_binary': {'path': str(baseline_binary), **pin(baseline_binary)},
    'verification': {'path': str(B68 / 'evidence/t1_wiring/verification_v1.json'),
                      **pin(B68 / 'evidence/t1_wiring/verification_v1.json')},
    'scope': 'Readback of actual 68 records; does not sign off all semantic coverage claims'})

# Reproduce the original runner's actual main() with mocked build/execute.
# All output directories are private; no old run or source is modified.
module = load_module(B68 / 'scripts/run_t1.py', 'reviewed_runner68')
fake = OUT / 'unprepared_mutation_probe'
fake.mkdir()
module.BATCH = fake
module.bundle_sha256 = lambda: json.loads((B68 / 'evidence/init_inputs_v1.json').read_text())['current_author_bundle']['bundle_sha256']
module.MUTATIONS = copy.deepcopy(module.MUTATIONS)
module.MUTATIONS[0]['find'] = '__intentionally_missing_source_pattern__'
module.configure_and_build = lambda *args, **kwargs: (types.SimpleNamespace(returncode=0), fake / 'mock_build.log')
calls = 0


def fake_gtest(binary, output_dir):
    global calls
    calls += 1
    if calls == 1:
        return 0, {name: {'status': row['status'], 'failures': []}
                   for name, row in nominal_cases.items()}, output_dir
    name = module.MUTATIONS[calls - 1]['name']
    rc, rows, _ = mutation_raw[name]
    return rc, rows, output_dir


module.run_gtest = fake_gtest
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    returncode = module.main()
create(fake / 'probe.stdout', capture.getvalue())
generated = json.loads((fake / 'evidence/t1_wiring/verification_v1.json').read_text())
assert returncode == 0 and generated['mutations'][0]['applied'] is False
create(OUT / 'failure_exit_counterexample_v1.json', {
    'schema': 'T1-runner-failure-exit-counterexample-v69',
    'original_main_returncode': returncode,
    'unprepared_mutation': generated['mutations'][0],
    'nominal_data': 'Actual run06 JSON; builds/execution mocked, no ROS initialized',
    'counterexample_confirmed': True,
    'expected_nonzero_returncode': True,
    'source': {'path': str(B68 / 'scripts/run_t1.py'), **pin(B68 / 'scripts/run_t1.py')}})

# Also show that the finalizer returns normally when its own final gate is false.
finalizer = load_module(B68 / 'scripts/finalize.py', 'reviewed_finalizer68')
final_fake = OUT / 'finalizer_false_green_probe'
(final_fake / 'evidence/t1_wiring').mkdir(parents=True)
(final_fake / 'postrun').mkdir()
(final_fake / 'build').mkdir()
init = json.loads((B68 / 'evidence/init_inputs_v1.json').read_text())
create(final_fake / 'evidence/init_inputs_v1.json', init)
bad = copy.deepcopy(verification)
bad['nominal_run']['all_passed'] = False
create(final_fake / 'evidence/t1_wiring/verification_v1.json', bad)
finalizer.BATCH = final_fake
finalizer.MIRROR = OUT / 'private_mirror_for_finalizer_probe'
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    returned = finalizer.main()
create(final_fake / 'probe.stdout', capture.getvalue())
assert returned is None and '"all_green": false' in capture.getvalue()
create(OUT / 'finalizer_exit_counterexample_v1.json', {
    'schema': 'T1-finalizer-exit-counterexample-v69',
    'main_return': returned, 'stdout_all_green': False,
    'entry_uses_sys_exit': False, 'normal_Python_exit_is_zero': True,
    'counterexample_confirmed': True,
    'scope': 'Private input with all_passed=false; actual finalizer control flow, no old mirror writes'})

# A destination-only loop cannot notice an omitted expected source file.
source = OUT / 'one_sided_mirror_probe/source'
mirror = OUT / 'one_sided_mirror_probe/mirror'
source.mkdir(parents=True)
mirror.mkdir(parents=True)
(source / 'a.txt').write_text('same')
(source / 'required_b.txt').write_text('must be present')
(mirror / 'a.txt').write_text('same')
old_mismatches = [str(path.relative_to(mirror)) for path in sorted(mirror.rglob('*'))
                  if path.is_file() and (not (source / path.relative_to(mirror)).is_file()
                  or pin(source / path.relative_to(mirror)) != pin(path))]
assert old_mismatches == []
create(OUT / 'mirror_population_counterexample_v1.json', {
    'original_destination_only_loop_mismatches': old_mismatches,
    'actually_missing_required_file': 'required_b.txt', 'counterexample_confirmed': True})
print(json.dumps({'actual_nominal25_all_passed': True, 'actual_mutations_caught': len(mutation_rows),
                  'real_8200_byte_pads': len(pads), 'runner_unprepared_returns_zero': True,
                  'finalizer_false_green_returns_normally': True,
                  'one_sided_mirror_misses_missing_file': True}))
