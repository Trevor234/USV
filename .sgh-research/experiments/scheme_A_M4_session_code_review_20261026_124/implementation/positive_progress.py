#!/usr/bin/env python3
"""Independently retain real progress while keeping coverage and qualification separate."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent


def read(p):
    return json.loads(Path(p).read_bytes())


def rows(p):
    return [(i, json.loads(s)) for i, s in enumerate(Path(p).read_text().splitlines(), 1) if s.strip()]


def one(data, typ, condition=lambda r: True):
    return next((i, r) for i, r in data if r.get('type') == typ and condition(r))


run = BASE / 'scheme_A_M4_rnw_s4_owned_20261025_119/implementation/runs/T2A_RNW3'
r, w, f = rows(run / 'regulator/source.jsonl'), rows(run / 'worker/source.jsonl'), rows(run / 'fixture/nominal_steps.jsonl')
oi, opened = one(r, 'reference_epoch_generation_opened')
ji, jobrow = one(r, 'job', lambda v: v['job']['job_id'] == 7)
ci, cand = one(r, 'candidate_registration', lambda v: v['job']['job_id'] == 7)
di, decision = one(r, 'decision', lambda v: v['job_id'] == 7 and v['accepted'] is True)
pi, pair = one(r, 'owned_API_pair', lambda v: v['sequence'] == decision['sequence'])
ai, applied = one(r, 'owned_applied_publication', lambda v: v['sequence'] == decision['sequence'])
_, receive = one(w, 'job_received', lambda v: v['job']['job_id'] == 7)
_, candidate = one(w, 'candidate', lambda v: v['job']['job_id'] == 7)
_, native = one(w, 'cold_start_policy_result', lambda v: v['job_id'] == 7)
_, resume = one(f, 't2_action_executed', lambda v: v['action'] == 'clock_resume')
job = jobrow['job']
rnw_checks = {
    'open_gen2': opened['generation'] == 2,
    'resume_before_submit': resume['executed_ns'] < jobrow['submit_commit_ns'],
    'full_Job_echo_equal': all(v == job for v in [cand['job'], receive['job'], candidate['job']]),
    'accepted_registration': cand['accepted_registration'] is True,
    'accepted_candidate_decision': decision['accepted'] is True and decision['control_source'] == 'candidate',
    'candidate_ready_before_activation': jobrow['submit_commit_ns'] <= cand['ready_commit_ns'] <= decision['activation_commit_ns'],
    'actual_API_after_activation': decision['activation_commit_ns'] <= pair['starts'][0] <= pair['ends'][0] <= pair['starts'][1] <= pair['ends'][1],
    'pair_success_and_command_match': pair['returned'] == [True, True] and pair['command_n'] == decision['final_n'],
    'Applied_same_sequence_and_source': applied['sequence'] == pair['sequence'] == decision['sequence'] == 18 and applied['control_source'] == 'candidate',
    'actual_C_once': native['metadata']['actual_C_solve_calls_this_job'] == 1,
}
assert all(rnw_checks.values()), rnw_checks
reg = read(BASE / 'scheme_A_M4_rnw_s4_owned_20261025_119/implementation/s4_registry.json')
bundle = read(reg['roles']['fixture']['source_bundle']['path'])
bundle_bad = []
for name, record in bundle['files'].items():
    raw = Path(record['path']).read_bytes()
    if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
        bundle_bad.append(name)
assert not bundle_bad and len(bundle['files']) == 108

pos = BASE / 'scheme_A_M4_t2bgen_owned_20261025_104/implementation/runs/T2BGEN_POS'
pr = rows(pos / 'regulator/source.jsonl')
commits = [x for _, x in pr if x.get('type') == 'reference_epoch_committed']
pos_ids = [x['job']['job_id'] for _, x in pr if x.get('type') == 'job']
pos_accepted = [x for _, x in pr if x.get('type') == 'decision' and x.get('accepted') is True]
assert [x['reference_epoch']['generation'] for x in commits] == [1, 2]
assert [x['reference_epoch']['task_generation'] for x in commits] == [2, 6]
assert pos_ids == sorted(set(pos_ids)) and max(pos_ids) == 27
neg = rows(pos.parent / 'T2BGEN_NEG/regulator/source.jsonl')
assert not any(x.get('type') == 'reference_epoch_generation_opened' for _, x in neg)

f6 = read(BASE / 'scheme_A_M4_n4_f6_impl_20261025_108/implementation/runs/F6-1/result.json')
equality = next(x for x in f6['assertions'] if x['name'] == 'f6_1_setter_switch_equals_fresh_m1_instance')
assert equality['observed'] == {'X_diff': 0.0, 'u_diff': 0.0}
cbase = BASE / 'scheme_A_M4_t3c_impl_20261025_100/implementation/runs'
c12 = read(cbase / 'T3C_C12/driver_result.json')
c3 = read(cbase / 'T3C_C3/driver_result.json')
cf = next(x for x in c12['closed_roles'] if x['role'] == 'fixture')
assert c12['cleanup_failed_roles'] == ['fixture'] and cf['group_empty'] is False
assert [x['signal'] for x in cf['signals']] == ['SIGINT', 'SIGTERM']
events = rows(cbase / 'T3C_C12/driver_events.jsonl')
assert sum(x.get('type') == 'role_spawned' for _, x in events) == 4
assert all(x['group_empty'] is True and x['returncode'] == 0 for x in c3['closed_roles'])

result = {
    'schema': 'schemeA-review-positive-progress-v124',
    'RNW3': {'run': str(run), 'checks': rnw_checks, 'job_id': 7, 'decision_sequence': 18,
             'source_lines': {'open': oi, 'job': ji, 'registration': ci, 'decision': di, 'API': pi, 'Applied': ai},
             'logical_times': {'resume': resume['executed_ns'], 'submit': jobrow['submit_commit_ns'],
                               'ready': cand['ready_commit_ns'], 'activation': decision['activation_commit_ns'],
                               'left_start': pair['starts'][0], 'right_end': pair['ends'][1]},
             'bundle_files': 108, 'bundle_bad_files': bundle_bad,
             'note': 'final Decision diagnostic row is appended after API/Applied; logical commit times establish causality'},
    'ScopedEpoch_POS': {'generations': [1, 2], 'task_generations': [2, 6], 'jobs': pos_ids,
                       'accepted_decisions': len(pos_accepted), 'NEG_no_open': True,
                       'limit': 'finite owned observation; not a proof of arbitrary Proposal callers or old-ELF bitwise equivalence'},
    'ModelTransaction_F6_1': {'observed': equality['observed'], 'tolerance': f6['tolerance'],
                             'limit': 'retained finite serial case, u and six-state prediction comparison; not all states/all trajectories/concurrency'},
    'T3_C12': {'fixture_group_empty': False, 'cleanup_failed_roles': c12['cleanup_failed_roles'],
              'fixture_signals': [x['signal'] for x in cf['signals']], 'Driver_role_spawns': 4,
              'C3_all_closed_clean': True,
              'limit': 'historical recorded finite supervisor path; no new process-group or survivor run performed'},
    'owned_runs_this_review': 0, 'qualification_granted': False}
with (ROOT / 'evidence/positive_progress_v1.json').open('x') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'RNW3_key_checks': len(rnw_checks), 'bundle_files': 108,
                  'scoped_POS_jobs': len(pos_ids), 'F6_observed_diff': equality['observed'], 'owned_runs': 0}))
