#!/usr/bin/env python3
"""Finite offline review probes only; no ROS, owned roles, or survivor launch."""
from pathlib import Path
import argparse
import ast
import collections
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
REPO = ROOT.parents[2]
OUT = ROOT / 'evidence/replay01'
sys.dont_write_bytecode = True


def create(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def run(directory, name, command, expected=0, env=None):
    with (directory / (name + '.stdout')).open('xb') as out, (directory / (name + '.stderr')).open('xb') as err:
        child = subprocess.run(command, stdout=out, stderr=err, timeout=60, env=env)
    result = {'command': command, 'returncode': child.returncode,
              'stdout': str((directory / (name + '.stdout')).relative_to(ROOT)),
              'stderr': str((directory / (name + '.stderr')).relative_to(ROOT))}
    assert child.returncode == expected, result
    return result


parser = argparse.ArgumentParser()
parser.add_argument('part', choices=['rnw', 'epoch_model', 't3'])
args = parser.parse_args()
directory = OUT / args.part
records = []
if args.part == 'rnw':
    for name in ['replay_checks', 'probe_audit', 'probe_admission']:
        records.append(run(directory, name, [sys.executable, '-B', str(directory / (name + '.py'))]))
    build = directory / 'build'
    build.mkdir()
    binary = build / 'mapping'
    records.append(run(directory, 'mapping_build', ['g++', '-std=c++17', '-O1', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', str(directory / 'probe_mapping.cpp'), '-o', str(binary)]))
    records.append(run(directory, 'mapping_cap', [str(binary)]))
    records.append(run(directory, 'mapping_overflow', [str(binary), 'overflow'], expected=1))
    assert 'signed integer overflow' in (directory / 'mapping_overflow.stderr').read_text()
    skew = build / 'receive_skew'
    records.append(run(directory, 'skew_build', ['g++', '-std=c++17', str(directory / 'probe_receive_skew.cpp'), '-o', str(skew)]))
    records.append(run(directory, 'receive_skew', [str(skew)]))
elif args.part == 'epoch_model':
    source_root = BASE / 'scheme_A_M4_t2b_gen_impl_20261025_103/implementation/t2_author'
    shadow = source_root / 'observer/src/shadow'
    build = directory / 'build'
    build.mkdir()
    cpp_common = ['g++', '-std=c++17', '-O1', '-I', str(shadow), '-I', str(source_root / 'common'),
                  '-I', '/usr/include/eigen3', '-I', str(REPO / 'usv_mpc_ws/src/usv_mpc_cpp/include')]
    utils = str(REPO / 'usv_mpc_ws/src/usv_mpc_cpp/src/utils.cpp')
    binary = build / 'epoch_probe'
    records.append(run(directory, 'epoch_build', [*cpp_common, str(directory / 'epoch_probe.cpp'), utils, '-o', str(binary), '-pthread']))
    records.append(run(directory, 'epoch_probe', [str(binary)]))
    create(directory / 'epoch_result.json', json.loads((directory / 'epoch_probe.stdout').read_bytes()))
    command = json.loads((ROOT / 'evidence/independent_reviews/epoch_model/compile_commands.json').read_bytes())
    command = [x.replace('/tmp/review123_epoch_model/model_probe.cpp', str(directory / 'model_probe.cpp'))
                 .replace('/tmp/review123_epoch_model/model_probe', str(build / 'model_probe')) for x in command]
    records.append(run(directory, 'model_build', command))
    model_env = dict(os.environ)
    model_env['LD_LIBRARY_PATH'] = str(REPO / 'usv_mpc_ws/install/usv_mpc_cpp/lib') + ':/home/trevor/acados/lib:' + model_env.get('LD_LIBRARY_PATH', '')
    records.append(run(directory, 'model_probe', [str(build / 'model_probe')], env=model_env))
    create(directory / 'model_result.json', json.loads((directory / 'model_probe.stdout').read_bytes()))
    # Remove the exact inner G3 ledger guard in a private copy, retaining old tests.
    mutation = directory / 'ledger_mutation'
    mutation.mkdir()
    original_header = shadow / 'scoped_epoch_v1.hpp'
    header = original_header.read_text()
    needle = '''    for (const auto &record : ledger_)
      if (record.anchor && record.anchor->binding == binding) {
        info.blocked_reason = "scoped_open_binding_not_new"; return info;
      }
'''
    assert header.count(needle) == 1
    with (mutation / 'scoped_epoch_v1.hpp').open('x') as stream:
        stream.write(header.replace(needle, ''))
    test = source_root / 'observer/tests/test_scoped_epoch_v1.cpp'
    with (mutation / test.name).open('xb') as stream:
        stream.write(test.read_bytes())
    mut_binary = build / 'test_deleted_ledger_guard'
    records.append(run(directory, 'ledger_mutation_build', [*cpp_common, '-I', str(mutation),
                        str(mutation / test.name), utils, '-o', str(mut_binary), '-pthread']))
    cases = []
    for i in range(1, 7):
        case = 'T2B-GEN-E' + str(i)
        records.append(run(directory, 'ledger_' + case, [str(mut_binary), case, str(mutation / case)]))
        cases.append(json.loads((mutation / case / 'result.json').read_bytes()))
    assert all(c['passed'] is True for c in cases)
    create(directory / 'mutation_ledger_result.json', {'mutation': 'delete exact G3 retired-ledger check',
           'all_original_six_pass': True, 'assertions': sum(len(c['assertions']) for c in cases),
           'source_sha256': hashlib.sha256(original_header.read_bytes()).hexdigest()})
    # Extract only the audit clause function and its binding comparison; never run the audit main.
    audit_path = BASE / 'scheme_A_M4_t2bgen_audit_20261025_105/implementation/audit_t2bgen.py'
    tree = ast.parse(audit_path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'clause')
    ns = {'clauses': [], 'json': json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(audit_path), 'exec'), ns)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'clause' and n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == 'GEN.owned.sources_vs_batch91')
    positional_bug = ns['clause'](call.args[0].value, False, ast.literal_eval(call.args[2]))
    compare = next(n for n in ast.walk(tree) if isinstance(n, ast.Compare) and isinstance(n.left, ast.Tuple)
                   and n.left.elts and isinstance(n.left.elts[0], ast.Constant) and n.left.elts[0].value == 1
                   and isinstance(n.comparators[0], ast.Tuple) and isinstance(n.comparators[0].elts[0], ast.Constant)
                   and n.comparators[0].elts[0].value == 2)
    committed = [{'reference_epoch': {'task_generation': 2, 'path_fingerprint': 'same'}} for _ in range(2)]
    constant_binding_bug = eval(compile(ast.Expression(compare), str(audit_path), 'eval'), {'committed': committed})
    assert positional_bug is True and constant_binding_bug is True
    create(directory / 'audit_false_pass_result.json', {'scope': 'actual AST-extracted clause and comparison',
           'false_source_comparison_recorded_as_pass': positional_bug,
           'same_binding_declared_different_due_generation_constants': constant_binding_bug,
           'recorded_clause': ns['clauses'][0]})
else:
    # ASAN only launches Q2 native harness; no ROS or survivor role is involved.
    records.append(run(directory, 'asan_driver', [sys.executable, '-B', str(directory / 'run_asan_probe.py')]))
    asan = json.loads((directory / 'asan_probe.json').read_bytes())
    assert asan['compile_rc'] == 0 and asan['run_rc'] == 1 and asan['asan_stack_use_after_scope'] is True
    source_root = BASE / 'scheme_A_M4_t3q_impl_20261025_99/implementation/t2_author'
    binary = directory / 'sticky_probe'
    records.append(run(directory, 'sticky_build', ['g++', '-std=c++17', '-O1', '-I', str(source_root / 'observer/src/shadow'),
                        '-I', str(source_root / 'common'), str(directory / 'sticky_probe.cpp'), '-o', str(binary), '-pthread']))
    records.append(run(directory, 'sticky_probe', [str(binary)]))
    create(directory / 'sticky_probe.json', json.loads((directory / 'sticky_probe.stdout').read_bytes()))
    actual = source_root.parent / 'runs/T3-Q2_r2/q2.jsonl'
    rows = [json.loads(x) for x in actual.read_text().splitlines() if x.strip()]
    ids = [x['sequence'] for x in rows if x.get('type') == 't3_event']
    assert len(ids) == 513 and len(set(ids)) == 163
    create(directory / 'q2_actual_id_probe.json', {'file': str(actual),
           'sha256': hashlib.sha256(actual.read_bytes()).hexdigest(), 'accepted_rows': len(ids),
           'unique_ids': len(set(ids)), 'duplicate_count': len(ids) - len(set(ids)), 'min': min(ids), 'max': max(ids)})
with (directory / 'replay_result.json').open('x') as stream:
    stream.write(json.dumps({'part': args.part, 'commands': records, 'owned_runs': 0, 'ROS_initialized': False,
                             'production_fixes_implemented': False,
                             'scope': 'review probes complete, including expected negative findings; not requalification'}, indent=2) + '\n')
print(json.dumps({'part': args.part, 'review_replay_complete': True, 'commands': len(records), 'owned_runs': 0}))
