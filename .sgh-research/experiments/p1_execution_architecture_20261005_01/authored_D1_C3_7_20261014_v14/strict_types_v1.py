"""C3.4-B closed field-domain rules for release evidence (version 1).

These are representation checks; existing identity, causality, source/storage,
deadline and absence checks remain responsible for semantic acceptance. Time
fields use the native signed int64 nanosecond domain; native counts/sequences
use uint64. Process IDs/return codes remain signed. Null is accepted only at
declared observation fields; the case-specific checker verifies unreadness.
"""
from __future__ import annotations
import math

SCHEMA = 'p1-C3.4-exact-field-domains/v1'
I64_MIN, I64_MAX, U64_MAX = -(1 << 63), (1 << 63) - 1, (1 << 64) - 1


def fail(path, domain):
    raise ValueError('field_domain:' + path + ':' + domain)


def int64(value, path, minimum=I64_MIN):
    if type(value) is not int or not minimum <= value <= I64_MAX:
        fail(path, 'exact_int64')
    return value


def uint64(value, path):
    if type(value) is not int or not 0 <= value <= U64_MAX:
        fail(path, 'exact_uint64')
    return value


def boolean(value, path):
    if type(value) is not bool:
        fail(path, 'exact_bool')
    return value


def finite_number(value, path):
    if type(value) not in (int, float):
        fail(path, 'finite_binary64_number')
    try:
        valid = math.isfinite(value)
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        fail(path, 'finite_binary64_number')
    return value


def finite_tree(value, path='$'):
    """Reject exponent overflow even when JSON parse_constant is not invoked."""
    if type(value) is float and not math.isfinite(value):
        fail(path, 'finite_json_number')
    elif type(value) is int and not I64_MIN <= value <= U64_MAX:
        fail(path, 'json_integer_native_64bit_range')
    elif type(value) is dict:
        for key, item in value.items():
            finite_tree(item, path + '.' + str(key))
    elif type(value) is list:
        for i, item in enumerate(value):
            finite_tree(item, path + '[' + str(i) + ']')
    return value


def fields(row, *, counts=(), times=(), bools=(), nullable_times=(), signed=(), path='$', required=True):
    if type(row) is not dict:
        fail(path, 'object')
    groups = ((counts, uint64), (times, lambda v, p: int64(v, p, 0)),
              (bools, boolean), (signed, int64))
    for names, check in groups:
        for name in names:
            if name not in row and not required:
                continue
            if name not in row:
                fail(path + '.' + name, 'required')
            check(row[name], path + '.' + name)
    for name in nullable_times:
        if name not in row:
            if not required:
                continue
            fail(path + '.' + name, 'required')
        if row[name] is not None:
            int64(row[name], path + '.' + name, 0)
    return row


def identity(row, path='$'):
    fields(row, counts=('process_start_ticks', 'start_ticks'),
           signed=('pid', 'ppid', 'pgid', 'sid'), required=False, path=path)


def gate(row):
    fields(row, counts=('release_bytes_count', 'poll_count', 'missing_release_count',
        'released_integrity_verify_count', 'original_freshness_read_count'),
        bools=('release_read_completed', 'release_present_at_last_completed_read',
            'business_policy_changed', 'observation_qualifies_physical_release', 'receipt_io_completed'),
        times=('release_read_start_steady_ns', 'release_read_end_steady_ns'),
        nullable_times=('valid_until_steady_ns', 'validate_now_ns', 'attempt_now_ns',
            'final_freshness_now_ns', 'arm_start_steady_ns', 'arm_end_steady_ns',
            'receipt_io_start_steady_ns', 'receipt_io_end_steady_ns',
            'commit_steady_ns', 'failure_steady_ns'), path='gate')


def release(row):
    fields(row, times=('valid_until_steady_ns',), path='release')
    fields(row.get('gates'), bools=('external_worker_zero_hooks',
        'subscriptions_verified', 'unique_dual_channel_owner'), path='release.gates')


def publication_event(row):
    fields(row, times=('valid_until_steady_ns', 'call_start_steady_ns'),
        nullable_times=('call_end_steady_ns',), bools=('completed',), path='publication_event')


def session(row):
    fields(row, times=('start_steady_ns', 'end_steady_ns'),
        counts=('queue_dropped_total', 'publish_errors', 'cycle_invocations_started',
            'interrupted_cycle_sequence'), bools=('flushed', 'normal_end'), path='session')
    if type(row['streams']) is not dict:
        fail('session.streams', 'object')
    for name, stream in row['streams'].items():
        fields(stream, counts=('generated', 'emitted', 'dropped', 'first_sequence', 'last_sequence'),
            path='session.streams.' + name)
    if 'reference_prediction' in row:
        fields(row['reference_prediction'], counts=('queue_capacity_events',),
            bools=('enabled',), path='session.reference_prediction')


