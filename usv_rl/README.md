# usv_rl — USV 轨迹跟踪强化学习（方案C）

训练侧：**Gymnasium 环境 + PPO (Stable-Baselines3)**，纯 Python，不进 colcon。
部署侧：`usv_mpc_ws/src/usv_rl_ros`（`rl_policy_node`，ONNX 推理，接口与 mpc_node 对齐）。

## 与 MPC（方案B）的对齐点

| 项 | 值 | 对齐来源 |
|---|---|---|
| 决策频率 | 5 Hz（dt=0.2 s） | mpc_params.yaml `mpc_dt` |
| 动作空间 | [T_L, T_R] ∈ ±25 N + 80 N/s 限率 | mpc_params.yaml 推力约束 |
| 奖励 | −MPC 代价（Q=[20,20,50,8,1,8], R=[0.05,0.05], Rd=[0.2,0.2]）+ 进度项 | mpc_params.yaml `dynamic.*` |
| 动力学 | Fossen 3-DOF RK4×4（与 C++ 200 步对拍 <1e-8） | usv_model_dynamic.cpp |
| 水动力参数 | usv_params_sim.yaml 快照（2026-09-03 辨识） | usv_bringup/config |
| 观测 | 43 维（相对量，无绝对 x/y） | usv_rl/observation.py 单一真源 |

## 目录

```
configs/env.yaml    环境参数（执行器约束/奖励权重/DR/初始扰动）
configs/ppo.yaml    PPO 超参 + 课程学习阶段
usv_rl/dynamics.py        Fossen 3-DOF（C++ 移植）
usv_rl/reference.py       随机路径 + 简化 TOPP 剖面
usv_rl/envs/              UsvTrackingEnv（usv/USVTracking-v0）
usv_rl/observation.py     观测构建单一真源（ROS 节点共用）
usv_rl/baselines/         LOS+PD 解析基线
usv_rl/train.py           PPO 训练（课程/评估回调/TensorBoard）
usv_rl/evaluate.py        指标评估（成功率/横向误差/能耗/平滑度）
usv_rl/export_policy.py   ONNX 导出（含 VecNormalize 折叠，对拍 <1e-3 N）
tests/                    对拍 + API + 等价性测试（17 个）
```

## 使用

```bash
cd usv_rl
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[train,deploy]   # 或按 pyproject 手动装

# 测试（M1 动力学对拍 / M2 环境与基线）
pytest tests/ -q

# 训练（全课程 10M 步：直航→Z字→随机→DR）
python -m usv_rl.train --run-name v1 --n-envs 16
tensorboard --logdir runs/

# 评估（PPO vs LOS 基线）
python -m usv_rl.evaluate --baseline los --episodes 50
python -m usv_rl.evaluate --model models/v1/best/best_model.zip \
    --vecnorm models/v1/best/vecnormalize.pkl --episodes 50

# 导出 ONNX（部署）
python -m usv_rl.export_policy --model models/v1/best/best_model.zip
```

## VRX 验证（scheme C）

```bash
# 三层 source：/opt/ros/jazzy → vrx_ws/install → usv_mpc_ws/install
ros2 launch usv_bringup vrx.launch.py scheme:=C \
    rl_model:=$(pwd)/usv_rl/models/v1/policy.onnx
# 对比方案 B（MPC）：
ros2 launch usv_bringup vrx.launch.py scheme:=B record_bag:=true run_id:=mpc_b_001
```

部署机（Pi5/Orin）需 `pip install` 本包（核心依赖仅 numpy/pyyaml/gymnasium）+ onnxruntime。
`real.launch.py` 的 scheme C（rc_override 模式）在部署阶段接入——节点需先移植
推力→PWM 映射（RcActuation，steering_sign=-1）。

## 已知坑（踩过的）

- **VecEnv 单环境动作形状**：`DummyVecEnv.step` 传 `(2,)` 会被取成标量——必须 `(1,2)`。
- **SB3 PPO 高斯均值已是物理量纲**：导出 ONNX 只需 clip，不要 tanh 反缩放。
- **nav_msgs/Path 遮蔽 pathlib.Path**：ROS 节点导入需 alias。
- **ament_python 脚本目录**：需要 setup.cfg 指定 `install_scripts=$base/lib/<pkg>`。
- torch≥2.9 的 ONNX 导出用 `dynamo=False`；`action_net` 是单层 Linear，
  `.children()` 为空，要整层加入 Sequential。
