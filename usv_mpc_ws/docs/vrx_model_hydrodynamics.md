# VRX 船模与水动力配置（2026-09-14）

已经将 `vrx.launch.py` 的默认船替换为按辨识 YAML 生成的原生 SDF 单体船。
船壳是自建的封闭 V 底、折角、外飘舷侧网格，带设备舱、GNSS 外罩、左右舷灯和小型双推进器。
外观来自参数化设计，**不是实船 CAD 复刻**；设备细节没有实测依据。

![生成模型的几何预览](../artifacts/vrx_model/preview.png)

## 1. 原模型为什么对不上辨识参数

旧 `usv_mono.urdf.xacro` 使用 2.0 × 0.6 × 0.4 m、30 kg 箱体，复用了两套
WAM-V 推进器；每套发动机 15 kg、桨 0.5 kg，IMU 另有 0.1 kg。
完整模型约 **61.1 kg**，并不是参数文件里的 14.2 kg。
旧动力学 Xacro 的附加质量与阻尼也还是早期估计值。

现在生成器把总质量、总重心、总惯量中的旋转桨质量扣除后分配给主体，避免重复计入。
原来的两个 Xacro 仅保留用于旧试验复现，已标注 LEGACY，当前 launch 不加载它们。

## 2. 参数入口与实际加载过程

| 文件 / 产物 | 用途 |
|---|---|
| `src/usv_bringup/config/usv_params_sim.yaml` | 默认辨识参数快照，保存原始数值 |
| `src/usv_simulation/config/vrx_model.yaml` | 未辨识的三维参数、推进器外观、附加质量处理策略 |
| `src/usv_simulation/usv_simulation/vrx_model.py` | 同时生成网格、SDF、TF 用 URDF、有效参数和报告 |
| `model.sdf` | Gazebo 实际加载的物理模型 |
| `effective_vehicle.yaml` | 生成后的有效参数；方案 B 的 MPC 也加载此文件 |
| `model_report.json` | 输入路径、重心、惯量、排水量和参数处理记录 |

启动时重新生成，默认存放在 `/tmp/usv_vrx_*`，终端会打印路径。
`model_output_dir:=...` 可以指定保存位置。
**不要只修改生成后的 SDF 或只改 MPC 参数**：下次启动会重新生成，且会造成植物与控制器不一致。

原始参数文件的数值没有被改写。也可以使用实船参数文件作为共同输入：

```bash
ros2 launch usv_bringup vrx.launch.py world:=usv_calm \
  vehicle_config:=/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/usv_params.yaml
```

方案 A 的推力内环也从这套有效参数读取桨距、纵向/艏摇阻尼和惯性前馈参数。
方案 B 和 Gazebo 的推力上下限都由输入 YAML 的 `thruster.T_max_forward/reverse` 决定；
方案 A 的对称限幅取正反向能力中的较小值。

## 3. 本次使用的物理参数

| 项目 | 数值 / 定义 |
|---|---|
| 总质量 | 14.2 kg，包含设备与两只旋转桨 |
| 长 / 最大宽 | 1.20 m / 0.60 m |
| 吃水 | 0.10 m |
| 干舷 | 0.30 m，按原 YAML 的 `height: freeboard above water` 注释解释 |
| 船体原点 O | 设计静水面、纵向几何中心、中心线的交点 |
| 坐标 | x 向艏，y 向左舷，z 向上；正艏摇为俯视逆时针 |
| 总重心 | 相对 O 为 `(0.12, 0, 0)` m |
| 艏摇刚体惯量 | 关于 O 为 2.13 kg·m²；关于总质心为 `2.13 − 14.2 × 0.12² = 1.92552` |
| 双桨中心距 | 0.50 m，左右桨分别为 y=+0.25 / −0.25 m |
| 推力输入 | 每桨单位 N；`τx = TL + TR`，`τz = 0.25 × (TR − TL)` |
| 静水排水体积 | 淡水密度 1000 kg/m³ 下为 0.0142 m³，即 14.2 L |

若实船“0.30 m 高”指的是船体总高而不是干舷，需要将 `height` 改为相应干舷值。
目前船壳水线宽通过网格排水体积求解，约 0.3122 m；0.60 m 是甲板处最大宽度。
横摇/纵摇惯量与阻尼属于仿真假设，没有冒充辨识结果。

## 4. 水动力参数如何写入 VRX

当前组合为 **VRX Surface 浮力 + Gazebo Hydrodynamics 阻尼 + DART 原生附加质量**。
官方建议 DART 使用 SDF `inertial/fluid_added_mass`，避免插件显式附加质量与原生附加质量
重复计算。参见 [Gazebo Harmonic Hydrodynamics 文档](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1Hydrodynamics.html)。

### 附加质量

