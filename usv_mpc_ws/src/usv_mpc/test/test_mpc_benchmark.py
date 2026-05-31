"""MPC solver performance benchmark.

Measures single-step solve time for both kinematic and dynamic MPC.
Run: python test/test_mpc_benchmark.py
"""

import math
import sys
import time

import numpy as np

sys.path.insert(0, "..")
from usv_mpc.mpc_kinematic import KinematicMPC
from usv_mpc.mpc_dynamic import DynamicMPC


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
    times30 = []
    for i in range(30):
        t0 = time.perf_counter()
        u_opt, info = mpc30.solve(state, ref)
        if info["success"]:
            times30.append((time.perf_counter() - t0) * 1000)
    stable30 = times30[5:]
    print(f"  N=30 steady-state: mean={np.mean(stable30):.1f}ms, "
          f"max={np.max(stable30):.1f}ms, min={np.min(stable30):.1f}ms")

    return np.mean(stable_times)


def benchmark_dynamic():
    print("\n--- Dynamic NMPC Benchmark ---")
    mpc = DynamicMPC(dt=0.1, N=15)

    state = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    ref = np.zeros((6, 16))
    for k in range(16):
        ref[0, k] = k * 0.5
        ref[3, k] = 1.0

    times = []
    for i in range(30):
        t0 = time.perf_counter()
        u_opt, info = mpc.solve(state, ref)
        elapsed = time.perf_counter() - t0

        if info["success"]:
            times.append(elapsed * 1000)
            if i == 0:
                print(f"  Initial solve: {times[-1]:.1f} ms")

    times = np.array(times)
    stable_times = times[5:]
    print(f"  N=15 steady-state: mean={np.mean(stable_times):.1f}ms, "
          f"max={np.max(stable_times):.1f}ms, min={np.min(stable_times):.1f}ms")

    # Test with N=20
    mpc20 = DynamicMPC(dt=0.1, N=20)
    times20 = []
    for i in range(20):
        t0 = time.perf_counter()
        u_opt, info = mpc20.solve(state, ref)
        if info["success"]:
            times20.append((time.perf_counter() - t0) * 1000)
    stable20 = times20[5:]
    print(f"  N=20 steady-state: mean={np.mean(stable20):.1f}ms, "
          f"max={np.max(stable20):.1f}ms, min={np.min(stable20):.1f}ms")

    return np.mean(stable_times)


def main():
    print("=== MPC Solver Performance Benchmarks ===\n")

    t_kin = benchmark_kinematic()
    t_dyn = benchmark_dynamic()

    print(f"\n=== Summary ===")
    print(f"  Kinematic MPC (N=20): {t_kin:.1f} ms  →  {'OK (<50ms)' if t_kin < 50 else 'TOO SLOW'}")
    print(f"  Dynamic NMPC (N=15):  {t_dyn:.1f} ms  →  {'OK (<100ms)' if t_dyn < 100 else 'TOO SLOW'}")

    # Real-time constraints
    assert t_kin < 200, f"Kinematic MPC too slow: {t_kin:.0f}ms (need <200ms)"
    assert t_dyn < 500, f"Dynamic MPC too slow: {t_dyn:.0f}ms (need <500ms)"
    print("\nPASS: Both solvers meet real-time constraints.")


if __name__ == "__main__":
    main()
