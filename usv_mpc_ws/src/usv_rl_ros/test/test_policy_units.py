"""Physical-N contract tests and real ROS publication/history regression tests.

Run in an isolated ROS domain with the source package on PYTHONPATH. The fake
ORT session supplies physical requests only; publishers, messages, executor,
observation composition and thrust limits are the production implementations.
"""
import hashlib
import json
import os
import sys
import time
from types import SimpleNamespace
import uuid

import numpy as np
import pytest
import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMsg
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Float64, String

from usv_rl_ros.rl_policy_node import (
    RlPolicyNode, load_policy_contract, validate_policy_session,
)


class PhysicalSession:
    def __init__(self, requests=(), *, input_shape=None, metadata=None):
        self.requests = [np.asarray(r, dtype=np.float32) for r in requests]
        self.observations = []
        self.input_shape = ["batch", 43] if input_shape is None else input_shape
        self.metadata = {} if metadata is None else metadata

    def get_inputs(self):
        return [SimpleNamespace(name="obs", type="tensor(float)", shape=self.input_shape)]

    def get_outputs(self):
        return [SimpleNamespace(name="thrust", type="tensor(float)", shape=["batch", 2])]

    def get_modelmeta(self):
        return SimpleNamespace(custom_metadata_map=self.metadata)

    def run(self, names, feeds):
        assert names == ["thrust"]
        assert set(feeds) == {"obs"}
        obs = feeds["obs"]
        assert obs.shape == (1, 43)
        assert obs.dtype == np.float32
        self.observations.append(obs.copy())
        index = len(self.observations) - 1
        return [self.requests[index][None, :]]


