"""Review-only deterministic original-writer/original-header interleaving.

Pause the original writer's directory fsync, after link and before temp unlink.
Keep all old code/evidence unchanged. This does not identify historical causes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import select
import stat
import subprocess
import sys
import threading
import time
from unittest.mock import patch

AUTHOR = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_3_20261012_v9')
sys.path.insert(0, str(AUTHOR))
import owned_release

def read_line(process):
    if not select.select([process.stdout], [], [], 5)[0]:
        raise TimeoutError('native probe output deadline')
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('native probe exited: ' + process.stderr.read())
    return json.loads(line)

def run_case(binary, root, paused):
    root.mkdir()
    process = subprocess.Popen([str(binary), str(root)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    reached, resume = threading.Event(), threading.Event()
    writer_result = {}
    original_fsync = os.fsync
    thread = None
    try:
        ready = read_line(process)
        release = {'schema_version': 'p1-D1-publisher-release-v1',
            'run_id': ready['identity']['run_id'],
            'producer_instance_id': ready['identity']['producer_instance_id'],
            'startup_manifest_sha256': ready['startup_manifest_sha256'],
            'release_nonce': '1' * 32, 'driver_evidence_sha256': '2' * 64,
            'valid_until_steady_ns': time.monotonic_ns() + 3_000_000_000,
            'gates': {'external_worker_zero_hooks': True,
                'subscriptions_verified': True, 'unique_dual_channel_owner': True}}
        def fsync(fd):
            if paused and stat.S_ISDIR(os.fstat(fd).st_mode):
                reached.set()
                if not resume.wait(5):
                    raise TimeoutError('directory fsync barrier deadline')
            return original_fsync(fd)
        def write():
            try:
                writer_result.update(returned=True,
                    sha256=owned_release.create_only_json(root / 'release.json', release))
            except BaseException as error:
                writer_result.update(returned=False, error=repr(error))
        with patch.object(owned_release.os, 'fsync', fsync):
            thread = threading.Thread(target=write); thread.start()
            if paused:
                if not reached.wait(5):
                    raise TimeoutError('writer did not reach post-link directory fsync')
            else:
                thread.join(5)
                if thread.is_alive():
                    raise TimeoutError('control writer deadline')
            links_at_first_poll = (root / 'release.json').stat().st_nlink
            process.stdin.write('poll\n'); process.stdin.flush()
            first = read_line(process)
            resume.set(); thread.join(5)
            if thread.is_alive():
                raise TimeoutError('writer cleanup deadline')
            links_after_writer = (root / 'release.json').stat().st_nlink
            process.stdin.write('poll\n'); process.stdin.flush()
            second = read_line(process)
            process.stdin.close()
            process.wait(timeout=5)
        return {'paused_after_atomic_link': paused, 'ready': ready,
            'release': release, 'writer': writer_result,
            'links_at_first_poll': links_at_first_poll,
            'links_after_writer': links_after_writer, 'first_poll': first,
            'second_poll': second, 'native_returncode': process.returncode,
            'native_stderr': process.stderr.read()}
    finally:
        resume.set()
        if thread is not None:
            thread.join(5)
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--root', required=True)
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    root = Path(a.root); root.mkdir()
    control = run_case(Path(a.binary), root / 'control', False)
    race = run_case(Path(a.binary), root / 'race', True)
    reproduced = (control['first_poll']['released'] and control['native_returncode'] == 0
        and race['links_at_first_poll'] == 2 and race['links_after_writer'] == 1
        and race['writer']['returned'] is True and not race['first_poll']['released']
        and race['first_poll']['gate']['gate_state'] == 'Fault'
        and race['first_poll']['gate']['failure_phase'] == 'release_read'
        and race['first_poll']['gate']['failure_reason'] ==
            'gate input is not a bounded, single-link regular file'
        and not race['first_poll']['arm_called']
        and not race['second_poll']['released'] and race['second_poll']['primitive_readable']
        and race['native_returncode'] == 0)
    report = {'schema': 'scheme-A-review-publication-race/v1',
        'client_date': '2026-10-13', 'reproduced': reproduced,
        'writer_source_sha256': hashlib.sha256((AUTHOR / 'owned_release.py').read_bytes()).hexdigest(),
        'native_header_sha256': hashlib.sha256((AUTHOR /
            'publisher/include/usv_mpc_cpp/p1_startup_gate.hpp').read_bytes()).hexdigest(),
        'probe_binary_sha256': hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
        'control': control, 'race': race, 'historical_timeout_cause_proven': False,
        'physical_output_or_ROS_nodes': False, 'stage_qualified': False}
    with Path(a.report).open('x') as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'reproduced': reproduced, 'report': a.report,
        'control_state': control['first_poll']['gate']['gate_state'],
        'race_state': race['first_poll']['gate']['gate_state'],
        'links': [race['links_at_first_poll'], race['links_after_writer']],
        'writer_returned': race['writer'].get('returned')}, ensure_ascii=False))
    return 0 if reproduced else 2

if __name__ == '__main__':
    raise SystemExit(main())
