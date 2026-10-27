#!/usr/bin/env python3
"""Single physical admission rule source (batch 126; fixes F124-03 / R-RNW-03).

Batch 119 shipped TWO rule sets: the hardened `rnw_admission_v2.validate_table`
used only by the freeze helper, and a weaker `t2b_gen_admission.validate_table`
that the Driver's pre-spawn preflight actually called. Three invalid tables
(all-false clauses, missing hold, resume-before-hold) were accepted by the real
Driver entry while the hardened copy rejected them.

This module is now the ONLY place where a T2A-gen-resume-new-window action table
is judged. Both the freeze script and the Driver preflight import it, and the
module records its own absolute path + sha so the identity can be checked from
either side.

Non-RNW families keep their existing rules unchanged: this module refuses to
judge them and says so, rather than silently widening its scope.
"""
import hashlib
from pathlib import Path

FAMILY = 'T2A-gen-resume-new-window'
TABLE_KEYS = {'schema', 'run_id', 'case', 'contract_sha256', 'actions', 'clauses'}
TABLE_SCHEMA = 'M4-t2-action-table-v1'

# Clause VALUES, not just the key set (R115-07).
CLAUSE_SPEC = {
    'resume_requires_new_window': True,
    'old_candidate_must_not_revive': True,
    'pause_confirm_ns': 400000000,
}

ACTION_SPEC = {
    'clock_hold': {'parameters': {'mode': 'silent', 'duration_ms': 1200},
                   'trigger': {'phase': 'after_grant_ms', 'delay_ms': 1200, 'job_id': 0}},
    'clock_resume': {'parameters': {},
                     'trigger': {'phase': 'after_grant_ms', 'delay_ms': 2700, 'job_id': 0}},
    'driver_shutdown_request': {'parameters': {},
                                'trigger': {'phase': 'after_grant_ms', 'delay_ms': 9000, 'job_id': 0}},
}
REQUIRED_ORDER = ['clock_hold', 'clock_resume']   # termination optional, must be last
ACTION_KEYS = {'id', 'action', 'parameters', 'trigger'}
MIN_ACTIONS, MAX_ACTIONS = 2, 3


def module_identity():
    raw = Path(__file__).resolve().read_bytes()
    return {'path': str(Path(__file__).resolve()),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'family_judged': FAMILY}


def judges(family):
    """True iff this module is the authority for that family."""
    return family == FAMILY


def validate_table(table, context):
    """Return a list of named rejection reasons; empty list == admitted.

    Pure function: no I/O, no subprocess, no side effects. Every rejection is a
    string so a caller can assert on the specific rule that fired.
    """
    r = []
    if not isinstance(table, dict):
        return ['table_not_an_object']
    if set(table) != TABLE_KEYS:
        return ['table_exact_fields']
    if table.get('schema') != TABLE_SCHEMA:
        return ['table_schema']
    if table.get('case') != FAMILY:
        return ['table_case_not_governed_by_this_module']

    # identity binding against the caller-supplied context
    if table.get('run_id') != context.get('run_id'):
        r.append('table_identity_run_id')
    if table.get('contract_sha256') != context.get('contract_sha256'):
        r.append('table_identity_contract')

    actions = table.get('actions')
    if not isinstance(actions, list) or not (MIN_ACTIONS <= len(actions) <= MAX_ACTIONS):
        return r + ['action_population_%d_to_%d' % (MIN_ACTIONS, MAX_ACTIONS)]

    # shape first: an unshaped action cannot be named later
    for a in actions:
        if not isinstance(a, dict) or set(a) != ACTION_KEYS:
            return r + ['action_shape']

    names = [a.get('action') for a in actions]
    if 'clock_hold' not in names:
        r.append('missing_hold')
    if 'clock_resume' not in names:
        r.append('missing_resume')
    if len(set(names)) != len(names):
        r.append('duplicate_action')
    for n in names:
        if n not in ACTION_SPEC:
            r.append('unregistered_action:' + str(n))
    if 'clock_hold' in names and 'clock_resume' in names:
        if names.index('clock_resume') < names.index('clock_hold'):
            r.append('resume_before_hold')
    if names[:len(REQUIRED_ORDER)] != REQUIRED_ORDER:
        r.append('required_sequence_not_exact_prefix')

    delays = []
    for a in actions:
        spec = ACTION_SPEC.get(a['action'])
        if spec is None:
            continue
        if a['parameters'] != spec['parameters']:
            r.append('parameters_domain:' + a['action'])
        if a['trigger'] != spec['trigger']:
            r.append('trigger_domain:' + a['action'])
        delay = (a['trigger'] or {}).get('delay_ms', -1)
        delays.append(delay if isinstance(delay, int) else -1)
    if delays != sorted(delays):
        r.append('trigger_delay_not_monotonic')

    clauses = table.get('clauses')
    if not isinstance(clauses, dict) or set(clauses) != set(CLAUSE_SPEC):
        r.append('clause_set')
    else:
        for k, expected in CLAUSE_SPEC.items():
            # exact value, and the type must match: `True == 1` must not admit
            if clauses.get(k) != expected or type(clauses.get(k)) is not type(expected):
                r.append('clause_value:' + k)
    return r