辨识 YAML 使用 Fossen 负导数，SDF 原生附加质量使用正的物理质量：

| 辨识 YAML | 原值 | SDF `inertial/fluid_added_mass` | 有效值 |
|---|---:|---|---:|
| `Xu_dot` | −2.0 | `xx` | 2.0 kg |
| `Yv_dot` | −8.0 | `yy` | 8.0 kg |
| `Nr_dot` | −3.41 | `rr` | 3.41 kg·m² |
| `Yr_dot`, `Nv_dot` | 0, −0.363545 | 对称项 `yr` | 0.1817725 kg·m |

最后一行不能原样复制：原始辨识的交叉项不对称，SDF 原生矩阵只保存对称的 21 个元素。
默认 `added_mass_cross_policy: symmetric_mean` 取两项平均值，生成的 MPC 参数也同步为：

```yaml
Yr_dot: -0.1817725
Nv_dot: -0.1817725
```

这是**明确的仿真近似**，不是重新辨识。设置 `added_mass_cross_policy: strict` 时，
遇到当前这组不对称参数会报错，要求先提供一致的参数。
原生矩阵的参考点是 link 原点，详见 [SDFormat inertial 规范](https://sdformat.org/spec?ver=1.11&elem=link#inertial_fluid_added_mass)。

对应的有效水平面惯性矩阵为：

```text
M = [16.2    0          0         ]
    [ 0     22.2        1.8857725 ]
    [ 0      1.8857725  5.54      ]
```

原报告中的有效艏摇惯量为 5.537；当前 YAML 保留两位小数后计算为 **5.54**，未擅自改回 5.537。
不要把有效质量 16.2 再填入刚体 `mass`，那会重复计入纵向附加质量。

### 线性与二次阻尼

新模型使用 `gz::sim::systems::Hydrodynamics`，保持辨识文件的负号；二次阻尼使用 `abs` 标签：

| 方向 | 线性标签 / 值 | 二次标签 / 值 |
|---|---|---|
| 纵向 | `xU = -2.272063` | `xUabsU = -11.571784` |
| 横漂 | `yV = -2.629019` | `yVabsV = -0.05` |
| 艏摇 | `nR = -3.105` | `nRabsR = -0.71` |

交叉阻尼也映射：`Yr → yR`、`Nv → nV`、`Yrr → yRabsR`、`Nvv → nVabsV`，目前均为零。
例如纵向流体力为 `Fx = -2.272063 u - 11.571784 |u|u`。

插件同时设置 `disable_added_mass=true`、`disable_coriolis=true`，关闭插件自身的旧实现；
DART 仍然计算原生附加质量及其科里奥利项。

**不要混用旧插件规则**：VRX 的 `libSimpleHydrodynamics.so` 接收正阻尼，二次标签为 `xUU/yVV/nRR`。
这与当前原生 Gazebo 插件的负号及 `xUabsU/yVabsV/nRabsR` 不同。
旧插件用法可对照 [VRX 官方水动力教程](https://github.com/osrf/vrx/wiki/hydrodynamic_params_tutorial)。

### 浮力、吃水与姿态

Surface 使用等效圆柱截面的分布浮力，**不会自动从显示网格计算水动力**。
四个采样点为 x=`0.12 ± 0.324`、y=`±0.18`、z=`−0.10` m，使静水平衡浮心与重心对齐，
并提供横摇和纵摇恢复力。

半径 0.15 m；等效 `hull_length≈0.68847 m` 根据
`ρ × hull_length × CircleSegment(radius, draft) = mass` 求出。
该长度是浮力等效系数，不能误改成外观船长 1.2 m，否则吃水会变化。
这里选择等效分布恢复力；并未求解真实船壳完整的静水力曲线或 CFD。

本次还修正了本地 `vrx_ws/src/vrx_gz/src/Surface.cc` 的采样点力矩参考点：新模型启用
`points_in_link_frame=true`，用关于 link 原点的力矩施力，避免重心偏移被重复相加。
旧模型不设置此参数时沿用原行为。**因此需要加载本项目编译的 Surface 插件。**

初始波场显式设置 `gain=0` 和 `amplitude=0`。
`usv_calm` 世界无风无浪；`sydney_regatta` 会通过 `/vrx/wavefield/parameters` 发布其海况。
先用静水匹配辨识响应，再加入海况。不要另加第二套 Buoyancy 或 SimpleHydrodynamics。

## 5. 构建与启动

当前机器上两个 Python 包和修正后的 Surface 已编译；新终端加载后即可启动。
从源代码重新构建时：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/trevor/USV/vrx_ws
colcon build --packages-select vrx_gz --symlink-install \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash

cd /home/trevor/USV/usv_mpc_ws
colcon build --packages-select usv_simulation usv_bringup --symlink-install
source install/setup.bash

# 先观察新船，不启动控制器
ros2 launch usv_bringup vrx.launch.py world:=usv_calm control_enabled:=false

# 静水方案 B；保持原有话题
ros2 launch usv_bringup vrx.launch.py world:=usv_calm scheme:=B

# VRX 悉尼场景
ros2 launch usv_bringup vrx.launch.py world:=sydney_regatta scheme:=B
```

GUI 中选择 `wamv` 聚焦船体。`headless:=True` 可关闭 GUI。
测试艇只有 1.2 m，不再使用 WAM-V 的大尺度船体。
`model.urdf` 仅供 TF/RViz，真正物理配置在 `model.sdf`，不要将 URDF 重新转回 SDF 启动。

单独导出可检查的模型：

```bash
ros2 run usv_simulation build_vrx_model \
  --vehicle /home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/usv_params_sim.yaml \
  --simulation /home/trevor/USV/usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml \
  --output /home/trevor/USV/usv_mpc_ws/artifacts/vrx_model
gz sdf -k /home/trevor/USV/usv_mpc_ws/artifacts/vrx_model/model.sdf
```

生成的网格 URI 指向本机绝对路径，换目录/换机器应重新生成。
新外观只使用本地生成资源，不依赖在线下载船体模型。

## 6. 已验证的范围

2026-09-14 在本机 ROS 2 Jazzy / Gazebo Harmonic 上检查：

| 检查 | 结果 |
|---|---|
| SDF 语法 | `gz sdf -k` 通过 |
| Python 回归 | 总质量、重心、总惯量、浮力、网格封闭性、符号、参数不覆盖等通过 |
| 纵向有效质量 | 1 N 外力测得 16.2000 kg |
| 艏摇有效加速度 | 1 N·m 测得 0.185880 rad/s²，与含横漂耦合的矩阵求解一致 |
| 静水漂浮 | 10 s 无推力，水线和姿态稳定 |
| 10 N 总推力 | 稳态 0.836605 m/s，阻力方程预测相同 |
| 倒车 / 停推 / 正向转艏 | 倒车方向正确，停推后速度衰减，正力矩正艏摇 |
| 完整 ROS→GZ→ROS 链路 | 收到 IMU / 里程计；左右各 5 N 时约 0.836585 m/s |
| 实际差动命令 | 左 −3 N、右 +3 N，测得正艏摇约 0.42287 rad/s |
| Scheme B 闭环 | ACADOS 在干净终端环境启动并切到 ACTIVE；12 s 内沿直线行驶至约 14.2 m |
| 碰撞几何 | 6 段 DART 支持的盒体近似；外观仍使用封闭三角网格 |

数值物理检查脚本 `src/usv_simulation/scripts/check_vrx_physics.py` 直接施加外力，不经过推进器；
`check_vrx_transport.py` 则验证实际推进器话题和桥接，结束后关闭自己启动的仿真。

本机系统 Gazebo Python 绑定为 8.15，而 ROS vendor 为 8.11；不要混用库路径。
独立数值检查示例（默认参数专用回归基准）：

```bash
cd /home/trevor/USV/usv_mpc_ws
env -u LD_LIBRARY_PATH -u PYTHONPATH \
  GZ_PARTITION=usv_model_check GZ_IP=127.0.0.1 \
  GZ_SIM_SYSTEM_PLUGIN_PATH=/home/trevor/USV/vrx_ws/install/vrx_gz/lib \
  /usr/bin/python3 src/usv_simulation/scripts/check_vrx_physics.py \
  --model artifacts/vrx_model/model.sdf \
  --world src/usv_simulation/worlds/usv_calm.sdf --case surge
```

可选 case：`float`、`mass`、`yaw_mass`、`surge`、`yaw`、`reverse`、`coupled`。
使用非零 `yr` 时，本机 DART 会输出空间惯量非刚体形式的警告；上述有效惯性测试已验证这组
广义附加质量的水平面响应。更换物理引擎或版本后应重新验证，不以“XML 能解析”代替物理检查。

## 7. 还不能视为实船已验证的内容

这次没有找到新的原始辨识产出文件，采用的是仓库已经记录的 7 月纵向先验与 9 月艏摇参数。
参数指南记载 9 月 8 日换过推进器，因此 **±25 N、正反对称和推力/RPM 标度仍是旧假设**，
不是新推进器的拉力标定。VRX 当前输入为 N，`thrust_coefficient` 只用于该模式下的桨转速显示。

横摇、纵摇、升沉、风载、波浪响应没有实船辨识支撑；当前不包含真实电机滞后、PWM 死区、
左右不对称、出水衰减、通气/空化。外观网格改变不会自动更新这些物理量。
目前完成的是按现有辨识参数搭建并验证仿真基线，闭环调参结果仍需实船复核。
