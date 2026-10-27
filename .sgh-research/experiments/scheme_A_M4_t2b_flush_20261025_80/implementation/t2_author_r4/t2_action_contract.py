"""Frozen T2 action-table / command / receipt contract. No ROS initialisation.

Batch 71 (S2). The same module is consumed at the four admission points:
registration preflight (entry), Driver parameter assembly, the Fixture
manifest/arm gate, and the T2 audit. A registration without T2 clauses (normal
or W scope) can never carry an action table; candidate forgery never enters
the Fixture because no candidate action exists in the vocabulary.

Semantics fixed by the 69th-batch review:
  * job_received only proves the Job was received/queued.
  * solve_active (capability active_job==K, no candidate for K yet) is the
    in-flight trigger; ready_window (an accepted candidate_registration) is a
    separate ready-window phase and must never be named "in-flight".
"""
from pathlib import Path
import hashlib
import json

TABLE_SCHEMA = 'M4-t2-action-table-v1'
COMMAND_SCHEMA = 'M4-t2-action-command-v1'
RECEIPT_TYPE = 't2_action_executed'
REGISTRATION_SCHEMA = 'M4-owned-t2-scenario-run-v1'
ORDINARY_SCOPE = 'M4_owned_local_nominal_only_v1'
T2_BOUNDARY_SCOPE = 'M4_owned_t2_boundary_diagnostic_v1'
V3_CONTRACT_SHA = '19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a'

FAMILIES = ['T2A-clock-freeze', 'T2B-inflight-clear-replace', 'T2C-driver-shutdown-interleave']
PHASES = {
    'after_grant_ms': 'Driver-relative time after the execute grant; no Job binding',
    'job_received': 'worker source job_received row for the bound Job; queued only, NOT in-flight',
    'solve_active': 'worker capability row with active_job==Job and no candidate row for it yet; in-flight',
    'ready_window': 'regulator candidate_registration accepted for the bound Job; result already admitted',
}
CLOCK_HOLD_MODES = ['same_stamp', 'silent']
# Executed by the existing Fixture writers; the shutdown request is the one
# Driver-side action (it is the Driver's own close stimulus).
FIXTURE_ACTIONS = ['clock_hold', 'clock_resume', 'path_clear', 'path_replace']
DRIVER_ACTIONS = ['driver_shutdown_request']
ACTIONS = {
    'clock_hold': {'executor': 'fixture', 'params': {'mode', 'duration_ms'}},
    'clock_resume': {'executor': 'fixture', 'params': {'advance_ms'}},
    'path_clear': {'executor': 'fixture', 'params': set()},
    'path_replace': {'executor': 'fixture', 'params': {'points', 'speed_m_s'}},
    'driver_shutdown_request': {'executor': 'driver', 'params': {'reason'}},
}
FAMILY_ACTIONS = {
    'T2A-clock-freeze': ['clock_hold', 'clock_resume'],
    'T2B-inflight-clear-replace': ['path_clear', 'path_replace'],
    'T2C-driver-shutdown-interleave': ['driver_shutdown_request'],
}
FAMILY_PHASES = {
    'T2A-clock-freeze': ['after_grant_ms'],
    'T2B-inflight-clear-replace': ['solve_active', 'ready_window', 'job_received'],
    'T2C-driver-shutdown-interleave': ['ready_window'],
}
MAX_ACTIONS = 4


