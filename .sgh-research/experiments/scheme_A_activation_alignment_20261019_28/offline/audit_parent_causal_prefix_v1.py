#!/usr/bin/env python3
"""Feasibility only: all actual parent measurement activation prefixes."""
from pathlib import Path
import copy, hashlib, json, math, sys

D = Path(__file__).resolve().parents[1]
N = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_activation_alignment_20261019_v28'
P = D.parent / 'scheme_A_owned_cold_start_20261018_27'
OLD = N.parent / 'authored_D1_owned_cold_start_20261018_v27'
R = OLD / 'runs/owned_cold_s005_01'
sys.path.insert(0, str(N))
import activation_alignment_audit_v1 as a

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def need(v, why):
    if not v: raise RuntimeError(why)

report = load(P / 'runs/s005_01/check_result.json')
inputs = dict(report['input_sha256_after'])
for p in [P / 'runs/s005_01/check_result.json', N / 'activation_alignment_audit_v1.py',
          N / 'check_source_components_v4.py', OLD / 'pair_wakeup_contract_v1.json']:
    inputs[str(p)] = sha(p)
need(all(sha(p) == h for p, h in inputs.items()), 'original inputs unchanged')
observer = [json.loads(line) for line in (R / 'observer/source.jsonl').read_text().splitlines()]
contract = load(OLD / 'pair_wakeup_contract_v1.json')
prefixes = a.reconstruct_frame_prefixes(observer)
jobs = {r['job']['job_id']: r['job'] for r in observer if r.get('type') == 'job'}
window = report['window']; rows = []
for d in [r for r in observer if r.get('type') == 'decision' and r.get('job_id', 0) > 0
          and window['start_ready_ns'] <= r['activation_commit_ns'] < window['end_driver_requested_ns']]:
    s = copy.deepcopy(d['d0_observation']['validation_snapshot'])
    # The original sample_ns predates the mutex-copy end. Keep it exactly;
    # do not make previously unavailable input causal by changing time.
    ids = [i for i in prefixes if i <= s['input_commit_ordinal']]
    generation, frames = prefixes[max(ids)]
    j = jobs[d['job_id']]
    point, scanned = a.select_frame(frames, s, j['target_sim_ns'], contract, generation)
    need(point is not None, 'no causal eligible state for Job ' + str(d['job_id']))
    state = a.propagate_frame(point, s, j['target_sim_ns'], contract['hydro'])
    error = [math.atan2(math.sin(x-y), math.cos(x-y)) if i == 2 else x-y
             for i, (x, y) in enumerate(zip(state, j['target_state']))]
    need(all(abs(x) <= contract['activation_tolerance'][i] for i, x in enumerate(error)), 'original state error gate')
    rows.append(dict(job_id=d['job_id'], actual_parent_accepted=d['accepted'], actual_parent_reason=d['reason'],
                     original_capture_ns=s['sample_ns'], original_copy_end_ns=s['copy_capture_ns'],
                     selected_frame=point, source_prefix_input_commit_ordinal=s['input_commit_ordinal'],
                     bounded_frame_count=len(frames), scanned=scanned, target_sim_ns=j['target_sim_ns'],
                     forward_horizon_ns=j['target_sim_ns']-point['odom_stamp_ns'],
                     forward_state=state, full_state_error=error,
                     selected_raw_odom_is_older=point['odom_sequence'] != s['odom_sequence'],
                     actual_runtime_used_this_selection=False))
need(len(rows) == 100, 'all 100 activation prefixes')
negative = []
s = copy.deepcopy(next(r for r in observer if r.get('type') == 'decision' and r.get('job_id') == 1)['d0_observation']['validation_snapshot'])
generation, frames = prefixes[max(i for i in prefixes if i <= s['input_commit_ordinal'])]
target = jobs[1]['target_sim_ns']
for name in ['empty', 'foreign_epoch', 'future_target_inputs', 'stale_receive', 'missing_dual_history', 'future_receive']:
    points, snapshot = copy.deepcopy(frames), copy.deepcopy(s)
    if name == 'empty': points = []
    elif name == 'foreign_epoch':
        for p in points: p['version']['epoch'] += 1
    elif name == 'future_target_inputs':
        for p in points: p['odom_stamp_ns'] = target + 1
    elif name == 'stale_receive':
        for p in points: p['odom_receive_ns'] = snapshot['sample_ns'] - contract['odom_age_ns'] - 1
    elif name == 'missing_dual_history': snapshot['held_history'] = [e for e in snapshot['held_history'] if e['channel'] == 0]
    elif name == 'future_receive':
        for p in points: p['odom_receive_ns'] = snapshot['sample_ns'] + 1
    point, scanned = a.select_frame(points, snapshot, target, contract, generation)
    need(point is None, 'negative not rejected: ' + name)
    negative.append(dict(case=name, rejected=True, scanned=scanned))
need(all(sha(p) == h for p, h in inputs.items()), 'read-only audit')
output = dict(schema='activation-causal-parent-feasibility/v1', passed=True,
              passed_semantics='offline causal availability and original forward state-error gate only; no runtime revalidation or predicted acceptance',
              actual_parent_case_passed=False, activation_prefixes=100, history_capacity=32,
              older_raw_odom_selected=sum(r['selected_raw_odom_is_older'] for r in rows),
              maximum_frames_scanned=max(r['scanned'] for r in rows),
              maximum_abs_state_error=[max(abs(r['full_state_error'][i]) for r in rows) for i in range(6)],
              rows=rows, negative_boundaries=negative, input_sha256_before=inputs, input_sha256_after=inputs,
              actual_parent_experiment_not_rewritten=True, no_ROS_process_started=True,
              stage_qualified=False, execute_qualified=False, research_conclusion=False)
with (D / 'offline/parent_causal_feasibility_v1.json').open('x') as f:
    json.dump(output, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
print(json.dumps({k: output[k] for k in ['passed', 'activation_prefixes', 'older_raw_odom_selected', 'maximum_frames_scanned', 'maximum_abs_state_error']}))
