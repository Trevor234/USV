"""Fail-closed release primitive for an independently supervised preparation.

No launches, signals, measurement, or automatic retry. The caller retains the
already-frozen Supervisor identities; a manifest's self-reported PID is not
accepted as ownership. ROS graph observations are collected from a live node.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

MAX_JSON = 64 * 1024
OWN_KEYS = ('pid', 'start_ticks', 'pgid', 'sid', 'exe', 'exe_sha256')
TOPIC_TYPES = {'/research/control/applied':'usv_research_interfaces/msg/AppliedControl',
               '/p1/solve_job':'usv_research_interfaces/msg/SolveJob',
               '/p1/solve_candidate':'usv_research_interfaces/msg/SolveCandidate',
               '/p1/execution_decision':'usv_research_interfaces/msg/ExecutionDecision',
               '/p1/worker_capability':'usv_research_interfaces/msg/WorkerCapability'}

class PublicationAmbiguousError(OSError):
    """Target became visible before a durability error; do not claim absent."""
    def __init__(self, path, content_sha256):
        super().__init__('target visible, directory durability unconfirmed: ' + str(path))
        self.path=str(path);self.content_sha256=content_sha256;self.target_visible=True

def require(value, reason):
    if not value:
        raise ValueError(reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def sha_text(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None

def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    require(len(raw) <= MAX_JSON, 'JSON exceeds budget')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def checked_path(path):
    p = Path(path)
    require(p.is_absolute() and '..' not in p.parts, 'absolute normalized path required')
    for parent in (p, *p.parents):
        require(not parent.is_symlink(), 'symlink path forbidden')
    return p

def read_regular(path):
    p = checked_path(path)
    fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_JSON, 'bounded regular file required')
        raw = os.read(fd, MAX_JSON + 1)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'file changed while reading')
        require(len(raw) == before.st_size, 'incomplete read')
        return raw
    finally:
        os.close(fd)

def create_only_json(path, data):
    p = checked_path(path)
    require(p.parent.is_dir(), 'existing owned parent required')
    raw = (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    require(len(raw) <= MAX_JSON, 'output exceeds budget')
    temp = p.parent / ('.' + p.name + '.' + secrets.token_hex(16) + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp, p)  # atomic no-overwrite; do not rename over existing evidence
        try:
            parent_fd = os.open(p.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError as error:
            raise PublicationAmbiguousError(p, digest(raw)) from error
    finally:
        temp.unlink(missing_ok=True)
    return digest(raw)

def actual_process(pid):
    require(type(pid) is int and pid > 0, 'positive owned PID required')
    root = Path('/proc') / str(pid)
    fields = (root / 'stat').read_text().rsplit(')', 1)[1].split()
    exe = os.readlink(root / 'exe')
    result = dict(pid=pid, start_ticks=int(fields[19]), pgid=int(fields[2]), sid=int(fields[3]),
                  exe=exe, exe_sha256=digest((root / 'exe').read_bytes()))
    require(fields[0] != 'Z', 'zombie cannot be preparation-ready')
    cmdline = (root / 'cmdline').read_bytes()
    result['argv'] = [part.decode('utf-8') for part in cmdline.rstrip(b'\0').split(b'\0')]
    result['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return result

def authenticate_owned(expected, boot):
    observed = actual_process(expected['pid'])
    require(observed['boot_id'] == boot, 'boot changed')
    require(all(observed.get(key) == expected.get(key) for key in OWN_KEYS), 'owned process identity changed / PID reused')
    require(observed['pgid'] == observed['pid'] == observed['sid'], 'owned session leader required')
    return observed

def explicit_parameters(argv, expected, hooks):
    """Reject alternate parameter sources and duplicate/selector overrides.

    Explicit values in the owned effective argv are required even when the
    runtime defaults are zero. Capability's injection *permission* is not an
    effective delay. This primitive does not infer defaults from capability.
    """
    require(argv and '--ros-args' in argv, 'explicit ROS parameters required')
    found = {}
    i = argv.index('--ros-args') + 1
    while i < len(argv):
        item = argv[i]
        if item in ('-p', '--param'):
            require(i + 1 < len(argv), 'missing parameter value')
            name, sep, value = argv[i + 1].partition(':=')
            require(sep and ':' not in name and name not in found, 'ambiguous/duplicate parameter override')
            require(name in expected or name in hooks, 'unregistered parameter override')
            found[name] = value
            i += 2
        elif item in ('-r', '--remap'):
            require(i + 1 < len(argv) and argv[i + 1].startswith('__node:='), 'only preregistered node remap permitted')
            require('__node' not in found, 'duplicate node remap')
            found['__node'] = argv[i + 1].partition(':=')[2]
            i += 2
        else:
            raise ValueError('unregistered ROS argument or parameter file')
    for key, value in expected.items():
        require(found.get(key) == str(value), 'effective parameter mismatch: ' + key)
    for key in hooks:
        require(found.get(key) == '0', 'hook must be explicitly integer zero: ' + key)
    return found

def authenticate_startup(manifest_path, owned, boot, pins):
    observed = authenticate_owned(owned, boot)
    raw = read_regular(manifest_path)
    m = strict_json(raw)
    require(m.get('schema_version') == 'p1-D1-publisher-startup-v1', 'startup schema mismatch')
    require(m.get('derived_publisher') is True, 'derived source lineage required')
    for key, value in pins.items():
        require(m.get(key) == value, 'startup pin mismatch: ' + key)
    require(m.get('boot_id') == boot and m.get('steady_clock_domain') == boot + ':steady_clock', 'startup boot/domain mismatch')
    require(m.get('pid') == observed['pid'] and m.get('process_start_ticks') == observed['start_ticks'], 'startup author is not owned publisher')
    require(m.get('binary_sha256') == observed['exe_sha256'], 'startup binary differs from actual executable')
    require(type(m.get('created_steady_ns')) is int and 0 < m['created_steady_ns'] <= time.monotonic_ns(), 'startup timestamp invalid')
    require(type(m.get('producer_instance_id')) is str and m['producer_instance_id'].startswith(m['run_id'] + ':'), 'producer does not bind run')
    return dict(manifest=m, manifest_sha256=digest(raw), observed=observed)

def live_graph(node, physical_topics, required_subscriptions):
    rows = {}
    for topic in sorted(set(physical_topics) | set(required_subscriptions)):
        # rclpy TopicEndpointInfo exposes attributes (not rclcpp methods).
        def python_project(endpoint):
            return dict(node=endpoint.node_namespace.rstrip('/') + '/' + endpoint.node_name,
                        type=endpoint.topic_type, gid=list(endpoint.endpoint_gid))
        rows[topic] = dict(publishers=[python_project(e) for e in node.get_publishers_info_by_topic(topic)],
                           subscriptions=[python_project(e) for e in node.get_subscriptions_info_by_topic(topic)])
    return dict(observed_ns=time.monotonic_ns(), topics=rows)

def verify_graph(graph, physical_topics, publisher_node, required_subscriptions, now, budget_ns):
    require(type(graph.get('observed_ns')) is int and 0 <= now - graph['observed_ns'] <= budget_ns, 'graph observation stale/future')
    require(len(physical_topics) == 2 and len(set(physical_topics)) == 2, 'exactly two distinct physical channels required')
    require(bool(required_subscriptions) and all(type(names) is list and names for names in required_subscriptions.values()), 'nonempty required subscription population required')
    for topic in physical_topics:
        rows = graph['topics'][topic]['publishers']
        require(len(rows) == 1 and rows[0]['node'] == publisher_node, 'unique physical publisher not proven')
        require(len(rows[0]['gid']) > 0 and any(rows[0]['gid']), 'physical publisher GID missing')
        require(rows[0].get('type') == 'std_msgs/msg/Float64', 'physical topic type mismatch')
    for topic, names in required_subscriptions.items():
        expected_type=TOPIC_TYPES.get(topic, 'std_msgs/msg/Float64' if topic in physical_topics else None)
        require(expected_type is not None, 'unregistered required topic type')
        rows = graph['topics'][topic]['subscriptions']
        for name in names:
            matched = [row for row in rows if row['node'] == name]
            require(len(matched) == 1 and any(matched[0]['gid']), 'exact actual subscription missing/ambiguous: ' + topic + ':' + name)
            require(matched[0].get('type') == expected_type, 'subscription topic type mismatch')
    return True

def authorize_release(*, manifest_path, publisher_owned, worker_owned, observer_owned, recorder_owned,
                      boot, startup_pins, worker_parameters, observer_parameters, node, physical_topics,
                      publisher_node, required_subscriptions, evidence_path, release_path,
                      preparation_start_ns, preparation_budget_ns):
    """Caller supplies trusted Supervisor records, never manifest-owned PIDs.

    This is one finite live observation; release is not a guarantee about later
    graph changes, readiness, measurement eligibility, or physical safety.
    """
    now = time.monotonic_ns()
    require(type(preparation_budget_ns) is int and 0 < preparation_budget_ns <= 60_000_000_000, 'finite prepare budget required')
    require(0 <= now - preparation_start_ns <= preparation_budget_ns, 'prepare deadline expired')
    startup = authenticate_startup(manifest_path, publisher_owned, boot, startup_pins)
    worker = authenticate_owned(worker_owned, boot)
    observer = authenticate_owned(observer_owned, boot)
    recorder = authenticate_owned(recorder_owned, boot)
    worker_argv = explicit_parameters(worker['argv'], worker_parameters, ('test_delay_ms', 'test_native_block_ms'))
    observer_argv = explicit_parameters(observer['argv'], observer_parameters,
                        ('test_delay_ms', 'test_native_block_ms', 'test_prepare_block_ms', 'test_tick_block_ms', 'test_sink_pause_ms'))
    graph = live_graph(node, physical_topics, required_subscriptions)
    verify_graph(graph, physical_topics, publisher_node, required_subscriptions, time.monotonic_ns(), 1_000_000_000)
    # Reauthenticate all processes after graph collection and before committing.
    for owned in (publisher_owned, worker_owned, observer_owned, recorder_owned):
        authenticate_owned(owned, boot)
    require(time.monotonic_ns() - preparation_start_ns <= preparation_budget_ns, 'prepare deadline expired at release')
    evidence = dict(schema_version='p1-D1-independent-preparation-observation-v1', checked_ns=time.monotonic_ns(),
                    startup=startup, worker=worker, observer=observer, recorder=recorder,
                    effective_worker_parameters=worker_argv, effective_observer_parameters=observer_argv,
                    graph=graph, external_worker_zero_hooks=True, subscriptions_verified=True,
                    unique_named_dual_channel_publisher_observed=True, legacy_ready=False, measurement_qualified=False,
                    owned_dds_endpoint_binding_verified=False, publisher_effective_configuration_verified=False,
                    production_release_authorized=False, release_written=False)
    # Alive owned processes + same-name/nonzero-GID graph entries do not bind
    # DDS endpoints to those processes. The recorder has no authenticated
    # endpoint manifest yet; publisher effective full configuration is also
    # not verified by this primitive. Production release therefore remains
    # unreachable. Do not turn these observations into a true gate attestation.
    raise ValueError('production release disabled: owned DDS endpoint bindings and publisher effective configuration not closed')
