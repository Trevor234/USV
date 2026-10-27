#!/usr/bin/env python3
"""Generate the W2 registry and registration from the frozen build.

Every field written here is consumed by code that already exists — the Driver's
`expected` clauses, the Regulator's `diagnostic_case` admission, and the
audit's identity chain — rather than being documentation-only JSON. That is the
62-review's §5.2 requirement: "新字段必须由最终Driver/审计实际消费".

Refuses to overwrite an existing registration: a frozen run's input identity is
immutable, and silently replacing it would let a later stimulus claim an earlier
registration's identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
AUTHOR = PKG / 'implementation' / 'w2_author'
EVIDENCE = PKG / 'evidence'
OUT = PKG / 'implementation'
BUILD = EVIDENCE / 'freeze_and_build' / 'cmake_build'

SCOPE = 'M4_owned_diagnostic_worker_only_v1'
# The Driver's frozen evidence marker. Registration must reproduce it exactly.
INDEX_SHA = 'd1a9f0e2b7c4a8536e0f2b9d4c7a1e5836b0d9f2c4a7e1b8369d0c5f2a8e4b71'


def _recorder_provenance(binary: str) -> str:
    """The experiment package a reused ELF actually lives under."""
    p = Path(binary)
    parts = p.parts
    experiments = Path('/home/trevor/USV/.sgh-research/experiments')
    try:
        idx = parts.index(experiments.name)
        return parts[idx + 1]
    except ValueError:
        return str(p.parent)


def _index_path() -> str:
    """The index artefact the marker names, as the 56 package records it."""
    return str(BATCH56 / 'implementation' / 'p1_execution_contract_v4.json')
CASE = 'W2-native-boundary-hold'

BATCH56 = Path('/home/trevor/USV/.sgh-research/experiments/'
               'scheme_A_M4_diagnostic_worker_20261021_56')


def pin(path: Path) -> dict:
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write_create_only(path: Path, value: dict) -> None:
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def main() -> int:
    build = json.loads((EVIDENCE / 'freeze_and_build' / 'freeze_and_build_v1.json').read_text())
    if not build['passed']:
        print('freeze/build did not pass; refusing to register')
        return 2

    registry_path = OUT / 'selected_runtime_registry_w2_v1.json'
    registration_path = OUT / 'W2_registration_v1.json'
    for p in (registry_path, registration_path):
        if p.exists():
            print('refusing to overwrite existing %s' % p)
            return 2

    contract = Path(build['contract']['path'])
    topics = BATCH56 / 'implementation' / 'm4_topics_v1.json'
    source_bundle = Path(build['source_bundle']['path'])

    # ── registry: the ELF identity chain for this build ──────────────
    roles = {}
    for role in ('regulator', 'worker', 'fixture'):
        entry = build['roles'][role]
        roles[role] = {
            'binary': entry['binary'],
            'binary_sha256': entry['sha256'],
            'source_bundle': {'path': str(source_bundle),
                              'sha256': build['source_bundle']['sha256']},
        }
    # The Recorder is a reused, separately registered ELF from the 56 package.
    # It is recorded by reference, not re-described as part of this build.
    old_registry = json.loads(
        (BATCH56 / 'implementation' / 'selected_runtime_registry_v1.json').read_text())
    rec = old_registry['roles']['recorder']
    roles['recorder'] = {
        'binary': rec['binary'],
        'binary_sha256': rec['binary_sha256'],
        'source_bundle': {'path': rec['source_bundle']['path'],
                          'sha256': rec['source_bundle']['sha256']},
        # The Recorder is NOT part of this build. Record where it actually came
        # from, derived from the path the 56 registry pins — not a guessed label.
        'reused_from': _recorder_provenance(rec['binary']),
    }

    registry = {
        'schema': 'M4-owned-runtime-registry/v2',
        'scope': SCOPE,
        'execute_qualified': False,
        'production_physical_release_enabled': False,
        'contract_sha256': pin(contract)['sha256'],
        'driver': build['driver']['path'],
        'driver_tool_sha256': build['driver']['sha256'],
        'regulator_source': str(AUTHOR / 'observer' / 'src' / 'shadow' /
                                'regulator_owned_execute.cpp'),
        'regulator_source_sha256': pin(
            AUTHOR / 'observer' / 'src' / 'shadow' / 'regulator_owned_execute.cpp')['sha256'],
        'source_scope': str(AUTHOR),
        'source_bundle_sha256': build['source_bundle']['sha256'],
        'roles': roles,
        'evidence_marker': 'W2-registration-2026-10-23',
        # Consumed by the Driver's live `/proc/<pid>/maps` check before grant.
        'acados_runtime': build['acados_runtime'],
    }
    write_create_only(registry_path, registry)

    # ── registration: the stimulus and its expected end state ────────
    registration = {
        'schema': 'M4-owned-diagnostic-run-v1',
        'scope': SCOPE,
        'case': CASE,
        'audit_tool': {'path': str(AUTHOR / 'audit_w2.py'), 'sha256': pin(AUTHOR / 'audit_w2.py')['sha256']},
        'launch_tool': {'path': str(OUT / 'launch_owned_once.py'), 'sha256': pin(OUT / 'launch_owned_once.py')['sha256']},
        'run_id': 'M4_diagnostic_W2_20261023_66_01',
        'boundary': (
            'The Worker reaches the registered inner call boundary and waits for a '
            'single private-pipe release. The Driver observes at least two complete '
            'Regulator business ticks after that entry and then writes one frame. By '
            'then the Job\'s original 150 ms deadline has passed, so the final guard '
            'refuses the C call: the release is verified, the Job is expired, and the '
            'target Job\'s native call count stays zero.'),
        'contract': str(contract),
        'contract_sha256': pin(contract)['sha256'],
        # The Driver pins this to its own INDEX_SHA constant: the freeze
        # evidence marker, NOT the contract's own hash.
        'index': _index_path(),
        'index_sha256': INDEX_SHA,
        'registry': str(registry_path),
        'registry_sha256': pin(registry_path)['sha256'],
        'topics': str(topics),
        'topics_sha256': pin(topics)['sha256'],
        'fault_injection_enabled': True,
        'production_physical_release_enabled': False,
        'automatic_retries': 0,
        'max_seconds': 45,
        'outer_timeout_seconds': 90,
        'domain_id': 120,
        'declared_exceptions': [],
        'old_normal_or_fault_qualifications_transferred': False,
        'M4_stage_qualified': False,
        'F6_qualified': False,
        'P1_qualified': False,
        # The Driver requires out.parent == <implementation>/runs.
        'output': str(OUT / 'runs' / 'W2_01'),
        # The stimulus. job_id/ordinal select the *target*; the Driver binds the
        # pipe to exactly this pair and the Worker refuses any other frame.
        'w2_release': {
            'job_id': 2,
            'ordinal': 1,
            'nonce': 20261023,
            'wait_budget_ns': 1500000000,
            'ticks_before_release': 2,
        },
        'expected': {
            # Only the Worker's exit code is registration-specific. All other
            # role checks stay as the ordinary rules require.
            'w2_exit_codes': {'worker': 2},
            'w2_worker_signals': ['SIGINT'],
            'w2_isolation_reason': 'fatal_capability',
            'w2_terminal_reasons': ['w2_boundary_expired'],
            'exit_codes': {'fixture': 0, 'recorder': 0, 'regulator': 0, 'worker': 2},
            'signals': {'fixture': ['SIGINT'], 'recorder': ['SIGINT'],
                        'regulator': [], 'worker': ['SIGINT']},
            'transition_reason': 'fatal_capability',
            'target_job_native_calls': 0,
            'target_job_candidate_published': False,
            'target_job_candidate_registered': False,
            'backend_terminal': True,
            'active_job_cleared': True,
            'pending_discard_required': True,
        },
        'two_deadlines': {
            'gate_wait_budget_ns': 1500000000,
            'job_deadline_ns_after_origin': 150000000,
            'gate_window_extends_job_deadline': False,
        },
        'release_preconditions': {
            'capability_lease_ns': 600000000,
            'active_watchdog_ns': 1000000000,
            'release_must_precede_active_watchdog': True,
            'required_complete_ticks_after_entry': 2,
        },
        'channel': {
            'kind': 'private_pipe',
            'driver_holds': 'write_end',
            'worker_inherits': 'read_end',
            'siblings_inherit': 'none',
            'binding_fixed_at_runtime': ['device', 'inode', 'nonce',
                                         'job_id', 'ordinal', 'wait_budget_ns'],
            'static_registration_predicts_inode': False,
        },
    }
    # The Driver does `out.mkdir()` without parents, and asserts the parent is
    # `<implementation>/runs`. Creating that parent is a registration-time duty,
    # not a runtime one, so the first launch cannot fail on a missing directory.
    (OUT / 'runs').mkdir(parents=True, exist_ok=True)
    write_create_only(registration_path, registration)

    print(json.dumps({
        'registry': str(registry_path),
        'registry_sha256': pin(registry_path)['sha256'],
        'registration': str(registration_path),
        'registration_sha256': pin(registration_path)['sha256'],
        'case': CASE,
        'target': registration['w2_release'],
    }, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
