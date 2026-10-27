#!/usr/bin/env python3
"""Hardened RNW table admission (batch 117, S1 per the batch-115 review R115-07).

Pure functions. Rejects BEFORE any spawn: missing hold, resume before hold,
wrong order, duplicate actions, unregistered actions, clause keys or VALUES
wrong, parameter-domain violations, observation/termination-window rules.
Legal positives must pass; every rejection is a named assertion."""

FAMILY = 'T2A-gen-resume-new-window'
TABLE_KEYS = {'schema', 'run_id', 'case', 'contract_sha256', 'actions', 'clauses'}
CLAUSE_SPEC = {  # exact values, not just keys
    'resume_requires_new_window': True,
    'old_candidate_must_not_revive': True,
    'pause_confirm_ns': 400000000,
}
ACTION_SPEC = {
    'clock_hold': {'parameters': {'mode': 'silent', 'duration_ms': 1200},
                   'trigger': {'phase': 'after_grant_ms', 'delay_ms': 1200, 'job_id': 0}},
    'clock_resume': {'parameters': {},  # B2' pairing mapping replaces the advance parameter
                     'trigger': {'phase': 'after_grant_ms', 'delay_ms': 2700, 'job_id': 0}},
    'driver_shutdown_request': {'parameters': {},
                                'trigger': {'phase': 'after_grant_ms', 'delay_ms': 9000, 'job_id': 0}},
}
REQUIRED_ORDER = ['clock_hold', 'clock_resume']  # termination optional but must be last

def validate_table(table, context):
    """Returns a list of rejection strings; empty list == admitted."""
    r = []
    if not isinstance(table, dict) or set(table) != TABLE_KEYS:
        r.append('table_exact_fields')
        return r
    if table.get('schema') != 'M4-t2-action-table-v1' or table.get('case') != FAMILY:
        r.append('table_schema_or_case')
        return r
    if table.get('run_id') != context.get('run_id') or table.get('contract_sha256') != context.get('contract_sha256'):
        r.append('table_identity_binding')
    actions = table.get('actions')
    if not isinstance(actions, list) or not (2 <= len(actions) <= 3):
        r.append('action_population_2_to_3')
        return r
    names = [a.get('action') for a in actions if isinstance(a, dict)]
    # sequence completeness: hold must exist and precede resume (R115-07 negatives)
    if 'clock_hold' not in names:
        r.append('missing_hold')
    if 'clock_resume' not in names:
        r.append('missing_resume')
    if names.count('clock_hold') > 1 or names.count('clock_resume') > 1 \
       or any(names.count(n) > 1 for n in set(names)):
        r.append('duplicate_action')
    if 'clock_hold' in names and 'clock_resume' in names:
        if names.index('clock_resume') < names.index('clock_hold'):
            r.append('resume_before_hold')
    if names != [n for n in names if n in REQUIRED_ORDER] + \
       [n for n in names if n not in REQUIRED_ORDER]:
        r.append('action_order_not_declared')
    if names[:2] != REQUIRED_ORDER:
        r.append('required_sequence_not_exact_prefix')
    delays = []
    for a in actions:
        if not isinstance(a, dict) or set(a) != {'id', 'action', 'parameters', 'trigger'}:
            r.append('action_shape')
            continue
        spec = ACTION_SPEC.get(a['action'])
        if spec is None:
            r.append('unregistered_action:' + str(a['action']))
            continue
        if a['parameters'] != spec['parameters']:
            r.append('parameters_domain:' + str(a['action']))
        if a['trigger'] != spec['trigger']:
            r.append('trigger_domain:' + str(a['action']))
        delays.append(a['trigger'].get('delay_ms', -1))
    if delays != sorted(delays):
        r.append('trigger_delay_not_monotonic')
    # clause VALUES (R115-07: values, not just the key set)
    clauses = table.get('clauses')
    if not isinstance(clauses, dict) or set(clauses) != set(CLAUSE_SPEC):
        r.append('clause_set')
    else:
        for k, v in CLAUSE_SPEC.items():
            if clauses.get(k) != v:
                r.append('clause_value:' + k)
    return r
