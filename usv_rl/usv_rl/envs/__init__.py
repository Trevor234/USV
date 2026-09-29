"""Gymnasium 环境注册。"""
import gymnasium as gym

from usv_rl.envs.usv_tracking_env import UsvTrackingEnv

_ENV_ID = "usv/USVTracking-v0"

if _ENV_ID not in gym.registry:
    gym.register(
        id=_ENV_ID,
        entry_point="usv_rl.envs.usv_tracking_env:UsvTrackingEnv",
    )

__all__ = ["UsvTrackingEnv", "_ENV_ID"]
