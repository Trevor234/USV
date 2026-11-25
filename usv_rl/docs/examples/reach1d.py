import gymnasium as gym
from gymnasium import spaces
import numpy as np

class Reach1DEnv(gym.Env):
    """最小教学环境：1 维小车间隔 dt 移动，到达目标点 x=1。"""
    metadata = {"render_modes": []}

    def __init__(self, dt=0.1, max_steps=100):
        super().__init__()
        self.dt, self.max_steps, self.step_i = dt, max_steps, 0
        self.observation_space = spaces.Box(-np.inf, np.inf, (2,), np.float32)  # [x, v]
        self.action_space = spaces.Box(-1.0, 1.0, (1,), np.float32)            # 加速度指令
        self._x, self._v = 0.0, 0.0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._rng = np.random.default_rng(seed)
        self._x = float(self._rng.uniform(-0.5, 0.0))
        self._v = 0.0
        self.step_i = 0
        return self._obs(), {}

    def step(self, action):
        a = float(np.clip(action[0], -1, 1))
        self._v += a * self.dt * 5.0
        self._x += self._v * self.dt
        self.step_i += 1
        err = abs(self._x - 1.0)
        reward = -(err ** 2)
        terminated = err < 0.05
        truncated = self.step_i >= self.max_steps
        return self._obs(), reward, terminated, truncated, {"err": err}

    def _obs(self):
        return np.array([self._x, self._v], dtype=np.float32)

    def close(self): ...