def make_policy(tmp_path):
    path = tmp_path / "policy_physical_n.onnx"
    path.write_bytes(b"test model bytes; ORT session is substituted in publication tests")
    contract = {
        "contract_version": 1, "output_unit": "N",
        "action_order": ["T_L", "T_R"],
        "input_name": "obs", "input_dim": 43,
        "output_name": "thrust", "output_dim": 2,
        "thrust_scale_n": 25.0,
        "physical_low_n": [-25.0, -25.0],
        "physical_high_n": [25.0, 25.0],
        "normalization_embedded": True,
        "onnx_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(contract), encoding="utf-8")
    return path, contract


def test_contract_accepts_physical_n_and_matching_metadata(tmp_path):
    path, contract = make_policy(tmp_path)
    assert load_policy_contract(path, 25.0) == contract
    metadata = {
        "usv.contract_version": "1", "usv.output_unit": "N",
        "usv.action_order": "T_L,T_R", "usv.input_dim": "43",
        "usv.output_dim": "2", "usv.thrust_scale_n": "25",
    }
    validate_policy_session(PhysicalSession(metadata=metadata), contract)


@pytest.mark.parametrize("change", [
    {"output_unit": "normalized"}, {"onnx_sha256": "0" * 64},
    {"action_order": ["T_R", "T_L"]}, {"input_dim": 42},
    {"physical_high_n": [20.0, 25.0]}, {"thrust_scale_n": 1.0},
    {"normalization_embedded": False}, {"contract_version": True},
])
def test_contract_rejects_wrong_units_hash_or_dimensions(tmp_path, change):
    path, contract = make_policy(tmp_path)
    contract.update(change)
    path.with_suffix(".manifest.json").write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy_contract(path, 25.0)


def test_contract_rejects_missing_manifest_and_current_bound(tmp_path):
    path, _ = make_policy(tmp_path)
    with pytest.raises(ValueError, match="t_max"):
        load_policy_contract(path, 20.0)
    path.with_suffix(".manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest"):
        load_policy_contract(path, 25.0)


@pytest.mark.parametrize("shape", [["batch", 42], [43], [2, 43]])
def test_session_rejects_actual_ort_shape(tmp_path, shape):
    _, contract = make_policy(tmp_path)
    with pytest.raises(ValueError, match="tensor"):
        validate_policy_session(PhysicalSession(input_shape=shape), contract)


@pytest.mark.parametrize("side,field,value", [
    ("input", "name", "observation"), ("input", "type", "tensor(double)"),
    ("output", "name", "action"), ("output", "shape", ["batch", 3]),
])
def test_session_rejects_wrong_actual_names_types_or_output_shape(
        tmp_path, monkeypatch, side, field, value):
    _, contract = make_policy(tmp_path)
    session = PhysicalSession()
    method = "get_inputs" if side == "input" else "get_outputs"
    arg = getattr(session, method)()[0]
    setattr(arg, field, value)
    monkeypatch.setattr(session, method, lambda: [arg])
    with pytest.raises(ValueError, match="tensor"):
        validate_policy_session(session, contract)


@pytest.mark.parametrize("metadata", [
    {"usv.output_unit": "normalized"}, {"usv.action_order": "T_R,T_L"},
    {"usv.thrust_scale_n": "1"}, {"usv.thrust_scale_n": "nan"},
])
def test_session_rejects_graph_metadata_disagreement(tmp_path, metadata):
    _, contract = make_policy(tmp_path)
    with pytest.raises(ValueError):
        validate_policy_session(PhysicalSession(metadata=metadata), contract)


@pytest.fixture
def ros_runtime():
    # Explicitly isolated: no discovery of the user's VRX/controller domain.
    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    domain = int(os.environ.get("USV_POLICY_TEST_DOMAIN_ID", "185"))
    rclpy.init(args=[], domain_id=domain)
    executor = SingleThreadedExecutor()
    nodes = []
    yield executor, nodes
    for node in reversed(nodes):
        executor.remove_node(node)
        node.destroy_node()
    executor.shutdown()
    rclpy.shutdown()


def spin_until(executor, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.05)
    assert predicate(), "timed out waiting for actual ROS discovery/messages"


def setup_ros_pair(ros_runtime, monkeypatch, path, session, t_max=25.0):
    executor, nodes = ros_runtime
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        InferenceSession=lambda *args, **kwargs: session))
    prefix = "/v5_policy_units_" + uuid.uuid4().hex
    topics = {key: prefix + "/" + key for key in (
        "odom_topic", "imu_topic", "path_topic", "profile_topic",
        "left_thrust_topic", "right_thrust_topic", "status_topic")}
    params = [Parameter("model_path", value=str(path)), Parameter("t_max", value=t_max)]
    params.extend(Parameter(key, value=value) for key, value in topics.items())
    policy = RlPolicyNode(parameter_overrides=params)
    nodes.append(policy)
    # Each assertion triggers precisely one production control iteration.
    for timer in policy.timers:
        timer.cancel()
    observer = Node("policy_units_observer_" + uuid.uuid4().hex)
    nodes.append(observer)
    left, right, statuses = [], [], []
    observer.create_subscription(Float64, topics["left_thrust_topic"],
                                 lambda msg: left.append(msg.data), 10)
    observer.create_subscription(Float64, topics["right_thrust_topic"],
                                 lambda msg: right.append(msg.data), 10)
    observer.create_subscription(String, topics["status_topic"],
                                 lambda msg: statuses.append(json.loads(msg.data)), 10)
    executor.add_node(policy)
    executor.add_node(observer)
    spin_until(executor, lambda: policy.thrust_pub_l.get_subscription_count() == 1
               and policy.thrust_pub_r.get_subscription_count() == 1
               and policy.status_pub.get_subscription_count() == 1)
    return policy, left, right, statuses


def seed_straight_path(policy):
    odom = Odometry()
    odom.pose.pose.orientation.w = 1.0
    odom.twist.twist.linear.x = 0.6
    policy._odom_cb(odom)
    path = PathMsg()
    for x in np.linspace(0.0, 100.0, 11):
        pose = PoseStamped()
        pose.pose.position.x = float(x)
        pose.pose.orientation.w = 1.0
        path.poses.append(pose)
    policy._path_cb(path)


