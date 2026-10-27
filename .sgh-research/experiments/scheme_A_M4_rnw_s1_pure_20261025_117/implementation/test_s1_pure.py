#!/usr/bin/env python3
"""S1 acceptance matrix (batch 117): pure audit + hardened admission against
synthetic fixtures and the two retained real runs. Fail-closed; parse/shape
errors never count as caught outcomes."""
import copy, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rnw_audit_v1 as audit
import rnw_admission_v2 as adm

FIX = HERE / 'fixtures'
if FIX.exists():
    shutil.rmtree(FIX)
FIX.mkdir()

def w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + '\n')

def base_clock(i, receive, sim, sched):
    return {'type': 'clock', 'receive_ns': receive, 'sim_ns': sim, 'epoch': 0,
            'schedule_generation': sched, 'rtf_valid': True, 'paused': False}

def base_stream():
    r = []
    for i in range(4):
        r.append(base_clock(i, 1_000_000_000_000 + i * 20_000_000, 100_000_000_000 + i * 20_000_000, 1))
    r.append({'type': 'reference_epoch_committed', 'reference_epoch': {
        'generation': 1, 'schedule_generation': 1, 'clock_epoch': 0, 'task_generation': 2,
        'path_fingerprint': 'a' * 64, 'profile_fingerprint': 'a' * 64}, 'job_id': 1})
    # silence > 400ms, then resumed clock with schedule transition (epoch stays 0 — legal)
    for i in range(4, 8):
        r.append(base_clock(i, 1_000_080_000_000 + (i - 4) * 20_000_000,
                            100_000_800_000 + (i - 4) * 20_000_000, 2 if i < 6 else 3))
    r.append({'type': 'reference_epoch_generation_opened', 'generation': 2,
              'previous_terminal_reason': 'epoch_binding_changed',
              'previous_first_job_id': 1, 'previous_last_job_id': 2, 'opened_ns': 42})
    r.append({'type': 'reference_epoch_committed', 'reference_epoch': {
        'generation': 2, 'schedule_generation': 3, 'clock_epoch': 0, 'task_generation': 2,
        'path_fingerprint': 'a' * 64, 'profile_fingerprint': 'a' * 64}, 'job_id': 3})
    r.append({'type': 'job', 'job': {'job_id': 3}})
    r.append({'type': 'candidate_registration', 'job': {'job_id': 3},
              'accepted_registration': True, 'reason': '', 'ready_commit_ns': 50})
    r.append({'type': 'decision', 'job_id': 3, 'accepted': True,
              'control_source': 'candidate', 'sequence': 17})
    r.append({'type': 'owned_API_pair', 'sequence': 17, 'returned': [True, True]})
    r.append({'type': 'owned_applied_publication', 'sequence': 17})
    return r

def make_fixture(name, stream=None, clean=True):
    d = FIX / name
    stream = base_stream() if stream is None else stream
    w(d / 'regulator/source.jsonl', None) if False else None
    (d / 'regulator').mkdir(parents=True, exist_ok=True)
    (d / 'regulator/source.jsonl').write_text('\n'.join(json.dumps(x) for x in stream) + '\n')
    roles = [{'role': r, 'returncode': 0, 'group_empty': True} for r in ('regulator', 'fixture', 'worker', 'recorder')]
    w(d / 'driver_result.json', {'passed': clean, 'closed_roles': roles})
    ev = [{'type': 'role_spawned', 'role': r} for r in ('fixture', 'worker', 'recorder', 'regulator')]
    (d / 'driver_events.jsonl').write_text('\n'.join(json.dumps(x) for x in ev) + '\n')
    return d

results = []
def check(name, ok, detail=None):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + json.dumps(detail, default=str)[:160]) if detail else ''))

# --- audit: legal positive
d = make_fixture('positive')
v = audit.audit_rnw_run(d)
check('audit.legal_positive_passes', v['passed'] is True,
      {c['name']: c['coverage'] for c in v['clauses']})

# --- audit: false candidate
s = base_stream()
for r in s:
    if r.get('type') == 'candidate_registration':
        r['accepted_registration'] = False; r['reason'] = 'solver_failed'
