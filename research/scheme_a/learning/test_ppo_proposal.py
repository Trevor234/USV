#!/usr/bin/env python3
"""Tests for Scheme A PPO proposal engine & observation contract (WP5)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from ppo_proposal_node import (
    DEFAULT_LOOKAHEAD,
    OBS_CONTRACT_VERSION,
    ProposalEngine,
    compose_observation_scheme_a,
)


def test_compose_observation_scheme_a_matches_usv_rl_source_exact() -> None:
    """Verify our standalone observation assembler matches `usv_rl.observation` bit-for-bit."""
    rng = np.random.default_rng(7)
    n = 40
    t = np.arange(n, dtype=np.float64) * 0.2
    xs = t * 0.7
    ys = 0.2 * np.sin(0.3 * t)
    psis = np.arctan2(np.gradient(ys, 0.2), np.gradient(xs, 0.2))
    vs = np.full(n, 0.7, dtype=np.float64)
    rs = np.gradient(psis, 0.2)
    ss = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))])
    kappas = rs / vs
    st = np.array([1.5, 0.05, 0.1, 0.68, -0.02, 0.05], dtype=np.float64)
    prev_q = np.array([6.5, -2.1], dtype=np.float64)
    local_obs = compose_observation_scheme_a(st, xs, ys, psis, kappas, vs, rs, ss, t, 2.2, 5, prev_q)

    # Cross-check against usv_rl/.venv's usv_rl.observation.compose_observation.
    payload = {
        "st": st.tolist(), "xs": xs.tolist(), "ys": ys.tolist(), "psis": psis.tolist(),
        "kappas": kappas.tolist(), "vs": vs.tolist(), "rs": rs.tolist(), "ss": ss.tolist(),
        "t": t.tolist(), "t_now": 2.2, "prog_idx": 5, "prev_q": prev_q.tolist(),
        "lookahead": list(DEFAULT_LOOKAHEAD),
    }
    script = (
        "import json, sys, numpy as np; "
        "from usv_rl.observation import compose_observation; "
        "d = json.loads(sys.stdin.read()); "
        "out = compose_observation(np.array(d['st']), np.array(d['xs']), np.array(d['ys']), "
        "np.array(d['psis']), np.array(d['kappas']), np.array(d['vs']), np.array(d['rs']), "
        "np.array(d['ss']), np.array(d['t']), d['t_now'], d['prog_idx'], np.array(d['prev_q']), tuple(d['lookahead'])); "
        "print(json.dumps(out.tolist()))"
    )
    proc = subprocess.run(
        ["/home/trevor/USV/usv_rl/.venv/bin/python", "-c", script],
        env={"PYTHONPATH": "/home/trevor/USV/usv_rl"},
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    ref_obs = np.asarray(json.loads(proc.stdout), dtype=np.float32)
    assert local_obs.shape == (43,)
    np.testing.assert_allclose(local_obs, ref_obs, atol=1e-7)


def test_proposal_engine_freshness_confirmed_feedback_and_bounds() -> None:
    eng = ProposalEngine(run_id="r1", boot_id="b1", max_odom_age_ns=120_000_000)

    # 1) Missing inputs fail gracefully with valid=False
    p0 = eng.evaluate()
    assert not p0.valid and p0.reason == "clock_missing"

    eng.on_clock(1_000_000_000)
    p1 = eng.evaluate()
    assert not p1.valid and p1.reason == "odom_missing"

    # 2) Stale odom rejected
    eng.on_odom(700_000_000, [0.0, 0.0, 0.0, 0.5, 0.0, 0.0])
    p2 = eng.evaluate()
    assert not p2.valid and p2.reason == "odom_stale"

    # 3) Missing reference rejected
    eng.on_odom(1_000_000_000, [0.5, 0.0, 0.0, 0.6, 0.0, 0.0])
    p3 = eng.evaluate()
    assert not p3.valid and p3.reason == "reference_missing"

    # 4) Provide reference and check valid proposal + confirmed hold thrust window
    t = np.arange(50, dtype=np.float64) * 0.2
    path = np.column_stack([t * 0.7, np.zeros_like(t), np.zeros_like(t)])
    prof = np.column_stack([np.full_like(t, 0.7), np.zeros_like(t), np.zeros_like(t), t])
    eng.on_reference(path, prof)

    p_zero = eng.evaluate()
    assert p_zero.valid
    assert p_zero.obs_contract_version == OBS_CONTRACT_VERSION
    assert p_zero.target_tick == 6
    assert p_zero.inference_ms >= 0.0
    assert -25.0 <= p_zero.q_pi[0] <= 25.0 and -25.0 <= p_zero.q_pi[1] <= 25.0

    # Inject confirmed execution receipt covering [800ms, 1000ms] & [1000ms, 1200ms]
    eng.on_plant_receipt(
        schema_version="p1-plant-receipt-v3",
        disposition="ok",
        execution_index=4,
        state_sample_sim_ns=800_000_000,
        planned_window_end_sim_ns=1_000_000_000,
        thrust_n=[12.0, -4.0],
        clock_epoch=0,
    )
    np.testing.assert_allclose(eng.confirmed_prev_thrust(1_000_000_000), [12.0, -4.0])
    # Once closed at 900ms, querying at 1000ms returns zero hold thrust!
    eng.on_hold_close(
        schema_version="p1-plant-hold-close-v2",
        execution_index=4,
        close_sim_ns=900_000_000,
        clock_epoch=0,
    )
    np.testing.assert_allclose(eng.confirmed_prev_thrust(1_000_000_000), [0.0, 0.0])

    # Non-v3 receipt must be ignored
    eng.on_plant_receipt(
        schema_version="p1-plant-receipt-v2",
        disposition="ok",
        execution_index=5,
        state_sample_sim_ns=1_000_000_000,
        planned_window_end_sim_ns=1_200_000_000,
        thrust_n=[10.0, 10.0],
        clock_epoch=0,
    )
    np.testing.assert_allclose(eng.confirmed_prev_thrust(1_100_000_000), [0.0, 0.0])


def test_proposal_engine_rejects_tampered_manifest(tmp_path: Path) -> None:
    manifest = json.loads(Path("/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.manifest.json").read_text())
    manifest["onnx_sha256"] = "0" * 64
    bad_man = tmp_path / "bad.manifest.json"
    bad_man.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        ProposalEngine(manifest_path=bad_man)


def test_ppo_proposal_node_live_ros2_pubsub(tmp_path: Path) -> None:
    """Spawn ppo_proposal_node.py in an isolated ROS_DOMAIN_ID and verify live ControlProposal pub/sub."""
    rclpy = pytest.importorskip("rclpy")
    from usv_research_interfaces.msg import ControlProposal, PlantReceipt
    from rosgraph_msgs.msg import Clock
    from nav_msgs.msg import Odometry, Path as NavPath
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import Float64MultiArray
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    import os
    import time

    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = "97"
    env["ROS_LOCALHOST_ONLY"] = "1"
    log_path = tmp_path / "ppo_live.jsonl"
    node_script = str(Path(__file__).with_name("ppo_proposal_node.py"))
    proc = subprocess.Popen(
        [
            "/usr/bin/python3",
            node_script,
            "--run-id", "live_wp5_test",
            "--boot-id", "boot_wp5_test",
            "--rate-hz", "20.0",
            "--log-file", str(log_path),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.environ["ROS_DOMAIN_ID"] = "97"
    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    try:
        rclpy.init()
        tester = rclpy.create_node("wp5_live_tester")
        received: list[ControlProposal] = []
        sub = tester.create_subscription(ControlProposal, "/p1/control_proposal", received.append, 10)
        sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        latched_qos = QoSProfile(depth=16, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        pub_clock = tester.create_publisher(Clock, "/clock", sensor_qos)
        pub_odom = tester.create_publisher(Odometry, "/wamv/sensors/position/ground_truth_odometry", sensor_qos)
        pub_path = tester.create_publisher(NavPath, "/path/reference", 4)
        pub_prof = tester.create_publisher(Float64MultiArray, "/path/reference_profile", 4)
        pub_rec = tester.create_publisher(PlantReceipt, "/p1/plant_receipt", latched_qos)

        # Wait briefly for initial invalid proposal before inputs arrive.
        t0 = time.monotonic()
        while time.monotonic() - t0 < 4.0 and not any((not m.valid and m.reason == "clock_missing") for m in received):
            rclpy.spin_once(tester, timeout_sec=0.05)
        assert any((not m.valid and m.reason == "clock_missing") for m in received)

        # Publish reference path + profile, receipt, clock, and odom.
        nav = NavPath()
        prof = Float64MultiArray()
        for k in range(30):
            ps = PoseStamped()
            ps.pose.position.x = k * 0.2 * 0.7
            ps.pose.orientation.w = 1.0
            nav.poses.append(ps)
            prof.data.extend([0.7, 0.0, 0.0, k * 0.2])

        rec = PlantReceipt()
        rec.schema_version = "p1-plant-receipt-v3"
        rec.disposition = "ok"
        rec.execution_index = 4
        rec.state_sample_sim_ns = 800_000_000
        rec.planned_window_end_sim_ns = 1_000_000_000
        rec.thrust_n = [6.0, 6.0]
        rec.clock_epoch = 0

        clk = Clock()
        clk.clock.sec = 1
        clk.clock.nanosec = 0
        odom = Odometry()
        odom.header.stamp.sec = 1
        odom.header.stamp.nanosec = 0
        odom.pose.pose.position.x = 0.5
        odom.pose.pose.orientation.w = 1.0
        odom.twist.twist.linear.x = 0.65

        pub_rec.publish(rec)
        pub_path.publish(nav)
        pub_prof.publish(prof)
        t1 = time.monotonic()
        while time.monotonic() - t1 < 5.0 and not any(m.valid for m in received):
            pub_clock.publish(clk)
            pub_odom.publish(odom)
            rclpy.spin_once(tester, timeout_sec=0.05)

        valid_msgs = [m for m in received if m.valid]
        assert valid_msgs, f"expected valid ControlProposal, got reasons={[m.reason for m in received[-5:]]}"
        last = valid_msgs[-1]
        assert last.run_id == "live_wp5_test"
        assert last.boot_id == "boot_wp5_test"
        assert last.obs_contract_version == OBS_CONTRACT_VERSION
        assert -25.0 <= last.q_pi[0] <= 25.0 and -25.0 <= last.q_pi[1] <= 25.0
        assert last.target_tick == 6
        tester.destroy_subscription(sub)
        tester.destroy_node()
        rclpy.shutdown()
    finally:
        proc.terminate()
        rc = proc.wait(timeout=5)
        assert rc in (0, -15)
    assert log_path.is_file() and log_path.stat().st_size > 0