def control_and_capture(executor, policy, left, right, statuses):
    before = (len(left), len(right), len(statuses))
    policy._control_loop()
    spin_until(executor, lambda: len(left) == before[0] + 1
               and len(right) == before[1] + 1 and len(statuses) == before[2] + 1)
    return np.array([left[-1], right[-1]]), statuses[-1]


def test_real_ros_publishes_half_action_in_n_without_extra_scale(
        tmp_path, monkeypatch, ros_runtime):
    path, _ = make_policy(tmp_path)
    session = PhysicalSession([[12.5, -12.5], [0.0, 0.0]])
    policy, left, right, statuses = setup_ros_pair(ros_runtime, monkeypatch, path, session)
    seed_straight_path(policy)
    applied, status = control_and_capture(ros_runtime[0], policy, left, right, statuses)
    np.testing.assert_allclose(applied, [12.5, -12.5], atol=1e-6)
    assert status["state"] == "ACTIVE"
    np.testing.assert_allclose([status["tl_cmd_n"], status["tr_cmd_n"]], [12.5, -12.5])
    np.testing.assert_allclose([status["tl_n"], status["tr_n"]], applied)
    control_and_capture(ros_runtime[0], policy, left, right, statuses)
    np.testing.assert_allclose(session.observations[1][0, -2:], applied)


def test_real_ros_limits_physical_requests_and_feeds_published_n_history(
        tmp_path, monkeypatch, ros_runtime):
    path, _ = make_policy(tmp_path)
    session = PhysicalSession([[25.0, -25.0], [25.0, -25.0], [-25.0, 25.0]])
    policy, left, right, statuses = setup_ros_pair(ros_runtime, monkeypatch, path, session)
    seed_straight_path(policy)
    expected = [[16.0, -16.0], [25.0, -25.0], [9.0, -9.0]]
    raw = [[25.0, -25.0], [25.0, -25.0], [-25.0, 25.0]]
    for i, reference in enumerate(expected):
        applied, status = control_and_capture(ros_runtime[0], policy, left, right, statuses)
        assert status["state"] == "ACTIVE"
        np.testing.assert_allclose(applied, reference, atol=1e-6)
        np.testing.assert_allclose([status["tl_cmd_n"], status["tr_cmd_n"]], raw[i])
        np.testing.assert_allclose([status["tl_n"], status["tr_n"]], reference)
        history = [0.0, 0.0] if i == 0 else expected[i - 1]
        np.testing.assert_allclose(session.observations[i][0, -2:], history)


@pytest.mark.parametrize("failure", ["missing", "unit", "hash", "current_bound", "shape"])
def test_real_ros_contract_failure_stays_standby_with_zero_thrust(
        tmp_path, monkeypatch, ros_runtime, failure):
    path, contract = make_policy(tmp_path)
    manifest = path.with_suffix(".manifest.json")
    if failure == "missing":
        manifest.unlink()
    elif failure == "unit":
        contract["output_unit"] = "normalized"
    elif failure == "hash":
        contract["onnx_sha256"] = "0" * 64
    if failure in {"unit", "hash"}:
        manifest.write_text(json.dumps(contract), encoding="utf-8")
    session = PhysicalSession([[25.0, -25.0]],
                              input_shape=["batch", 42] if failure == "shape" else None)
    policy, left, right, statuses = setup_ros_pair(
        ros_runtime, monkeypatch, path, session,
        t_max=20.0 if failure == "current_bound" else 25.0)
    seed_straight_path(policy)
    applied, status = control_and_capture(ros_runtime[0], policy, left, right, statuses)
    np.testing.assert_array_equal(applied, [0.0, 0.0])
    assert status["state"] == "STANDBY"
    assert status["standby_reason"] == "model_contract_invalid"
    assert policy.session is None
    assert session.observations == []
