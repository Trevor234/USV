#!/usr/bin/env python3
"""Read-only AST replay against retained C3.3 callbacks; no ROS imports/startup.

The invalid/foreign rows below are real retained native callback observations.
The +1 ns commit and worker-valid operand are explicitly hypothetical inputs
to the original checker predicate, not newly observed network Decisions.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
N = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9')
OUT = Path(__file__).absolute().parent
inputs = {}


def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(raw).hexdigest()
    return raw


def predicate(path, code):
    tree = ast.parse(read(path).decode(), str(path))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)
             and n.args[1].value == code]
    assert len(nodes) == 1, (code, len(nodes))
    call = nodes[0]
    expr = ast.Expression(call.args[0])
    return compile(expr, str(path), 'eval'), call.lineno, ast.unparse(call.args[0])


checker = N/'check_atomic_observation_v2.py'
expr, lineno, expression = predicate(checker, 'worker_valid_lease_source_binding')
admission_expr, admission_line, admission_expression = predicate(
    N/'validate_readiness_v3.py', 'capability_callback_invalid')
xml = ET.fromstring(read(N/'native_matrix03/gtest.xml'))
tests = {r.attrib['name']: {'failures': len(r.findall('failure')),
                          'status': r.attrib.get('status'),
                          'result': r.attrib.get('result')}
         for r in xml.iter('testcase')}
results = []
for name in ('CapabilityInvalidAfterValidKeepsLease',
             'CapabilityForeignAfterValidKeepsLease',
             'CapabilityResourceRejectedAfterValidKeepsLease',
             'CapabilityExpiredLeaseIsIrreversible',
             'CapabilityChangedInstanceIsTerminal',
             'CapabilityMatchingFatalIsTerminal'):
    rows = [json.loads(line) for line in read(N/'native_matrix03'/name/'source.jsonl').splitlines()]
    scope = json.loads(read(N/'native_matrix03'/name/'test_scope.json'))
    cap = [r for r in rows if r['type'] == 'capability_admission']
    renewed = [r for r in cap if r['renewed']]
    assert renewed
    final = cap[-1]
    commit = final['validation_commit_ns'] + 1
    original = eval(expr, {'__builtins__': {'bool': bool}}, {
        'cap': cap, 'f': {'commit_ns': commit},
        'cfg': {'worker_capability_receipt_timeout_ns': final['lease_timeout_ns']},
        'reads': {'commit_worker_valid': True}})
    last_valid = renewed[-1]['validation_commit_ns']
    terminal = [r for r in rows if r['type'] == 'worker_unusable_transition']
    expected_usable = not terminal and 0 <= commit-last_valid <= final['lease_timeout_ns']
    preserved = all(r['lease_last_after_ns'] == last_valid for r in cap[1:])
    results.append({'case': name, 'retained_native_result': tests[name],
                    'raw_network_authenticated': scope['raw_network_authenticated'],
                    'actual_final_admission': {k: final[k] for k in
                        ('valid', 'identity_valid', 'renewed', 'terminal_run',
                         'validation_commit_ns', 'lease_last_before_ns',
                         'lease_last_after_ns', 'lease_timeout_ns')},
                    'actual_terminal_reasons': [r['reason'] for r in terminal],
                    'hypothetical_commit_ns': commit,
                    'hypothetical_commit_worker_valid': True,
                    'lease_age_at_hypothetical_commit_ns': commit-last_valid,
                    'actual_later_admissions_preserve_last_valid': preserved,
                    'original_checker_predicate': original,
                    'last_valid_plus_terminal_rule_usable': expected_usable,
                    'original_normal_admission_predicate': eval(admission_expr,
                        {'__builtins__': {}}, {'a': final})})

# Actual normal fixture: this evaluates only the unchanged original local
# predicate at actually recorded operands. It is NOT a whole checker rerun.
run = N/'runs/owned_C3_3_positive_01'
source = [json.loads(line) for line in read(run/'observer/source.jsonl').splitlines()]
actual = []
for row in source:
    if row['type'] != 'decision':
        continue
    ob = row['d0_observation']; f = ob['final_snapshot']; reads = ob['gate_reads']
    if reads.get('commit_worker_valid') is None:
        continue
    cap = [r for r in source if r['type'] == 'capability_admission'
           and r['validation_commit_ns'] <= f['commit_ns']]
    assert cap
    actual.append({'sequence': row['sequence'], 'predicate_passed': eval(expr,
        {'__builtins__': {'bool': bool}}, {'cap': cap, 'f': f, 'reads': reads,
        'cfg': {'worker_capability_receipt_timeout_ns': cap[-1]['lease_timeout_ns']}})})
assert actual and all(r['predicate_passed'] for r in actual)
assert [r['case'] for r in results if r['last_valid_plus_terminal_rule_usable']
        and not r['original_checker_predicate']] == [
            'CapabilityInvalidAfterValidKeepsLease', 'CapabilityForeignAfterValidKeepsLease']
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
           for p, digest in inputs.items())
report = {'schema': 'scheme-A-lease-review-offline-AST/v1',
          'checker_predicate_line': lineno, 'checker_original_expression': expression,
          'normal_admission_predicate_line': admission_line,
          'normal_admission_original_expression': admission_expression,
          'cases': results, 'actual_normal_predicate_evaluations': actual,
          'new_runtime_tests': 0, 'new_network_tests': 0,
          'new_whole_checker_runs': 0,
          'historical_sources_unchanged': True, 'input_sha256': inputs,
          'scope': 'AST local predicate evaluation; retained source-linked native logs; hypothetical commit for invalid/foreign examples',
          'stage_qualification_changed': False}
(OUT/'lease_predicate_evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'cases': len(results), 'known_generalization_mismatches': 2,
                  'actual_normal_predicates_passed': len(actual),
                  'historical_sources_unchanged': True,
                  'evidence': str(OUT/'lease_predicate_evidence.json')}, ensure_ascii=False))
