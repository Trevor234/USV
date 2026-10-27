#!/usr/bin/env python3
"""Check already-available policy fields for consistency; no new ROS channel."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent / 'scheme_A_W2_registration_20261023_63'
reg = json.loads((PKG / 'implementation/W2_registration_v1.json').read_text())
contract = json.loads(Path(reg['contract']).read_text())
w = reg['w2_release']
d = reg['two_deadlines']
p = reg['release_preconditions']
c = reg['channel']
e = reg['expected']
checks = {
    'gate_budget_matches_actual_parameter': d['gate_wait_budget_ns'] == w['wait_budget_ns'],
    'job_deadline_matches_pinned_contract': d['job_deadline_ns_after_origin'] == contract['deadline_ns'],
    'gate_does_not_extend_job_deadline': d['gate_window_extends_job_deadline'] is False,
    'complete_tick_requirement_agrees': p['required_complete_ticks_after_entry'] == w['ticks_before_release'] == 2,
    'capability_lease_matches_contract': p['capability_lease_ns'] == contract['worker_capability_receipt_timeout_ns'],
    'active_watchdog_matches_contract': p['active_watchdog_ns'] == contract['active_watchdog_ns'],
    'release_before_watchdog_required': p['release_must_precede_active_watchdog'] is True,
    'channel_roles_agree': c['kind'] == 'private_pipe' and c['driver_holds'] == 'write_end'
        and c['worker_inherits'] == 'read_end' and c['siblings_inherit'] == 'none',
    'dynamic_inode_rule': c['static_registration_predicts_inode'] is False,
    'worker_rc_formats_agree': e['exit_codes']['worker'] == e['w2_exit_codes']['worker'] == 2,
    'worker_signal_formats_agree': e['signals']['worker'] == e['w2_worker_signals'] == ['SIGINT'],
    'isolation_reason_formats_agree': e['transition_reason'] == e['w2_isolation_reason'] == 'fatal_capability',
    'one_finite_attempt': reg['max_seconds'] == 45 and reg['automatic_retries'] == 0,
    'diagnostic_not_physical_release': reg['production_physical_release_enabled'] is False,
}
assert all(checks.values()), checks
report = {'schema': 'W2-registered-policy-static-consistency-v1', 'checks': checks,
          'all_consistent_now': True,
          'existing_contract_parameter_manifest_fields_are_sufficient_for_static_check': True,
          'original_driver_consumes_each_policy_field': False,
          'runtime_release_heartbeat_slots_observed': False,
          'ROS_started': False, 'owned_run_performed': False,
          'note': 'A 1.5s gate maximum does not authorize release after the original 1s watchdog; success still requires release earlier.'}
(ROOT / 'evidence/policy_consistency_v1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'checks': len(checks), 'all_consistent_now': True, 'runtime_observed': False}))
