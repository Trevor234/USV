import math

import numpy as np

from usv_mpc.utils import (
    body_to_ned,
    ned_to_body,
    normalize_angle,
    parse_profile_stamp,
    profile_sync_state,
    quaternion_to_yaw,
    sample_path_profile_at_time,
)


def test_local_map_body_rotation_semantics():
    vx, vy = body_to_ned(1.0, 0.0, math.pi / 2.0)
    assert abs(vx) < 1e-9
    assert abs(vy - 1.0) < 1e-9

    u, v = ned_to_body(vx, vy, math.pi / 2.0)
    assert abs(u - 1.0) < 1e-9
    assert abs(v) < 1e-9


def test_quaternion_to_yaw_ros_semantics():
    yaw = math.pi / 2.0
    assert abs(quaternion_to_yaw(0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)) - yaw) < 1e-9
    assert abs(normalize_angle(3.0 * math.pi) - math.pi) < 1e-9


class _Dim:
    def __init__(self, label):
        self.label = label


class _Layout:
    def __init__(self, labels):
        self.dim = [_Dim(label) for label in labels]


def test_profile_stamp_parsing_and_sync_state():
    layout = _Layout(["points", "v_kappa_r_t", "stamp_sec:12", "stamp_nanosec:34"])
    stamp = parse_profile_stamp(layout)
    assert stamp == (12, 34)
    assert profile_sync_state(3, 3, (12, 34), stamp) == (True, "stamp_match")
    assert profile_sync_state(3, 3, (12, 35), stamp) == (False, "stamp_mismatch")
    assert profile_sync_state(3, 2, (12, 34), stamp) == (False, "length_mismatch")
    assert profile_sync_state(3, 3, (12, 34), None) == (True, "legacy_no_profile_stamp")


def test_sample_at_time_interpolates_heading_and_speed():
    path = [[0.0, 0.0, 0.0], [10.0, 0.0, math.pi / 2.0]]
    x, y, psi, v, r, j = sample_path_profile_at_time(
        path, [0.0, 10.0], [1.0, 3.0], [0.0, 0.2], 5.0, 0
    )
    assert np.isclose(x, 5.0)
    assert np.isclose(y, 0.0)
    assert np.isclose(psi, math.pi / 4.0)
    assert np.isclose(v, 2.0)
    assert np.isclose(r, 0.1)
    assert j == 0
