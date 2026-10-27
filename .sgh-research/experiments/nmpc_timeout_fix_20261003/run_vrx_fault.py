"""Run the deadline fixture against an isolated Gazebo plant, without code changes."""

import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def ros_command(workspace, command):
    setups = [Path('/opt/ros/jazzy/setup.bash'),
              workspace.parent / 'vrx_ws/install/setup.bash',
              workspace / 'install/setup.bash']
    for setup in setups:
        if not setup.is_file():
            raise FileNotFoundError(setup)
    return ' && '.join(['source ' + shlex.quote(str(p)) for p in setups] +
                       ['exec ' + shlex.join(command)])


def build_fixture(workspace, case):
    build = workspace / 'build/usv_mpc_cpp'
    target = build / 'CMakeFiles/test_deadline_control.dir'
    source = workspace / 'src/usv_mpc_cpp/test/test_deadline_control.cpp'
    text = source.read_text()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    mappings = {'left': '/wamv/thrusters/left/thrust',
                'right': '/wamv/thrusters/right/thrust',
                'status': '/mpc/status', 'trajectory': '/mpc/predicted_trajectory'}
    for suffix, topic in mappings.items():
        text, count = re.subn(r'\bprefix_?\s*\+\s*"/' + suffix + r'"',
                             '"' + topic + '"', text)
        if count != 2:
            raise RuntimeError(f'Expected publisher and observer for {suffix}: {count}')
    for member, threshold in [('vrx_left_pub_', 3), ('vrx_right_pub_', 3), ('status_pub_', 2)]:
        text, count = re.subn(re.escape(member) + r'->get_subscription_count\(\)\s*>\s*0',
                             member + f'->get_subscription_count() >= {threshold}', text)
        if count != 1:
            raise RuntimeError(f'Missing discovery check for {member}')
    text = text.replace('now() + 3s', 'now() + 6s')
    # RC is deliberately kept on the isolated fixture topic and explicitly observed.
    assertion = ('expect_vrx(8.0, 12.0); EXPECT_TRUE(rc_.empty());\n'
                 '    std::printf("FAULT_RC_OBSERVER_COUNT=%zu\\n", rc_.size());')
    text, count = re.subn(r'expect_vrx\(8\.0,\s*12\.0\);', lambda _: assertion, text)
    if count == 0:
        raise RuntimeError('No fixture output assertions found')
    temporary_source = case / 'test_deadline_control_vrx.cpp'
    temporary_source.write_text(text)
    flags = {}
    for line in (target / 'flags.make').read_text().splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            flags[key] = shlex.split(value)
    link = shlex.split((target / 'link.txt').read_text())
    compiler = link[0]
    obj = case / 'test_deadline_control_vrx.o'
    executable = case / 'test_deadline_control_vrx'
    compile_command = [compiler] + flags['CXX_DEFINES'] + flags['CXX_INCLUDES'] + \
        flags['CXX_FLAGS'] + ['-c', str(temporary_source), '-o', str(obj)]
    replacements = [i for i, item in enumerate(link)
                    if item.endswith('test_deadline_control.cpp.o')]
    if len(replacements) != 1:
        raise RuntimeError('Cannot uniquely identify the fixture object in link.txt')
    link[replacements[0]] = str(obj)
    link[link.index('-o') + 1] = str(executable)
    with (case / 'fixture_build.log').open('w') as log:
        subprocess.run(compile_command, cwd=build, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
        subprocess.run(link, cwd=build, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
        raise RuntimeError('Production fixture source changed during experiment')
    (case / 'fixture_build.json').write_text(json.dumps({
        'production_test_sha256': original_hash, 'compile': compile_command, 'link': link,
        'temporary_source': str(temporary_source), 'rc_topic_isolated': True}, indent=2))
    return executable


def stop_own_process(process):
    if process is None or process.poll() is not None:
        return
    # start_new_session=True makes this particular Popen PID its process-group ID.
    try:
        if os.getpgid(process.pid) != process.pid:
            raise RuntimeError('Refusing to signal an unverified process group')
    except ProcessLookupError:
        process.wait()
        return
    for sig, timeout in [(signal.SIGINT, 20), (signal.SIGTERM, 15), (signal.SIGKILL, 5)]:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            process.wait()
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError('Owned launch did not terminate')


def analyze(case):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    bag = case / 'vrx_fault'
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    counts = collections.Counter()
    thrust = {'left': [], 'right': []}
    statuses = []
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        counts[topic] += 1
        if topic in ('/wamv/thrusters/left/thrust', '/wamv/thrusters/right/thrust'):
            message = deserialize_message(data, types[topic])
            thrust['left' if '/left/' in topic else 'right'].append(float(message.data))
        elif topic == '/mpc/status':
            message = deserialize_message(data, types[topic])
            statuses.append(dict(json.loads(message.data), bag_timestamp_ns=stamp))
    xml = ET.parse(case / 'fixture.xml').getroot()
    test_passed = int(xml.attrib.get('tests', 0)) == 1 and \
        int(xml.attrib.get('failures', 0)) == 0 and int(xml.attrib.get('errors', 0)) == 0
    log = (case / 'fixture.log').read_text()
    rc_observations = [int(n) for n in re.findall(r'FAULT_RC_OBSERVER_COUNT=(\d+)', log)]
    rejections = [s for s in statuses if s.get('deadline_miss')]
    wall = [s.get('solve_wall_time_ms') for s in rejections]
    checks = {
        'gtest_passed': test_passed,
        'left_three_messages': len(thrust['left']) == 3,
        'right_three_messages': len(thrust['right']) == 3,
        'left_always_8N': len(thrust['left']) == 3 and
            all(math.isclose(v, 8.0, abs_tol=1e-9) for v in thrust['left']),
        'right_always_12N': len(thrust['right']) == 3 and
            all(math.isclose(v, 12.0, abs_tol=1e-9) for v in thrust['right']),
        'candidate_22_minus18_absent': not any(
            math.isclose(v, 22.0, abs_tol=1e-9) or math.isclose(v, -18.0, abs_tol=1e-9)
            for values in thrust.values() for v in values),
        'two_rejections_and_three_status': len(rejections) == 2 and len(statuses) == 3,
        'wall_250_and_400ms': len(wall) == 2 and
            all(isinstance(v, (int, float)) and v >= threshold
                for v, threshold in zip(wall, (250.0, 400.0))),
        'backend_1ms_repeat_source': len(rejections) == 2 and all(
            s.get('solve_time_ms') == 1.0 and s.get('control_source') == 'repeat_last_command'
            and s.get('success') is False for s in rejections),
        'only_initial_trajectory': counts['/mpc/predicted_trajectory'] == 1,
        'rc_observer_zero_messages': len(rc_observations) >= 2 and
            all(n == 0 for n in rc_observations),
    }
    metrics = {'passed': all(checks.values()), 'checks': checks, 'topic_counts': dict(counts),
               'thrust_N': thrust, 'statuses': statuses, 'rc_observer_counts': rc_observations,
               'scope': 'Fault-injected controller fixture driving isolated Gazebo plant; '
                        'does not measure real solver optimization or deadline preemption.'}
    (case / 'fault_metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)
    return 0 if metrics['passed'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=Path('/home/trevor/USV/usv_mpc_ws'))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent /
                        'results/vrx_fault')
    parser.add_argument('--analyze', action='store_true')
    args = parser.parse_args()
    case = args.output.resolve()
    if args.analyze:
        return analyze(case)
    case.mkdir(parents=True, exist_ok=True)
    if (case / 'vrx_fault').exists():
        raise FileExistsError('Existing bag preserved; choose a new --output directory')
    workspace = args.workspace.resolve()
    executable = build_fixture(workspace, case)
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID='90', ROS_LOCALHOST_ONLY='1',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               GZ_PARTITION='nmpc_timeout_vrx_fault_' + str(os.getpid()))
    launch_args = ['ros2', 'launch', 'usv_bringup', 'vrx.launch.py', 'scheme:=B',
                   'control_enabled:=false', 'headless:=True', 'record_bag:=True',
                   'bag_dir:=' + str(case), 'run_id:=vrx_fault',
                   'model_output_dir:=' + str(case / 'model')]
    command = ros_command(workspace, launch_args)
    launch = None
    started = time.monotonic()
    try:
        with (case / 'launch.log').open('w') as launch_log:
            launch = subprocess.Popen(['bash', '-c', command], env=env, stdout=launch_log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
            (case / 'process.json').write_text(json.dumps({
                'pid': launch.pid, 'pgid': os.getpgid(launch.pid), 'command': command,
                'environment': {k: env[k] for k in ('ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY',
                                                   'GZ_PARTITION')},
                'controller_enabled': False}, indent=2))
            time.sleep(12)
            if launch.poll() is not None:
                raise RuntimeError('VRX launch exited before the fault fixture started')
            test_args = [str(executable),
                         '--gtest_filter=DeadlineControl.BlockingSolveWithShortBackendTimingCannotPublishItsCandidate',
                         '--gtest_output=xml:' + str(case / 'fixture.xml')]
            with (case / 'fixture.log').open('w') as log:
                test = subprocess.run(['bash', '-c', ros_command(workspace, test_args)],
                                      env=env, stdout=log, stderr=subprocess.STDOUT, timeout=30)
            time.sleep(2)
            stop_own_process(launch)
            (case / 'complete.json').write_text(json.dumps({
                'launch_returncode': launch.returncode, 'fixture_returncode': test.returncode,
                'wall_seconds': time.monotonic() - started}, indent=2))
            if test.returncode:
                raise RuntimeError('Fault fixture failed; see fixture.log and fixture.xml')
    finally:
        stop_own_process(launch)
    analysis_args = ['/usr/bin/python3', str(Path(__file__).resolve()),
                     '--analyze', '--output', str(case)]
    with (case / 'analysis.log').open('w') as log:
        result = subprocess.run(['bash', '-c', ros_command(workspace, analysis_args)], env=env,
                                stdout=log, stderr=subprocess.STDOUT, timeout=30)
    if result.returncode:
        raise RuntimeError('Fault recording checks failed; see analysis.log/fault_metrics.json')
    print('VRX_FAULT_COMPLETE ' + str(case / 'fault_metrics.json'), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
