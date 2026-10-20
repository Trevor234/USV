# usv_rl — USV 轨迹跟踪强化学习（方案C）

训练侧：**Gymnasium 环境 + PPO (Stable-Baselines3)**，纯 Python，不进 colcon。
部署侧：`usv_mpc_ws/src/usv_rl_ros`（`rl_policy_node`，ONNX 推理，接口与 mpc_node 对齐）。

## 与 MPC（方案B）的对齐点

| 项 | 值 | 对齐来源 |
|---|---|---|
| 决策频率 | 5 Hz（dt=0.2 s） | mpc_params.yaml `mpc_dt` |
| 动作空间 | [-1,1] 归一化 → [T_L,T_R] ∈ ±25N + 80 N/s 限率 | mpc_params.yaml 推力约束 |
| 奖励 | −MPC 代价（Q=[20,20,50,8,1,8], R=[0.05,0.05], Rd=[0.2,0.2]）+ 空间项(q=100) + 进度项(w=15) | mpc_params.yaml `dynamic.*` |
| 动力学 | Fossen 3-DOF RK4×4（与 C++ 200 步对拍 <1e-8） | usv_model_dynamic.cpp |
| 水动力参数 | usv_params_sim.yaml 快照（2026-09-03 辨识） | usv_bringup/config |
| 观测 | 43 维（相对量，无绝对 x/y） | usv_rl/observation.py 单一真源 |

## 训练成果（v5，随机路径 50 episode，DR 关闭；2026-09-30 初测，2026-10-06 同命令复现逐项一致）

| 指标 | LOS 基线 | PPO (v5 s4_dr) |
|---|---|---|
| 成功率 | 100% | 100% |
| 横向误差 RMS | 0.404 m | **0.312 m** |
| 横向误差 max | 1.172 m | **1.056 m** |
| 航向误差 RMS | 25.8° | **16.1°** |
| 单次推理 | — | 0.03 ms (ONNX) |
| 能耗均值 | 2416 N²·s | 7338 N²·s（精度换能耗的权衡，见教程 6.7） |

部署模型：`models/v5/s4_dr/policy_physical_n.onnx` + `policy_physical_n.manifest.json`（契约式导出：VecNormalize 折叠进图，图内 `clip(±1)×25N`，输出直接为物理推力 N；manifest 记录单位/维数/缩放/SHA256/对拍记录，部署节点加载时硬校验，不符即 STANDBY 零推力。经 domain randomization ±20% 水动力/推力延迟/观测噪声训练）。旧 `policy.onnx` 输出归一化动作 [-1,1]（缺物理缩放，2026-10-03 审计发现），仅留作诊断对照，勿再部署。

## 激励设计教训（五轮迭代，每轮一个 reward hacking）

| 轮 | 症状 | 根因 → 修复 |
|---|---|---|
| v1 | 倒车自尽（ep_len 23 步） | 存活罚 >> 速死罚 → 调度 rebase + 终端奖惩 |
| v2 | 0.24m 精度沿路径线倒车 | 前进回报 ≈ 死亡回报 → 进度权重 15 |
| v3 | ep_len 303→27 单调衰减 | 提前终止 = 求死通道 → 训练期取消提前终止 |
| sanity4 | 悬停蹭 rebase | ±25N 量纲下 PPO 探索只有 ±1N → 动作归一化 [-1,1] |
| v4/sanity5 | 直线冲线 / 赛车线甩宽 | rebase 让几何失约束；2m 封顶梯度饱和 → 空间项 q=100 |

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
usv_rl/export_policy.py   契约式 ONNX 导出（图内 ×25N + manifest + 独立 oracle 对拍 <1e-3 N）
tests/                    对拍 + API + 等价性 + 导出契约测试（pytest 收集 53 例）
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

# 评估（PPO vs LOS 基线；s4_dr 与上方成果表同源）
python -m usv_rl.evaluate --baseline los --episodes 50
python -m usv_rl.evaluate --model models/v5/s4_dr/model.zip \
    --vecnorm models/v5/s4_dr/vecnormalize.pkl --episodes 50

# 导出 ONNX（契约式；--thrust-scale-n 必填且只接受 25.0）
python -m usv_rl.export_policy --model models/v5/s4_dr/model.zip --thrust-scale-n 25.0
```

## VRX 验证（scheme C）

```bash
# 三层 source：/opt/ros/jazzy → vrx_ws/install → usv_mpc_ws/install
ros2 launch usv_bringup vrx.launch.py scheme:=C \
    rl_model:=$(pwd)/usv_rl/models/v5/s4_dr/policy_physical_n.onnx
# 对比方案 B（MPC）：
ros2 launch usv_bringup vrx.launch.py scheme:=B record_bag:=true run_id:=mpc_b_001
```

部署机（Pi5/Orin）需 `pip install` 本包（核心依赖仅 numpy/pyyaml/gymnasium）+ onnxruntime。
Ubuntu 24.04（PEP 668）系统 Python 安装命令（ROS 节点跑在系统 Python，不是训练 venv）：

```bash
python3 -m pip install --user --break-system-packages -e ~/USV/usv_rl
python3 -m pip install --user --break-system-packages onnxruntime
```
`real.launch.py` 的 scheme C（rc_override 模式）在部署阶段接入——节点需先移植
推力→PWM 映射（RcActuation，steering_sign=-1）。

## 已知坑（踩过的）

- **VecEnv 单环境动作形状**：`DummyVecEnv.step` 传 `(2,)` 会被取成标量——必须 `(1,2)`。
- **策略输出是归一化动作 [-1,1]，物理 N 必须显式缩放**：SB3 PPO 的高斯均值在动作空间量纲（[-1,1]），物理推力 = clip(mean)×25。缩放必须折叠进 ONNX 图并写入 manifest（`policy_physical_n.onnx`）——只在文档里"声明"物理量纲、图里不实现，就是 2026-10-03 单位 bug 的根源。
- **nav_msgs/Path 遮蔽 pathlib.Path**：ROS 节点导入需 alias。
- **ament_python 脚本目录**：需要 setup.cfg 指定 `install_scripts=$base/lib/<pkg>`。
- torch≥2.9 的 ONNX 导出用 `dynamo=False`；`action_net` 是单层 Linear，
  `.children()` 为空，要整层加入 Sequential。
