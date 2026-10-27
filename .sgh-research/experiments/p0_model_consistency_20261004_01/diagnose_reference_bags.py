"""Read old pilot evidence, preserve hashes, separate active tracking and standby."""
from pathlib import Path
import sys, json, math, re
from collections import Counter
ROOT = Path('/home/trevor/USV')
sys.path.insert(0, str(ROOT / 'usv_mpc_ws/scripts'))
import check_p0_contract as c

result = []
for run in ['p0_contract_straight_20261004_03', 'p0_contract_left_20261004_01', 'p0_contract_right_20261004_01']:
    exp = ROOT / '.sgh-research/experiments' / run
    bag = ROOT / 'data/sim_bags' / run
    before = c.hash_bag(bag)
    records, _, _ = c.read_bag(bag, c.Config())
    groups = {key: [r for r in records if r.topic == value] for key, value in c.DEFAULT_TOPICS.items()}
    nonempty = [r for r in groups['path'] if len(r.payload['poses']) >= 2]
    assert nonempty
    first_path = nonempty[0]
    clear = next((r for r in groups['path'] if r.bag_ns > first_path.bag_ns and len(r.payload['poses']) < 2), None)
    end = nonempty[-1].payload['poses'][-1]['pose']['position']
    profiles = [r for r in groups['profile'] if r.payload['data']]
    speeds = [v for r in profiles for v in r.payload['data'][::4]]
    def valid_states(start, stop):
        return [r for r in groups['state'] if r.payload['valid'] and start <= r.bag_ns < stop]
    def describe(states):
        vectors = [r.payload['state_6'] for r in states]
        return {'count': len(vectors), 'u_m_s': c.distribution([s[3] for s in vectors]),
                'v_m_s': c.distribution([s[4] for s in vectors]),
                'body_speed_m_s': c.distribution([math.hypot(s[3], s[4]) for s in vectors]),
                'endpoint_distance_m': c.distribution([math.hypot(s[0]-end['x'], s[1]-end['y']) for s in vectors])}
    boundary = clear.bag_ns if clear else records[-1].bag_ns+1
    closest = min(groups['state'], key=lambda r: abs(r.bag_ns-boundary)) if clear else None
    actions_after = [r.payload for r in groups['applied'] if r.bag_ns >= boundary]
    cycles_after = [r.payload for r in groups['cycle'] if r.bag_ns >= boundary]
    loglines = (exp / 'logs/launch.log').read_text(errors='replace').splitlines()
    completed = [line for line in loglines if '所有航点任务已完成' in line]
    failure_lines = [line for line in loglines if '未能生成有效参考路径' in line or '等待有效航点' in line]
    out = {'run_id': run, 'profile_columns': ['u_ref','kappa','r_ref','relative_profile_time'],
           'profile_u_m_s': c.distribution(speeds), 'first_path_clear_bag_ns': boundary if clear else None,
           'first_path_clear_poses': len(clear.payload['poses']) if clear else None,
           'active_path_window': describe(valid_states(first_path.bag_ns, boundary)),
           'after_first_path_clear': describe(valid_states(boundary, records[-1].bag_ns+1)),
           'nearest_clear_state_bag_offset_ms': (closest.bag_ns-boundary)/1e6 if closest else None,
           'nearest_clear_state': closest.payload['state_6'] if closest else None,
           'nearest_clear_endpoint_distance_m': math.hypot(closest.payload['state_6'][0]-end['x'], closest.payload['state_6'][1]-end['y']) if closest else None,
           'after_clear_control_sources': dict(Counter(p['control_source'] for p in actions_after)),
           'after_clear_cycle_reasons': dict(Counter(p.get('reason', p.get('state_reason','unknown')) for p in cycles_after)),
           'planner_completion_log_count': len(completed), 'planner_completion_first_log': completed[0] if completed else None,
           'planner_failure_or_wait_log_count': len(failure_lines), 'bag_hashes': before,
           'raw_bag_unchanged': before == c.hash_bag(bag),
           'scope': 'Bag receive timestamps for event ordering only; raw state snapshots, not frozen mixed solver states. No exact actual reference matrix or actuator acknowledgment.'}
    assert out['raw_bag_unchanged']
    result.append(out)
target = ROOT / '.sgh-research/experiments/p0_model_consistency_20261004_01/reference_bag_diagnostics.json'
assert not target.exists()
target.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
print(json.dumps([{'run_id': r['run_id'], 'active_u_max': r['active_path_window']['u_m_s']['max'],
                  'active_speed_max': r['active_path_window']['body_speed_m_s']['max'],
                  'clear_endpoint_distance_m': r['nearest_clear_endpoint_distance_m'],
                  'after_clear_sources': r['after_clear_control_sources'],
                  'planner_completion_logs': r['planner_completion_log_count']} for r in result]))