v = audit.audit_rnw_run(make_fixture('false_candidate', s))
r4 = [c for c in v['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
check('audit.false_candidate_rejected', v['passed'] is False and r4['coverage'] == 'not_covered'
      and r4['detail']['attempted'][0]['reason'] == 'candidate_not_accepted')

# --- audit: fallback-only decision
s = base_stream()
for r in s:
    if r.get('type') == 'decision':
        r['control_source'] = 'ramp_zero'
v = audit.audit_rnw_run(make_fixture('fallback_only', s))
r4 = [c for c in v['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
check('audit.fallback_only_rejected', v['passed'] is False
      and r4['detail']['attempted'][0]['reason'] == 'no_accepted_candidate_sourced_decision'
      and 'ramp_zero' in r4['detail']['attempted'][0].get('observed_control_sources', []))

# --- audit: applied-only (no candidate registration)
s = [r for r in base_stream() if r.get('type') != 'candidate_registration']
v = audit.audit_rnw_run(make_fixture('applied_only', s))
r4 = [c for c in v['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
check('audit.applied_only_rejected', v['passed'] is False
      and r4['detail']['attempted'][0]['reason'] == 'no_candidate_registration')

# --- audit: API pair not real for the decision sequence
s = base_stream()
for r in s:
    if r.get('type') == 'owned_API_pair':
        r['returned'] = [True, False]
v = audit.audit_rnw_run(make_fixture('partial_api', s))
r4 = [c for c in v['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
check('audit.partial_api_rejected', v['passed'] is False
      and r4['detail']['attempted'][0]['reason'] == 'no_real_api_pair_for_decision_sequence')

# --- audit: real retained runs are honest negatives
B112 = Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/runs')
v1 = audit.audit_rnw_run(B112 / 'T2A_RNW2_attempt1')
v2 = audit.audit_rnw_run(B112 / 'T2A_RNW2')
r4_2 = [c for c in v2['clauses'] if c['name'] == 'r4_same_job_new_generation_acceptance'][0]
check('audit.attempt1_honest_not_covered', v1['passed'] is False,
      {c['name']: c['coverage'] for c in v1['clauses'] if c['coverage'] != 'covered'})
check('audit.attempt2_honest_not_covered', v2['passed'] is False
      and r4_2['detail']['reason'] == 'no_scoped_open')

# --- audit: parse error is distinct, never a pass and never "caught"
d = make_fixture('parse_error')
with open(d / 'regulator/source.jsonl', 'a') as f:
    f.write('{not json\n')
v = audit.audit_rnw_run(d)
check('audit.parse_error_distinct_failure',
      v['passed'] is False and any(c['name'] == 'regulator_source_parse_clean' and not c['passed']
                                   for c in v.get('clauses', [])) or v.get('error') == 'parse_errors_present')

# --- admission: legal table
legal = {'schema': 'M4-t2-action-table-v1', 'run_id': 'T3-RNW3', 'case': adm.FAMILY,
         'contract_sha256': 'c' * 64,
         'actions': [
             {'id': 'a1', 'action': 'clock_hold', 'parameters': {'mode': 'silent', 'duration_ms': 1200},
              'trigger': {'phase': 'after_grant_ms', 'delay_ms': 1200, 'job_id': 0}},
             {'id': 'a2', 'action': 'clock_resume', 'parameters': {},
              'trigger': {'phase': 'after_grant_ms', 'delay_ms': 2700, 'job_id': 0}},
             {'id': 'a3', 'action': 'driver_shutdown_request', 'parameters': {},
              'trigger': {'phase': 'after_grant_ms', 'delay_ms': 9000, 'job_id': 0}}],
         'clauses': dict(adm.CLAUSE_SPEC)}
ctx = {'run_id': 'T3-RNW3', 'contract_sha256': 'c' * 64}
check('admission.legal_table_passes', adm.validate_table(legal, ctx) == [])

def negative(name, mutate, expected_rejection):
    t = copy.deepcopy(legal)
    mutate(t)
    r = adm.validate_table(t, ctx)
    check('admission.' + name, expected_rejection in r, r[:3])

negative('missing_hold', lambda t: t['actions'].pop(0), 'missing_hold')
negative('resume_before_hold', lambda t: t['actions'].reverse(), 'resume_before_hold')
def all_false(t):
    t['clauses'] = {k: (False if v is True else 0) for k, v in adm.CLAUSE_SPEC.items()}
negative('all_false_clauses', all_false, 'clause_value:resume_requires_new_window')
negative('duplicate_action', lambda t: t['actions'][2].update({'action': 'clock_resume'}), 'duplicate_action')
def wrong_order(t):
    t['actions'][0], t['actions'][1] = t['actions'][1], t['actions'][0]
    t['actions'][0]['trigger']['delay_ms'] = 2700; t['actions'][1]['trigger']['delay_ms'] = 1200
negative('wrong_order', wrong_order, 'resume_before_hold')
negative('unregistered_action', lambda t: t['actions'][1].update({'action': 'path_clear'}), 'unregistered_action:path_clear')
negative('param_domain', lambda t: t['actions'][0]['parameters'].update({'duration_ms': 999}), 'parameters_domain:clock_hold')
negative('trigger_domain', lambda t: t['actions'][1]['trigger'].update({'delay_ms': 1}), 'trigger_domain:clock_resume')
def termination_not_last(t):
    t['actions'][2]['trigger']['delay_ms'] = 1000
negative('termination_window', termination_not_last, 'trigger_delay_not_monotonic')

passed = sum(1 for _, ok, _ in results if ok)
out = {'schema': 'S1-acceptance/v1', 'total': len(results), 'passed': passed,
       'results': [{'name': n, 'passed': ok, 'detail': d} for n, ok, d in results]}
(HERE.parent / 'postrun/s1_acceptance_v1.json').write_text(json.dumps(out, indent=2, default=str) + '\n')
print(f'S1 MATRIX {passed}/{len(results)}')
sys.exit(0 if passed == len(results) else 2)
