"""Test kinematic MPC on a circular path.

No ROS required — pure CasADi simulation.
Run: python test/test_mpc_circle.py
"""

import math
import sys
import time

import numpy as np

sys.path.insert(0, "..")
from usv_mpc.usv_model_kinematic import USVKinematicModel
from usv_mpc.mpc_kinematic import KinematicMPC
from usv_mpc.utils import normalize_angle


def generate_circle_reference(center_x, center_y, radius, theta_cur, dt, N, speed=1.0):
    """Generate a circular reference path for MPC."""
    ref = np.zeros((3, N + 1))
    ds = speed * dt
    for k in range(N + 1):
        theta = theta_cur + k * ds / radius
        ref[0, k] = center_x + radius * math.cos(theta)
        ref[1, k] = center_y + radius * math.sin(theta)
        ref[2, k] = normalize_angle(theta + math.pi / 2)
    return ref


def main():
    print("=== Circular Path Tracking Test ===")

    mpc = KinematicMPC(dt=0.2, N=20)
    model = USVKinematicModel(dt=0.2)

    center = (20.0, 20.0)
    radius = 15.0

    # Start on the circle at theta=0 (eastmost point), heading north
    x0 = np.array([center[0] + radius, center[1] + 3.0, math.pi / 2])

    state = x0.copy()
    T = 80.0
    n_steps = int(T / 0.2)

    history = [state.copy()]
    solve_times = []
    errors = []

    print(f"Circle: center=({center[0]},{center[1]}), r={radius}m")
    print(f"Initial: pos=({state[0]:.1f},{state[1]:.1f}), psi={math.degrees(state[2]):.0f}°")

    for i in range(n_steps):
        # Current angular position on circle
        dx = state[0] - center[0]
        dy = state[1] - center[1]
        theta_cur = math.atan2(dy, dx)

        ref = generate_circle_reference(center[0], center[1], radius, theta_cur, 0.2, 20)

        u_opt, info = mpc.solve(state, ref)

        if info["success"]:
            solve_times.append(info["solve_time_ms"])
            state = model.forward(state, u_opt)
            state[2] = normalize_angle(state[2])
            history.append(state.copy())

            # Radial tracking error
            actual_r = math.hypot(state[0] - center[0], state[1] - center[1])
            err = abs(actual_r - radius)
            errors.append(err)
        else:
            print(f"  Step {i}: solve failed - {info.get('error')}")

        if i % 25 == 0:
            print(f"  t={i*0.2:.1f}s  pos=({state[0]:.1f},{state[1]:.1f})  "
                  f"r_err={errors[-1]:.3f}m  solve={info['solve_time_ms']:.0f}ms")

    print(f"\nResults:")
    print(f"  Mean radial error: {np.mean(errors):.3f} m")
    print(f"  Max radial error:  {np.max(errors):.3f} m")
    print(f"  Mean solve time:   {np.mean(solve_times):.1f} ms")
    print(f"  Max solve time:    {np.max(solve_times):.1f} ms")

    assert np.mean(errors) < 2.0, f"Radial error too large: {np.mean(errors):.2f}m"
    print("\nPASS: Circular tracking within tolerances.")


if __name__ == "__main__":
    main()
