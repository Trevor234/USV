"""B0 startup rejection: node RC1, pure CLI RC2; physical release stays closed."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

E = Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01')
WS = Path('/home/trevor/USV/usv_mpc_ws')
R = E / 'authored_runtime_v30_contract_20261007'
G = E / 'contract_v30_prelaunch_assets_20261007.json'
B = E / 'contract_v14_build_result_20261007.json'
O = E / 'contract_B0_startup_rejection_20261007'
PRE = E / 'authored_v14_contract_20261007/p1_execution_pre_freeze_v1.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guard-sha256', required=True)
    parser.add_argument('--build-sha256', required=True)
    args = parser.parse_args()
    if sys.platform != 'linux':
        raise RuntimeError('Linux ROS host required')
    if sha(G) != args.guard_sha256 or sha(B) != args.build_sha256:
        raise RuntimeError('predeclared guard/build identity mismatch')
    sys.path.insert(0, str(R))
    from owned_process_supervisor import Supervisor, boot_id
    from run_worker_fault_matrix import verify_assets
    from run_formal_no_output_validation import host_preflight
    before = verify_assets(G)
    host_before = host_preflight()  # No owned children yet.
    build = json.loads(B.read_text())
    if build.get('schema') != 'p1-B0-cpp-build-v1' or build.get('release_enabled') is not False:
        raise RuntimeError('release-disabled B0 build required')
    bins = build['binaries']
    for name in ('p1_regulator', 'p1_solver_worker'):
        if sha(bins[name]['path']) != bins[name]['sha256']:
            raise RuntimeError('actual build executable changed: ' + name)
    header = WS / 'src/usv_research_safety_cpp/p1_full_contract.hpp'
    if 'physical_execute_release_enabled = false;' not in header.read_text():
        raise RuntimeError('guard-bound source release flag changed')
    from p1_full_contract import load_contract
    pre, pre_sha = load_contract(PRE, mode='no_output', runtime=True)
    if pre['qualification'] != 'execution_pre_freeze':
        raise RuntimeError('pre-freeze source contract required')
    O.mkdir(exist_ok=False)
    write(O / 'declaration.json', {
        'schema': 'p1-B0-startup-rejection-context-v1',
        'guard': before, 'build_sha256': sha(B), 'binaries': bins,
        'pre_contract_sha256': pre_sha, 'boot_id': boot_id(),
        'observer_domain': 167, 'node_expected_rc': 1, 'pure_cli_rc': 2,
        'startup_limit_s': 3, 'cleanup_s': [.5, 1, 1],
        'release_enabled': False, 'execute_qualified': False,
        'node_base_dds_visibility_possible': True, 'endpoint_poll_is_sampled': True,
        'script_sha256': sha(__file__)})
    env = dict(os.environ, ROS_DOMAIN_ID='167', ROS_LOCALHOST_ONLY='1')
    os.environ.update(ROS_DOMAIN_ID='167', ROS_LOCALHOST_ONLY='1')
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    spy = rclpy.create_node('p1_B0_rejection_observer')
    supervisor = Supervisor(O)
    rows, python_rows = [], []
    failure, after, host_after = None, None, None
    max_endpoints = {'left': 0, 'right': 0}

    def observe(seconds=.02):
        rclpy.spin_once(spy, timeout_sec=seconds)
        for side, topic in pre['output_topics'].items():
            count = len(spy.get_publishers_info_by_topic(topic))
            max_endpoints[side] = max(max_endpoints[side], count)
            if count:
                raise RuntimeError('physical publisher observed: ' + side)

    def altered(**values):
        return dict(copy.deepcopy(pre), **values)
    missing = altered()
    del missing['T_ns']
    frozen = altered(qualification='execution_frozen', execute_qualified=True,
                     parameters_are_diagnostic_only=False, pending_final_calibration=[],
                     freeze_evidence_sha256='a' * 64)
    cases = [
        ('reg_missing_T', 'p1_regulator', missing, 'no_output', 'missing or unknown top-level fields'),
        ('reg_float_T', 'p1_regulator', altered(T_ns=float(pre['T_ns'])), 'no_output', 'int64 JSON integer required: T_ns'),
        ('reg_fault_true', 'p1_regulator', altered(fault_injection_enabled=True), 'no_output', 'formal fault injection prohibited'),
        ('reg_pre_execute', 'p1_regulator', pre, 'execute', 'profile/mode mismatch'),
        ('reg_frozen_execute', 'p1_regulator', frozen, 'execute', 'physical execute release is disabled until B5/M4'),
        ('worker_bool_rho', 'p1_solver_worker', altered(rho_n_s=True), None, 'finite number required: rho_n_s'),
        ('worker_int_overflow', 'p1_solver_worker', altered(T_ns=2 ** 63), None, 'int64 JSON integer required: T_ns')]
    try:
        discover = time.monotonic() + 1
        while time.monotonic() < discover:
            observe()
        write(O / 'initial_endpoint_observation.json', {'counts': dict(max_endpoints), 'observed_ns': time.monotonic_ns()})
        for name, binary, contract, mode, expected in cases:
            path, source = O / (name + '.json'), O / (name + '_source.jsonl')
            write(path, contract)
            argv = [bins[binary]['path'], '--ros-args', '-p', 'run_id:=' + name,
                    '-p', 'contract_file:=' + str(path), '-p', 'contract_hash:=' + sha(path),
                    '-p', 'source_file:=' + str(source)]
            if mode is not None:
                argv += ['-p', 'mode:=' + mode]
            child = supervisor.spawn(name, argv, env, Path(bins[binary]['path']), bins[binary]['sha256'])
            deadline = time.monotonic() + 3
            while child.process.poll() is None and time.monotonic() < deadline:
                observe()
            timed_out = child.process.poll() is None
            clean = supervisor.stop(child, .5, 1, 1)
            observe()
            console = (O / (name + '.console.log')).read_text(errors='replace')
            prefix = 'regulator fatal:' if binary == 'p1_regulator' else 'worker fatal:'
            passed = (not timed_out and clean['cleanup_complete'] and clean['returncode'] == 1
                      and prefix in console and expected in console and not source.exists())
            rows.append({'case': name, 'binary': binary, 'contract_sha256': sha(path),
                         'mode': mode, 'expected_error': expected, 'timed_out': timed_out,
                         'returncode': clean['returncode'], 'source_exists': source.exists(),
                         'cleanup': clean, 'console_sha256': sha(O / (name + '.console.log')),
                         'passed': passed})
            if not passed:
                raise RuntimeError('startup rejection not closed: ' + name)
        import run_formal_no_output_validation as formal
        for field in ('test_delay_ms', 'test_native_block_ms', 'test_prepare_block_ms', 'test_tick_block_ms'):
            run_id = 'B0_python_' + field
            child_dir = O / run_id
            values = dict(contract=PRE, contract_hash=pre_sha, experiment_root=O,
                          workspace=WS, run_id=run_id, duration=10., worker_sha256=None,
                          regulator_sha256=None, test_delay_ms=0, test_native_block_ms=0,
                          test_prepare_block_ms=0, test_tick_block_ms=0)
            values[field] = 50
            error = None
            try:
                formal.run(SimpleNamespace(**values))
            except Exception as exc:
                error = type(exc).__name__ + ': ' + str(exc)
            passed = (error == 'RuntimeError: fault injection disabled by contract' and not child_dir.exists())
            python_rows.append({'hook': field, 'error': error, 'directory_exists': child_dir.exists(), 'passed': passed})
            if not passed:
                raise RuntimeError('Python pre-mkdir rejection failed: ' + field)
    except BaseException as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    finally:
        for child in supervisor.owned.values():
            supervisor.stop(child, .5, 1, 1)
        try:
            observe()
            after = verify_assets(G)
            if not supervisor.cleanup_failed:
                host_after = host_preflight()  # All owned groups empty.
        except Exception as exc:
            failure = failure or (type(exc).__name__ + ': ' + str(exc))
        supervisor.close()
        spy.destroy_node()
        rclpy.shutdown()
        result = {'schema': 'p1-B0-real-startup-rejection-v1', 'cases': rows, 'python_hooks': python_rows,
                  'failure': failure, 'guard_before': before, 'guard_after': after,
                  'host_before': host_before, 'host_after': host_after, 'max_physical_endpoints': max_endpoints,
                  'cleanup_failed': supervisor.cleanup_failed, 'supervision_evidence_complete': not supervisor.evidence_failed,
                  'supervision_memory_tail': supervisor.memory_tail if supervisor.evidence_failed else [],
                  'passed': failure is None and len(rows) == 7 and len(python_rows) == 4
                            and not supervisor.cleanup_failed and not supervisor.evidence_failed,
                  'native_nonentry_basis': 'guard-bound constructor code order, not source absence alone',
                  'worker_has_no_execute_mode_gate': True, 'normal_contract_complete': False,
                  'execute_qualified': False, 'freeze_marker_is_test_fixture_only': True}
        write(O / 'result.json', result)
        print(json.dumps(result), flush=True)
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
