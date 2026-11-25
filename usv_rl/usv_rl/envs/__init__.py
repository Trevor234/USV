"""Gymnasium 环境注册。"""
import gymnasium as gym

import os
from pathlib import Path

from usv_rl.envs.usv_tracking_env import UsvTrackingEnv

_ENV_ID = "usv/USVTracking-v0"

if _ENV_ID not in gym.registry:
    gym.register(
        id=_ENV_ID,
        entry_point="usv_rl.envs.usv_tracking_env:UsvTrackingEnv",
    )

FUSION_ENV = os.environ.get("FUSION_ENV", "") not in ("", "0", "false", "False")
SCHEME_A_LEARNING_DIR = Path(
    os.environ.get(
        "USV_SCHEME_A_LEARNING_DIR",
        "/home/trevor/usv_scheme_a_wt/research/scheme_a/learning",
    )
)
# P5：融合闭环训练。FUSION_ENV=1 时把合约/GP/λπ 通过环境变量传进来，
# 由 scheme A 目录里的 fusion_env 构造环境（usv_rl 不反向依赖 scheme A 源码树）。
FUSION_CONTRACT = os.environ.get("USV_FUSION_CONTRACT", "")
FUSION_GP = os.environ.get("USV_FUSION_GP", "")
FUSION_LAMBDA_PI = float(os.environ.get("USV_FUSION_LAMBDA_PI", "0.0005"))
FUSION_SOLVER_LIB = os.environ.get("USV_ACADOS_LIB", "") or None


def make_env_factory(env_cfg: dict, seed: int, fusion_cfg: dict | None = None):
    """返回一个生成 env 的工厂：FUSION_ENV=1 走融合闭环，否则走方案C环境。"""
    if not FUSION_ENV:
        return None
    if not (FUSION_CONTRACT and FUSION_GP):
        raise RuntimeError(
            "FUSION_ENV=1 需要 USV_FUSION_CONTRACT 与 USV_FUSION_GP（并向 USV_SCHEME_A_LEARNING_DIR 提供脚本）"
        )
    import sys

    if str(SCHEME_A_LEARNING_DIR) not in sys.path:
        sys.path.insert(0, str(SCHEME_A_LEARNING_DIR))
    from fusion_env import make_fusion_env

    fusion_cfg = fusion_cfg or {}
    lambda_pi = float(fusion_cfg.get("lambda_pi", FUSION_LAMBDA_PI))
    penalty_kwargs = {}
    if "r_qpi_u0" in fusion_cfg:
        penalty_kwargs["r_qpi_u0"] = float(fusion_cfg["r_qpi_u0"])
    return make_fusion_env(
        env_cfg, seed,
        contract_path=Path(FUSION_CONTRACT), gp_snapshot=Path(FUSION_GP),
        lambda_pi=lambda_pi, solver_lib=FUSION_SOLVER_LIB, **penalty_kwargs,
    )


__all__ = ["UsvTrackingEnv", "_ENV_ID", "make_env_factory", "FUSION_ENV"]
