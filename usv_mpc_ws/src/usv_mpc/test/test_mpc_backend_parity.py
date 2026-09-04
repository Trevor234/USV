"""acados vs IPOPT 后端对比 / 基准（方案 A 运动学 MPC）。

两种用法：
  * pytest（colcon test）：未装 acados 时整文件自动 skip，不影响 10/10。
  * 独立运行：python3 src/usv_mpc/test/test_mpc_backend_parity.py
    打印两后端的最优控制与求解耗时，供人工核对。

见 docs/acados_migration.md。
"""

import os
import sys
import time

import numpy as np
import pytest

# 允许独立运行时 import usv_mpc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from usv_mpc.mpc_kinematic import KinematicMPC

try:
    import acados_template  # noqa: F401
    HAS_ACADOS = True
except Exception:
    HAS_ACADOS = False


def _straight_ref(N: int) -> np.ndarray:
    ref = np.zeros((3, N + 1))
    for k in range(N + 1):
        ref[0, k] = k * 1.0  # 沿 +x 的直线，航向 0
    return ref


@pytest.mark.skipif(not HAS_ACADOS, reason="acados 未安装，跳过后端对比测试")
def test_acados_backend_sane():
    """acados 后端应成功求解并给出有界、有限的控制量。"""
    from usv_mpc.mpc_kinematic_acados import AcadosKinematicMPC

    N = 20
    mpc = AcadosKinematicMPC(dt=0.2, N=N, u_max=2.0, u_min=0.0, r_max=0.5)
    ref = _straight_ref(N)

    for state in (
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.1]),
        np.array([2.0, -1.0, -0.2]),
    ):
        u, info = mpc.solve(state, ref)
        assert info["success"], info.get("error")
        assert np.all(np.isfinite(u))
        assert -1e-6 <= u[0] <= 2.0 + 1e-6
        assert abs(u[1]) <= 0.5 + 1e-6
        assert info["X_pred"].shape == (3, N + 1)


@pytest.mark.skipif(not HAS_ACADOS, reason="acados 未安装，跳过后端对比测试")
def test_backends_roughly_agree():
    """同一问题下 acados(RTI) 与 IPOPT 的首步控制不应大幅背离。

    容差较松：RTI 单步迭代与 IPOPT 收敛解本就不会逐位相同。
    """
    from usv_mpc.mpc_kinematic_acados import AcadosKinematicMPC

    N = 20
    ref = _straight_ref(N)
    ipopt = KinematicMPC(dt=0.2, N=N)
    acados = AcadosKinematicMPC(dt=0.2, N=N)

    state = np.array([0.0, 0.8, 0.05])
    # 各跑几次让 warm-start / RTI 稳定
    for _ in range(5):
        u_i, _ = ipopt.solve(state, ref)
        u_a, _ = acados.solve(state, ref)

    assert abs(u_i[0] - u_a[0]) < 1.0
    assert abs(u_i[1] - u_a[1]) < 1.0


def main():
    if not HAS_ACADOS:
        print("acados 未安装。请先按 docs/acados_migration.md 阶段 0 安装后再运行。")
        return

    from usv_mpc.mpc_kinematic_acados import AcadosKinematicMPC

    N = 20
    ref = _straight_ref(N)
    state = np.array([0.0, 1.0, 0.1])

    print("=== 后端对比：acados(SQP_RTI) vs CasADi/IPOPT ===")
    ipopt = KinematicMPC(dt=0.2, N=N)
    acados = AcadosKinematicMPC(dt=0.2, N=N)

    def bench(mpc, label):
        for _ in range(5):  # warm
            mpc.solve(state, ref)
        ts = []
        u_last = None
        for _ in range(50):
            t0 = time.perf_counter()
            u, info = mpc.solve(state, ref)
            if info["success"]:
                ts.append((time.perf_counter() - t0) * 1000)
                u_last = u
        ts = np.array(ts)
        print(f"  {label:16s} u=[{u_last[0]:.3f}, {u_last[1]:.3f}]  "
              f"solve mean={ts.mean():.2f}ms max={ts.max():.2f}ms")
        return ts.mean()

    bench(ipopt, "IPOPT")
    bench(acados, "acados RTI")


if __name__ == "__main__":
    main()