def require(value, message):
    if not value:
        raise AssertionError(message)


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded_json(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()


EVIDENCE_SOURCE_ROLE = {'job_received': 'worker', 'solve_active': 'worker',
                        'ready_window': 'regulator', 'after_grant_ms': 'driver'}


def make_evidence(phase, job, event_ns, source_role):
    """The single complete trigger-evidence constructor (R0).

    event_ns is the REAL Source event time; a Driver poll time must never be
    passed here. source_role is bound by the phase via EVIDENCE_SOURCE_ROLE."""
    require(phase in EVIDENCE_SOURCE_ROLE, 'unknown evidence phase')
    require(source_role == EVIDENCE_SOURCE_ROLE[phase], 'phase/source_role binding')
    require(type(event_ns) is int and event_ns > 0, 'real event time required')
    return {'phase': phase, 'job': job, 'observed_ns': event_ns, 'source_role': source_role}


def verify_budgets_unchanged(config):
    """The T2 interface may not relax any frozen budget (69th-batch clause)."""
    expected = {'deadline_ns': 150000000, 'hold_ns': 600000000,
                'active_watchdog_ns': 1000000000,
                'worker_capability_receipt_timeout_ns': 600000000,
                'clock_pause_confirm_ns': 400000000, 'shutdown_grace_ns': 2500000000}
    for key, value in expected.items():
        require(config.get(key) == value, 'T2 must not relax frozen budget: ' + key)


def _validate_trigger(trigger, family, index):
    require(isinstance(trigger, dict) and set(trigger) == {'phase', 'job_id', 'delay_ms'},
            'action %d trigger exact fields' % index)
    require(trigger['phase'] in FAMILY_PHASES[family],
            'action %d phase not admitted for %s (job_received proves queued only)' % (index, family))
    require(type(trigger['delay_ms']) is int and 0 <= trigger['delay_ms'] <= 2000,
            'action %d delay outside finite bound' % index)
    if trigger['phase'] == 'after_grant_ms':
        require(trigger['job_id'] == 0, 'after_grant_ms carries no Job binding')
    else:
        require(type(trigger['job_id']) is int and trigger['job_id'] >= 1,
                'action %d requires a positive bound Job' % index)


def _validate_parameters(name, parameters, index):
    require(isinstance(parameters, dict) and set(parameters) == ACTIONS[name]['params'],
            'action %d parameter exact fields' % index)
    if name == 'clock_hold':
        require(parameters['mode'] in CLOCK_HOLD_MODES, 'clock_hold mode domain')
        require(type(parameters['duration_ms']) is int and 50 <= parameters['duration_ms'] <= 2000,
                'clock_hold duration outside finite bound')
    elif name == 'clock_resume':
        require(type(parameters['advance_ms']) is int and 0 <= parameters['advance_ms'] <= 1000,
                'clock_resume advance outside finite bound')
    elif name == 'path_replace':
        require(type(parameters['points']) is int and 2 <= parameters['points'] <= 201,
                'path_replace points domain')
        require(parameters['speed_m_s'] == .05, 'path_replace stays in the calibrated .05 domain')
    elif name == 'driver_shutdown_request':
        require(isinstance(parameters['reason'], str) and 0 < len(parameters['reason']) <= 64,
                'driver_shutdown_request reason domain')


def validate_table(table, context):
    """Entry-admission validation; context pins run/case/contract identity."""
    require(isinstance(table, dict) and set(table) == {'schema', 'run_id', 'case', 'contract_sha256', 'actions', 'clauses'},
            'action table exact top-level fields')
    require(table['schema'] == TABLE_SCHEMA, 'action table schema')
    family = table['case']
    require(family in FAMILIES, 'unknown T2 scenario family')
    require(table['run_id'] == context['run_id'], 'table run binding')
    V4_CONTRACT_SHA = '3a8451d5172423adbef955d78c8550d67bbeec4582a80bd9ba69028b867b9f06'
    require(table['contract_sha256'] == context['contract_sha256'] and
            table['contract_sha256'] in (V3_CONTRACT_SHA, V4_CONTRACT_SHA),
            'table contract binding must stay a frozen contract (v3 or v4 for boundary)')
    actions = table['actions']
    require(isinstance(actions, list) and 1 <= len(actions) <= MAX_ACTIONS, 'finite action population')
    seen = set()
    hold_open = False
    for index, row in enumerate(actions, 1):
        require(isinstance(row, dict) and set(row) == {'id', 'action', 'parameters', 'trigger'},
                'action %d exact fields' % index)
        require(isinstance(row['id'], str) and row['id'] == 'a%d' % index, 'action ids are a1..aN in declared order')
        require(row['id'] not in seen, 'duplicate action id')
        seen.add(row['id'])
        name = row['action']
        require(isinstance(name, str) and 'candidate' not in name.lower(),
                'candidate forgery does not enter the Fixture')
        require(name in ACTIONS, 'unknown action: %r' % name)
        require(name in FAMILY_ACTIONS[family], 'action %s not admitted for %s' % (name, family))
        _validate_parameters(name, row['parameters'], index)
        _validate_trigger(row['trigger'], family, index)
        if name == 'clock_hold':
            hold_open = True
        elif name == 'clock_resume':
            require(hold_open, 'clock_resume must follow a clock_hold')
            hold_open = False
    require(not hold_open or family == 'T2A-clock-freeze', 'trailing clock_hold stays family-local')
    shutdowns = [row for row in actions if row['action'] == 'driver_shutdown_request']
    require(len(shutdowns) <= 1, 'at most one shutdown request')
    if shutdowns:
        require(actions[-1]['action'] == 'driver_shutdown_request', 'shutdown request must be the final action')
    _validate_clauses(table['clauses'], family)
    return table


def _validate_clauses(clauses, family):
    """Family timing/failure clauses consumed by the run-time audit."""
    require(isinstance(clauses, dict), 'clauses required')
    if family == 'T2A-clock-freeze':
        require(set(clauses) == {'receipt_stale_ns', 'pause_confirm_ns', 'same_stamp_keeps_receipt_fresh',
                                 'silent_exceeds_receipt_stale', 'old_candidate_must_not_revive',
                                 'resume_requires_new_window'},
                'T2A clause exact fields')
        require(clauses['receipt_stale_ns'] == 100000000, 'clock receipt stale bound is 100 ms')
        require(clauses['pause_confirm_ns'] == 400000000, 'pause confirm bound is 400 ms')
        for key in ('same_stamp_keeps_receipt_fresh', 'silent_exceeds_receipt_stale',
                    'old_candidate_must_not_revive', 'resume_requires_new_window'):
            require(clauses[key] is True, 'T2A clause must hold: ' + key)
    elif family == 'T2B-inflight-clear-replace':
        require(set(clauses) == {'job_deadline_ns_after_origin', 'deadline_must_not_extend',
                                 'missed_window_is_registered_failure', 'stale_result_reject_reasons',
                                 'expiry_or_worker_terminal_is_not_task_rejection'},
                'T2B clause exact fields')
        require(clauses['job_deadline_ns_after_origin'] == 150000000, 'Job deadline stays 150 ms')
        require(clauses['deadline_must_not_extend'] is True and clauses['missed_window_is_registered_failure'] is True,
                'T2B deadline clauses must hold')
        require(clauses['stale_result_reject_reasons'], 'stale reject reasons must be registered')
        require(all(isinstance(r, str) for r in clauses['stale_result_reject_reasons']),
                'stale reject reasons are strings')
        require(clauses['expiry_or_worker_terminal_is_not_task_rejection'] is True,
                'expiry/worker-terminal must not masquerade as task rejection')
    else:
        require(set(clauses) == {'ordering', 'stop_must_precede_activation_guard',
                                 'guard_rejects_target', 'full_exit_and_storage_required'},
                'T2C clause exact fields')
        require(clauses['ordering'] == 'ready_commit<request<=stopping_observed<=activation_guard',
                'T2C ordering clause is fixed')
        for key in ('stop_must_precede_activation_guard', 'guard_rejects_target', 'full_exit_and_storage_required'):
            require(clauses[key] is True, 'T2C clause must hold: ' + key)


def validate_command(command, table, executed_ids):
    """Driver->executor command admission; executed_ids enforces create-once order."""
    require(isinstance(command, dict) and set(command) == {'schema', 'run_id', 'contract_sha256',
                                                           'action_id', 'sequence', 'trigger'},
            'command exact fields')
    require(command['schema'] == COMMAND_SCHEMA, 'command schema')
    require(command['run_id'] == table['run_id'] and command['contract_sha256'] == table['contract_sha256'],
            'command identity binding')
    require(command['action_id'] in {row['id'] for row in table['actions']}, 'command action not in frozen table')
    require(command['action_id'] not in executed_ids, 'duplicate action command')
    require(command['sequence'] == len(executed_ids) + 1, 'commands execute in declared table order')
    entry = next(row for row in table['actions'] if row['id'] == command['action_id'])
    require(table['actions'][len(executed_ids)]['id'] == command['action_id'], 'commands follow the declared table order')
    require(isinstance(command['trigger'], dict) and set(command['trigger']) == {'phase', 'job', 'observed_ns', 'source_role'},
            'command trigger evidence exact fields')
    require(command['trigger']['phase'] == entry['trigger']['phase'], 'command phase matches the frozen trigger')
    require(command['trigger']['source_role'] in ('worker', 'regulator', 'driver'), 'trigger source role domain')
    require(type(command['trigger']['observed_ns']) is int and command['trigger']['observed_ns'] > 0,
            'trigger monotonic evidence required')
    if entry['trigger']['job_id']:
        require(isinstance(command['trigger']['job'], dict) and command['trigger']['job'].get('job_id') == entry['trigger']['job_id'],
                'command Job binding matches the frozen target')
    else:
        require(command['trigger']['job'] is None, 'after_grant_ms carries no Job binding')
    return command


def check_receipts(table, receipts, regulator_rows, commands=None):
    """Post-run accounting: executor receipts stay separate from Regulator
    state-change rows and are correlated by action id, Job binding and
    monotonic time. The test flush pad is never an acknowledgement."""
    by_id = {}
    declared = {row['id'] for row in table['actions']}
    for row in receipts:
        require(isinstance(row, dict) and row.get('type') == RECEIPT_TYPE, 'foreign row in receipt stream')
        action_id = row.get('action_id')
        require(action_id in declared, 'receipt for an action outside the frozen table: ' + str(action_id))
        require(action_id not in by_id, 'duplicate executed receipt: ' + str(action_id))
        by_id[action_id] = row
    if commands is not None:
        require({c['action_id'] for c in commands} == declared, 'command set must equal the frozen table')
        for record in commands:
            row = by_id[record['action_id']]
            require(row.get('command_sha256') == record['command_sha256'],
                    'receipt does not bind the exact commanded bytes: ' + record['action_id'])
    ordered = []
    last_ns = 0
    for entry in table['actions']:
        row = by_id.get(entry['id'])
        require(row is not None, 'missing executed receipt: ' + entry['id'])
        require(set(row) >= {'type', 'action_id', 'command_sha256', 'executed_ns', 'trigger'},
                'receipt fields: ' + entry['id'])
        require(type(row['executed_ns']) is int and row['executed_ns'] > last_ns,
                'receipts must advance monotonically in table order: ' + entry['id'])
        last_ns = row['executed_ns']
        require(row['trigger'].get('observed_ns', 0) < row['executed_ns'],
                'execution must follow its trigger: ' + entry['id'])
        ordered.append({'action_id': entry['id'], 'executed_ns': row['executed_ns'],
                        'command_sha256': row['command_sha256']})
    # Regulator rows are a separate stream; only their ordering relative to the
    # receipts is checked here. Family semantics live in the audit clauses.
    regulator_ns = [row.get('processed_ns', row.get('submit_commit_ns', 0)) for row in regulator_rows]
    return {'receipts_complete': True, 'ordered': ordered,
            'regulator_rows_separate_stream': all(ns not in [r['executed_ns'] for r in ordered] for ns in regulator_ns)}


def require_normal_scope_unarmed(registration):
    """A non-T2 registration must not carry any action-table capability."""
    for key in ('action_table', 'action_table_sha256', 't2_case'):
        require(key not in registration, 'normal/W registration cannot carry T2 capability: ' + key)


def fixture_action_parameters(registration, command_dir, table_path):
    """The exact Fixture ROS parameters arming the action channel."""
    require(registration['schema'] == REGISTRATION_SCHEMA, 'T2 registration schema')
    table = json.loads(Path(table_path).read_bytes())
    validate_table(table, {'run_id': registration['run_id'], 'case': registration['case'],
                           'contract_sha256': registration['contract_sha256']})
    require(pin(table_path)['sha256'] == registration['action_table_sha256'], 'action table pin mismatch')
    return {'t2_case': registration['case'],
            't2_action_table_file': str(table_path),
            't2_action_table_sha256': registration['action_table_sha256'],
            't2_command_dir': str(command_dir)}
