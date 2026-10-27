#!/usr/bin/env python3
"""Compile existing deterministic core tests against current frozen headers."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
AUTHOR = ROOT / 'implementation/current_author'
TESTS = REPO / 'usv_mpc_ws/src/usv_research_safety_cpp'
OUT = ROOT / 'evidence/core_components_attempt02'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n'
                     if isinstance(value, (dict, list)) else value)


OUT.mkdir()
originals = [TESTS / name for name in ('test_p1_admission.cpp',
    'test_p1_capability_lease.cpp', 'test_p1_tick_barrier.cpp')]
copies = []
for original in originals:
    destination = OUT / original.name
    shutil.copy2(original, destination)
    copies.append(destination)
include_root = REPO / 'usv_mpc_ws/src/usv_mpc_cpp/include'
inputs = originals + [ROOT / 'implementation/test_deadline_matrix.cpp']
inputs += [p for p in AUTHOR.rglob('*') if p.is_file()]
inputs += [p for p in include_root.rglob('*.hpp') if p.is_file()]
core_sources = [REPO / 'usv_mpc_ws/src/usv_mpc_cpp/src' / name
                for name in ('p1_input_core.cpp', 'utils.cpp')]
inputs += core_sources
before = {str(p): pin(p) for p in inputs}
base = ['g++', '-std=c++17', '-O0', '-pthread', '-I/usr/include/eigen3',
        '-I' + str(include_root), '-I' + str(AUTHOR / 'observer/src/shadow'),
        '-I' + str(AUTHOR / 'common')]
sources = [str(p) for p in copies] + [str(ROOT / 'implementation/test_deadline_matrix.cpp'),
                                       str(AUTHOR / 'common/usv_model_dynamic.cpp')]
sources += [str(p) for p in core_sources]


def build_run(folder, flags=None):
    folder.mkdir()
    argv = base + (flags or []) + sources + ['-lgtest_main', '-lgtest', '-o', str(folder / 'core_tests')]
    create(folder / 'compile_argv.json', argv)
    result = subprocess.run(argv, capture_output=True, timeout=180)
    (folder / 'compile.stdout').write_bytes(result.stdout)
    (folder / 'compile.stderr').write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode(errors='replace')[-3000:]
    xml_path = folder / 'gtest.xml'
    run = subprocess.run([str(folder / 'core_tests'), '--gtest_output=xml:' + str(xml_path)],
                         capture_output=True, timeout=60)
    (folder / 'stdout.log').write_bytes(run.stdout)
    (folder / 'stderr.log').write_bytes(run.stderr)
    xml = ET.parse(xml_path).getroot()
    cases = [{'suite': suite.attrib['name'], 'name': case.attrib['name'],
              'passed': not case.findall('failure') and case.attrib.get('status') == 'run'}
             for suite in xml.findall('testsuite') for case in suite.findall('testcase')]
    return {'returncode': run.returncode, 'tests': int(xml.attrib['tests']),
            'failures': int(xml.attrib['failures']), 'errors': int(xml.attrib['errors']),
            'disabled': int(xml.attrib['disabled']), 'cases': cases, 'ELF': pin(folder / 'core_tests')}


baseline = build_run(OUT / 'baseline')
# Mutate only a temporary copy of the admission header, never the frozen author.
mutations = {}
header = AUTHOR / 'observer/src/shadow/p1_admission.hpp'
text = header.read_text()
for name, old, new in [
    ('accept_after_deadline', 'if(now>t.deadline)return "late";', 'if(false)return "late";'),
    ('reject_deadline_equality', 'if(now>t.deadline)return "late";', 'if(now>=t.deadline)return "late";'),
    ('permit_early_target', ' || now<committed_->target_ns', '')]:
    assert text.count(old) == 1, ('unprepared mutation', name)
    folder = OUT / 'mutations' / name
    folder.mkdir(parents=True)
    changed_header = folder / 'p1_admission.hpp'
    changed_header.write_text(text.replace(old, new, 1))
    # Quoted includes search the test file's folder first (no header there),
    # followed by this injected -I directory, ahead of the frozen header dirs.
    original_base = list(base)
    base[1:1] = ['-I' + str(folder)]
    try:
        result = build_run(folder / 'run')
    finally:
        base[:] = original_base
    failing = [case['suite'] + '.' + case['name'] for case in result['cases'] if not case['passed']]
    mutations[name] = {'prepared': True, 'compile_succeeded': True,
                       'caught_by_assertions': result['returncode'] == 1 and result['failures'] > 0,
                       'failing_tests': failing}
after = {path: pin(Path(path)) for path in before}
report = {'schema': 'M4-current-deterministic-core-components-v67', 'baseline': baseline,
          'mutations': mutations, 'inputs_before': before, 'inputs_after': after,
          'source_unchanged': before == after,
          'new_deadline_cases': 7, 'ROS_initialized': False, 'owned_runs': 0,
          'API_calls': 0, 'production_source_edited': False,
          'scope': 'Current admission, clock, input core, history, lease and scheduler components; generic FCU allowed-mode input is synthetic and does not change real B MANUAL contract',
          'complete': (baseline['returncode'] == 0 and baseline['tests'] > 0 and
              baseline['failures'] == baseline['errors'] == baseline['disabled'] == 0 and
              all(row['caught_by_assertions'] for row in mutations.values()) and before == after),
          'M4_stage_qualified': False, 'F6_qualified': False, 'P1_qualified': False}
create(OUT / 'verification_v1.json', report)
print(json.dumps({'baseline_tests': baseline['tests'], 'baseline_failures': baseline['failures'],
                  'mutations': mutations, 'complete': report['complete']}))
raise SystemExit(0 if report['complete'] else 2)
