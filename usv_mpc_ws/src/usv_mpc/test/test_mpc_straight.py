"""Test kinematic MPC on a straight-line path.

No ROS required — pure CasADi simulation.
Run: python test/test_mpc_straight.py
"""

import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from usv_mpc.usv_model_kinematic import USVKinematicModel
from usv_mpc.mpc_kinematic import KinematicMPC
from usv_mpc.utils import normalize_angle


def generate_straight_reference(start_x, start_y, heading, length, dt, N):
    """Generate a straight reference path for MPC tracking."""
    ref = np.zeros((3, N + 1))
    for k in range(N + 1):
        dist = 1.0 * dt * k
        ref[0, k] = start_x + dist * math.cos(heading)
        ref[1, k] = start_y + dist * math.sin(heading)
        ref[2, k] = heading
    return ref


def main():
    print("=== Straight Line Tracking Test ===")

    mpc = KinematicMPC(dt=0.2, N=20)
    model = USVKinematicModel(dt=0.2)

    # Initial condition: offset from path at 45°
    heading = math.radians(45)
    x0 = np.array([0.0, 2.0, heading])  # 2m cross-track offset

    state = x0.copy()
    ref_heading = heading

    T = 60.0
    n_steps = int(T / 0.2)

    history = [state.copy()]
    solve_times = []
    errors = []

    print(f"Initial: x=({state[0]:.1f},{state[1]:.1f}), psi={math.degrees(state[2]):.0f}°")
    print(f"Simulating {n_steps} steps ({T}s)...")

    for i in range(n_steps):
        # Build reference ahead of the boat
        ref = generate_straight_reference(state[0], state[1], ref_heading, 80.0, 0.2, 20)

        u_opt, info = mpc.solve(state, ref)

        if info["success"]:
            solve_times.append(info["solve_time_ms"])
            # Move the boat
            state = model.forward(state, u_opt)
            state[2] = normalize_angle(state[2])
            history.append(state.copy())

            # Cross-track error (distance to line x=y)
            # Line passes through origin at 45°
            err = abs(state[0] - state[1]) / math.sqrt(2)
            errors.append(err)
        else:
            print(f"  Step {i}: solve failed - {info.get('error')}")

        if i % 25 == 0:
            print(f"  t={i*0.2:.1f}s  pos=({state[0]:.1f},{state[1]:.1f})  "
                  f"err={errors[-1]:.3f}m  solve={info['solve_time_ms']:.0f}ms")

    print(f"\nResults:")
    print(f"  Final position: ({state[0]:.1f}, {state[1]:.1f})")
    print(f"  Mean solve time: {np.mean(solve_times):.1f} ms")
    print(f"  Max solve time:  {np.max(solve_times):.1f} ms")
    print(f"  Mean cross-track error: {np.mean(errors):.3f} m")
    print(f"  Max cross-track error:  {np.max(errors):.3f} m")

    # Quick validation
    assert np.mean(errors) < 1.0, f"Tracking error too large: {np.mean(errors):.2f}m"
    assert np.mean(solve_times) < 200, f"Solve time too slow: {np.mean(solve_times):.0f}ms"
    print("\nPASS: Straight line tracking within tolerances.")


if __name__ == "__main__":
    main()
