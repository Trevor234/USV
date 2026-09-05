"""MPC solver performance benchmark.

Measures single-step solve time for the kinematic MPC.
Run: python test/test_mpc_benchmark.py
"""

import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from usv_mpc.mpc_kinematic import KinematicMPC


def benchmark_kinematic():
    print("--- Kinematic MPC Benchmark ---")
    mpc = KinematicMPC(dt=0.2, N=20)

    # Random reference path
    np.random.seed(42)
    state = np.array([0.0, 0.0, 0.0])
    ref = np.zeros((3, 21))
    for k in range(21):
        ref[0, k] = k * 1.0
        ref[1, k] = 0.0
        ref[2, k] = 0.0

    times = []
    for i in range(50):
        t0 = time.perf_counter()
        u_opt, info = mpc.solve(state, ref)
        elapsed = time.perf_counter() - t0

        if info["success"]:
            times.append(elapsed * 1000)
            if i == 0:
                print(f"  Initial solve: {times[-1]:.1f} ms")

    times = np.array(times)
    # Skip first few for warm cache
    stable_times = times[5:]
    print(f"  N=20 steady-state: mean={np.mean(stable_times):.1f}ms, "
          f"max={np.max(stable_times):.1f}ms, min={np.min(stable_times):.1f}ms")

    # Test with N=30
    mpc30 = KinematicMPC(dt=0.2, N=30)
    ref30 = np.zeros((3, 31))
    for k in range(31):
        ref30[0, k] = k * 1.0
    times30 = []
    for i in range(30):
        t0 = time.perf_counter()
        u_opt, info = mpc30.solve(state, ref30)
        if info["success"]:
            times30.append((time.perf_counter() - t0) * 1000)
    stable30 = times30[5:]
    print(f"  N=30 steady-state: mean={np.mean(stable30):.1f}ms, "
          f"max={np.max(stable30):.1f}ms, min={np.min(stable30):.1f}ms")

    return np.mean(stable_times)


def main():
    print("=== MPC Solver Performance Benchmarks ===\n")

    t_kin = benchmark_kinematic()

    print(f"\n=== Summary ===")
    print(f"  Kinematic MPC (N=20): {t_kin:.1f} ms  →  {'OK (<50ms)' if t_kin < 50 else 'TOO SLOW'}")

    # Real-time constraints
    assert t_kin < 200, f"Kinematic MPC too slow: {t_kin:.0f}ms (need <200ms)"
    print("\nPASS: Solver meets real-time constraints.")


if __name__ == "__main__":
    main()
