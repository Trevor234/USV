"""usv_rl — USV 轨迹跟踪强化学习（方案C）。

训练侧：Gymnasium 环境（Fossen 3-DOF Python 移植）+ PPO (Stable-Baselines3)。
部署侧：策略导出 ONNX 后由 usv_mpc_ws/src/usv_rl_ros 的 rl_policy_node 推理。
"""
__version__ = "0.1.0"
