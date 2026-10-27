"""Close only the owned simulation controller between observed publish events.

This is experiment lifecycle choreography, not a real-time safety supervisor.
No controller parameter, matching threshold, actuator message or bag is changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time

MIN_GAP_NS = 70_000_000
MAX_GAP_NS = 110_000_000


def in_gap(now, end):
    return (isinstance(end, int) and not isinstance(end, bool) and end > 0
            and MIN_GAP_NS <= now-end <= MAX_GAP_NS)


def verify_owned(pid, partition, workspace):
    process = Path('/proc') / str(pid)
    if (process/'comm').read_text().strip() != 'mpc_node':
        raise ValueError('Target is not the owned controller')
    env = (process/'environ').read_bytes().split(b'\0')
    if b'ROS_DOMAIN_ID=94' not in env or ('GZ_PARTITION='+partition).encode() not in env:
        raise ValueError('Target domain/partition does not match this run')
    actual = (process/'exe').resolve(strict=True)
    expected = workspace/'usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node'
    if actual != expected.resolve(strict=True):
        raise ValueError('Target executable is not the verified workspace controller')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--experiment', type=Path, required=True)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--partition', required=True)
    ap.add_argument('--pid', type=int, required=True)
    args = ap.parse_args()
    workspace = Path('/home/trevor/USV')
    exp = args.experiment.resolve(strict=True)
    if not exp.is_relative_to(workspace/'.sgh-research/experiments') or exp.name != args.run_id:
        raise ValueError('Experiment is not the explicit fresh owned run')
    verify_owned(args.pid, args.partition, workspace)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()+':steady_clock'
    import rclpy
    from usv_research_interfaces.msg import AppliedControl
    rclpy.init()
    node = rclpy.create_node('p0_lifecycle_'+hashlib.sha256(args.run_id.encode()).hexdigest()[:12])
    latest = None

    def callback(msg):
        nonlocal latest
        if msg.run_id != args.run_id or msg.steady_clock_domain != boot:
            return
        if msg.left_publish_success and msg.right_publish_success:
            if latest is None or msg.sequence > latest.sequence:
                latest = msg

    sub = node.create_subscription(AppliedControl, '/research/control/applied', callback, 100)
    start = time.monotonic()
    requested_at = None
    try:
        while time.monotonic()-start < 180:
            rclpy.spin_once(node, timeout_sec=.002)
            if sub.get_publisher_count() == 1 and not (exp/'shutdown_observer_ready.json').exists():
                (exp/'shutdown_observer_ready.json').write_text(json.dumps({'run_id':args.run_id,'pid':os.getpid(),
                    'steady_clock_domain':boot,'role':'read-only applied observer plus owned simulation shutdown'}))
            if not (exp/'shutdown_requested.json').exists():
                continue
            if requested_at is None:
                requested_at = time.monotonic()
            if time.monotonic()-requested_at > 10:
                raise TimeoutError('No observed publish gap within the bounded closure wait')
            if latest is None:
                continue
            end = max(latest.left_publish_end_steady_ns, latest.right_publish_end_steady_ns)
            now = time.monotonic_ns()
            if not in_gap(now, end):
                continue
            verify_owned(args.pid, args.partition, workspace)
            committed = time.monotonic_ns()
            if not in_gap(committed, end):
                continue
            os.kill(args.pid, signal.SIGINT)
            (exp/'shutdown_gap_evidence.json').write_text(json.dumps({'run_id':args.run_id,'controller_pid':args.pid,
                'applied_sequence':latest.sequence,'observed_publish_end_steady_ns':end,
                'kill_steady_ns':committed,'observed_gap_ns':committed-end,
                'requested_min_gap_ns':MIN_GAP_NS,'requested_max_gap_ns':MAX_GAP_NS,
                'purpose':'avoid ambiguity between timer and shutdown publications; unchanged 20ms matcher',
                'physical_execution_observed':False},indent=2))
            return 0
        raise TimeoutError('Experiment did not request bounded closure')
    except Exception as exc:
        (exp/'shutdown_gate_failure.json').write_text(json.dumps({'reason':str(exc)},indent=2))
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
