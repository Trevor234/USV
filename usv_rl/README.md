# usv_rl — USV 轨迹跟踪强化学习（方案C）

训练侧：**Gymnasium 环境 + PPO (Stable-Baselines3)**，纯 Python，不进 colcon。
部署侧：`usv_mpc_ws/src/usv_rl_ros`（`rl_policy_node`，ONNX 推理，接口与 mpc_node 对齐）。

## 与 MPC（方案B）的对齐点

| 项 | 值 | 对齐来源 |
|---|---|---|
| 决策频率 | 5 Hz（dt=0.2 s） | mpc_params.yaml `mpc_dt` |
| 动作空间 | [-1,1] 归一化 → [T_L,T_R] ∈ ±25N + 80 N/s 限率 | mpc_params.yaml 推力约束 |
| 奖励 | −MPC 代价（q_ct=100, q_ψ=50, q_u=8, q_v=1, q_r=8, R=[0.05,0.05], Rd=[0.2,0.2]）+ 进度项(w=15)；位置项用**路径折线横向误差 e_ct**（平方-线性过渡，`usv_rl/envs/reward.py`） | mpc_params.yaml `dynamic.*` |
| 动力学 | Fossen 3-DOF RK4×4（与 C++ 200 步对拍 <1e-8） | usv_model_dynamic.cpp |
| 水动力参数 | usv_params_sim.yaml 快照（2026-09-03 辨识） | usv_bringup/config |
| 观测 | 43 维（相对量，无绝对 x/y）；契约 `ppo-obs-v2`：e_ψ/v_ref/r_ref 取**进度索引**，前瞻 [0.4,0.8,1.4,2.2,3.2,4.4,5.8,7.5] m，进度窗口 8 点 + 1.0 m 距离门 | usv_rl/observation.py 单一真源（部署节点同值副本，`tests/test_obs_contract_parity.py` 逐位锁定） |

## 训练成果（v5，随机路径 50 episode，DR 关闭；2026-09-30 初测，2026-10-06 同命令复现逐项一致）

| 指标 | LOS 基线 | PPO (v5 s4_dr) |
|---|---|---|
| 成功率 | 100% | 100% |
| 横向误差 RMS | 0.404 m | **0.312 m** |
| 横向误差 max | 1.172 m | **1.056 m** |
| 航向误差 RMS | 25.8° | **16.1°** |
| 单次推理 | — | 0.03 ms (ONNX) |
| 能耗均值 | 2416 N²·s | 7338 N²·s（精度换能耗的权衡，见教程 6.7） |

部署模型：`../artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx` + `policy_physical_n.manifest.json`（契约式导出：VecNormalize 折叠进图，图内 `clip(±1)×25N`，输出直接为物理推力 N；manifest 记录单位/维数/缩放/SHA256/对拍记录，部署节点加载时硬校验，不符即 STANDBY 零推力。经 domain randomization ±20% 水动力/推力延迟/观测噪声训练）。旧 `policy.onnx` 输出归一化动作 [-1,1]（缺物理缩放，2026-10-03 审计发现），仅留作诊断对照，勿再部署。

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

训练产物不在本目录：`models/` → `../artifacts/rl_models/`，`runs/` → `../artifacts/rl_runs/`。
路径由 `usv_rl/paths.py` 统一解析（可用 `USV_ARTIFACTS_DIR` 覆盖）。

## 使用

```bash
cd usv_rl
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[train,deploy]   # 或按 pyproject 手动装

# 测试（M1 动力学对拍 / M2 环境与基线）
pytest tests/ -q

# 训练（全课程 10M 步：直航→Z字→随机→DR）
# 默认 device=cpu（见 configs/ppo.yaml 的说明）；试 GPU 加 --device cuda，实测约 1.28x
python -m usv_rl.train --run-name v1 --n-envs 16
tensorboard --logdir ../artifacts/rl_runs/

# 评估（PPO vs LOS 基线；s4_dr 与上方成果表同源）
python -m usv_rl.evaluate --baseline los --episodes 50
python -m usv_rl.evaluate --model ../artifacts/rl_models/v5/s4_dr/model.zip \
    --vecnorm ../artifacts/rl_models/v5/s4_dr/vecnormalize.pkl --episodes 50

# 导出 ONNX（契约式；--thrust-scale-n 必填且只接受 25.0）
python -m usv_rl.export_policy --model ../artifacts/rl_models/v5/s4_dr/model.zip --thrust-scale-n 25.0
```

## VRX 验证（scheme C）

```bash
# 三层 source：/opt/ros/jazzy → vrx_ws/install → usv_mpc_ws/install
ros2 launch usv_bringup vrx.launch.py scheme:=C \
    rl_model:=$(pwd)/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx
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

## 观测契约 `ppo-obs-v2`（2026-11-22）

- `LOOKAHEAD_M = (0.4, 0.8, 1.4, 2.2, 3.2, 4.4, 5.8, 7.5)`：由方案 A 三臂闭环消融定值
  （42 eps/arm：la40 Δ=−0.00031、la75 Δ=+0.00120、判据 `adopt_training=False`；
  一致性优先，训练与部署取同一元组）。
- `e_psi / v_ref / r_ref` 一律取 `prog_idx`（单调推进最近点），**不再取时间索引**：
  时间索引在落后/超前时给出与船实际状态错位的参考，且 rebase 平移量是未进入观测的隐藏状态。
- 进度搜索 = 窗口 8 点（≤4 m/步）+ 距离门 1.0 m；两者缺一都会让"抄近道"记满进度。
- 成功判据 = 到末段 ∧ 终点 1.0 m 内 ∧ 全程 max|e_ct| ≤ 0.75 m；只判"到终点"会奖励
  沿直线蒙到目标、全程离航线 5 m+ 的策略（`tests/test_env_api.py::test_beeline_policy_scores_zero_success`）。
- 导出必须带 `--train-meta <run>/train_meta.json`：manifest 写入 `observation_contract`
  （version/lookahead_m/prev_thrust_timing/reference_index），部署节点按 manifest 做绑定校验。

闭环效果（方案 A 受控仿真，calibration 12 eps × 3 seeds 配对）：冻结 v5 权重在 `ppo-obs-v2`
下 ΔCTE = **−0.0047 m**（95% CI [−0.0056,−0.0037]，W/T/L 34/0/2）；旧契约下同一权重为 +0.0012。
即 R5 的"融合无增益"主要来自观测语义错位，而不是网络容量或训练步数。

## 方案 A Phase 2 受控仿真默认策略

Phase 2 选定的 Option A 平衡配置为 `gp_v6_fusion_direct_best_001`，使用
`v6_fusion_direct/best` 的 PPO 策略、`ppo-obs-v2` 观测契约及融合权重 `λ_π=0.001`。
方案 A 工作区的 `scheme_a_active_energy_policy.json` 固定了能耗执行契约、pooled GP 快照、
ONNX 和 manifest 的路径及 SHA-256。闭环运行器默认选择该 ONNX 和 manifest。运行此配置时，
显式传入能耗契约 `--contract`、pooled GP 快照 `--gp-snapshot` 和
`--ppo-proposal --lambda-pi 0.001`。