def result(row):
    fields(row, times=('prepare_start_ns', 'prepare_budget_ns', 'overall_budget_ns',
            'close_elapsed_ns', 'elapsed_ns'),
        bools=('fixture_only', 'execute_qualified', 'physical_release_qualified',
            'D1_dynamic_qualified', 'cleanup_complete', 'resource_cleanup_complete',
            'cleanup_within_budget', 'evidence_qualification_clean', 'ledger_failed',
            'passed', 'released'), path='result')
    fields(row, bools=('held_negative_passed', 'expected_negative_rejection',
        'expired_release_no_receipt', 'release_file_exists', 'sensor_start_exists',
        'pid_start_mismatch_rejected', 'tampered_gid_rejected'), required=False, path='result')
    for role, code in row['owned_role_returncodes'].items():
        int64(code, 'result.owned_role_returncodes.' + role)
    for role, cleanup in row['cleanup'].items():
        fields(cleanup, signed=('returncode',), bools=('cleanup_complete',
            'resource_cleanup_complete', 'qualification_clean'), path='result.cleanup.' + role)
        for key in ('remaining_members', 'unexpected_descendants'):
            if type(cleanup[key]) is not list:
                fail('result.cleanup.' + role + '.' + key, 'array')
            for member in cleanup[key]:
                if type(member) is dict:
                    identity(member, 'result.cleanup.' + role + '.' + key)
                elif type(member) is int:
                    int64(member, 'result.cleanup.' + role + '.' + key, 1)
                else:
                    fail('result.cleanup.' + role + '.' + key, 'process_identity_or_pid')


def ledger(row):
    fields(row, times=('monotonic_ns',), signed=('returncode', 'signal'),
        bools=('executable_verified', 'cleanup_complete', 'resource_cleanup_complete',
            'qualification_clean'), required=False, path='ledger')
    if 'identity' in row:
        identity(row['identity'], 'ledger.identity')


def owned(row):
    identity(row, 'owned')
    fields(row, times=('created_steady_ns',), counts=('gid_storage_size',),
        bools=('effective_parameters_immutable', 'execute_qualified', 'physical_release_qualified',
            'infrastructure_endpoints_in_scope'), required=False, path='owned')
    for endpoint in row.get('endpoints', row.get('application_endpoints', [])):
        values = endpoint['gid']
        if type(values) is not list or len(values) != 16:
            fail('owned.endpoint.gid', '16_uint8')
        for value in values:
            if type(value) is not int or not 0 <= value <= 255:
                fail('owned.endpoint.gid', '16_uint8')
    if 'source_fd' in row:
        fd = row['source_fd']
        fields(fd, counts=('device', 'inode', 'mode', 'flags', 'access_mode'),
            signed=('fd',), bools=('append',), path='owned.source_fd')
        int64(fd['fd'], 'owned.source_fd.fd', 0)


def report(row):
    fields(row, times=('snapshot_steady_ns',), bools=('controller_shutdown_requested',
        'terminal_observation_only', 'receipt_qualifies_physical_release',
        'physical_release_qualified', 'execute_qualified', 'research_conclusion'), path='report')
    identity(row['identity'], 'report.identity')
    gate(row['gate'])


def transport(row):
    fields(row, counts=('ordinal', 'serialized_bytes'), times=('receipt_steady_ns',),
        required=False, path='transport')


def terminal(row):
    fields(row, times=('closed_steady_ns',), counts=('transport_total', 'elapsed_ms'),
        signed=('pid', 'stop_signal'), bools=('normal_end', 'failed', 'synthetic', 'prepared',
            'Recorder_stop_completed', 'clean', 'metadata_exists', 'manifest_written',
            'storage_stream_accounting_verified'), required=False, path='terminal')
    identity(row, 'terminal')
    for key in ('transport_counts', 'published_counts'):
        if key in row:
            for topic, value in row[key].items():
                uint64(value, 'terminal.' + key + '.' + topic)


def metadata(row):
    fields(row, counts=('message_count',), path='metadata')
    for entry in row['topics_with_message_count']:
        fields(entry, counts=('message_count',), path='metadata.topic')


def inputs(row):
    fields(row, counts=('domain',), bools=('sensor_start_is_separate_create_only_gate',),
        required=False, path='inputs')
    if 'measurement_seconds' in row:
        finite_number(row['measurement_seconds'], 'inputs.measurement_seconds')
    for role, pin in row['source_bundles'].items():
        fields(pin, counts=('files',), path='inputs.source_bundles.' + role)
    for role, build in row['builds'].items():
        fields(build, bools=('passed',), path='inputs.builds.' + role)


def source_bundle(row):
    for name, entry in row['files'].items():
        fields(entry, counts=('bytes',), path='source_bundle.' + name)
