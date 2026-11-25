# USV MPC 算法分析与优化建议

> 评审日期：2026-09-12  
> 评审范围：`usv_mpc_kinematic_cpp`（方案 A）、`usv_mpc_cpp`（方案 B）、参考轨迹生成、VRX 执行内环及相关参数  
> 工作区：ROS 2 Jazzy / `ament_cmake` + `ament_python`

## 1. 文档目的

本文记录当前 USV MPC 控制系统的算法结构、已验证问题、优化建议、实施顺序和验收方法。文档只记录分析结论，不直接修改控制器实现或参数。

当前系统包含两套控制方案：

| 项目 | 方案 A：运动学 MPC | 方案 B：动力学 NMPC |
|---|---|---|
| 包 | `usv_mpc_kinematic_cpp` | `usv_mpc_cpp` |
| 状态 | `[x, y, psi, u, r]` | `[x, y, psi, u, v, r]`，acados 内部增广上一拍双桨推力 |
| 优化变量 | `[u_cmd, r_cmd]` | `[T_L, T_R]` |
| 预测模型 | 平面运动学 + 速度/角速度一阶滞后 | Fossen 三自由度动力学 |
| 数值积分 | RK4，每个离散周期 4 个子步 | RK4，每个离散周期 4 个子步 |
| 求解器 | CasADi Opti + IPOPT | acados SQP_RTI，CasADi + IPOPT 备用 |
| 执行输出 | `TwistStamped`，再由飞控或 VRX 内环执行 | VRX 直接推力，实机经 RC override 映射 |
| 默认时域 | `dt=0.2 s, N=20`，共 4 s | `dt=0.2 s, N=20`，共 4 s |

当前实现已经具备以下良好基础：

- 状态与求解结果的 NaN/Inf 门禁；
- 航向参考连续展开，避免 `+-pi` 处出现虚假跳变；
- 原始控制边界与控制变化率硬约束；
- 原始解的移位热启动；
- 求解失败计数、HOLD 和安全输出；
- 路径与速度剖面的时间戳同步检查；
- acados 生成代码的 `N`、`dt` 与运行配置一致性校验。

## 2. 总体结论

当前最主要的限制并非单纯的 `Q/R` 权重选择，而是控制链路中仍存在三个基础一致性问题：

1. 方案 A 的 VRX 内环对已经处于船体系的速度又做了一次坐标旋转；
2. 方案 A 会把只满足“数值有限”的 IPOPT 未收敛迭代点当作成功解；
3. 方案 B 的 acados 与 CasADi 后端对阶段代价使用了不同缩放，同一套权重并不代表同一个优化问题。

这些问题应在进一步调权前解决，否则调参结果会吸收坐标系错误、约束违反或求解器差异，难以迁移到实船。

建议按以下顺序实施：

| 优先级 | 修改项 | 预期收益 | 风险/工作量 |
|---|---|---|---|
| P0 | 修复方案 A VRX 速度坐标系 | 消除转弯时速度反馈失真 | 低 |
| P0 | 对 IPOPT 早停解做约束可行性门禁 | 防止发布违反硬约束的控制 | 中 |
| P1 | 统一方案 B 两个后端的代价缩放 | 保证后端切换和调参含义一致 | 中 |
| P1 | 将方案 B 航向代价改为非线性最小二乘 | 改善大航向误差下的 Hessian 性质 | 中，需要重新生成 acados 代码 |
| P1 | 使预测模型与实际执行器链路一致 | 提升仿真到实船迁移质量 | 中到高，需要辨识 |
| P2 | 为方案 A 增加速度/角速度跟踪与控制增量代价 | 降低振荡，利用现有 TOPP 剖面 | 中 |
| P2 | 使用连续弧长进度构造参考 | 减少参考跳点和点密度依赖 | 中 |
| P2 | 优化方案 A 求解性能并补偿延迟 | 降低闭环延迟和 deadline miss | 中到高 |

## 3. P0：修复方案 A VRX 内环速度坐标系

> 实施状态：已于 2026-09-12 完成。`cmdvel_to_thrust` 现在直接读取船体系
> `twist.linear.x`，并增加 90 度航向回归测试和话题坐标系契约说明。

### 3.1 当前行为

`usv_simulation/usv_simulation/cmdvel_to_thrust.py` 在里程计回调中把 `twist.linear.x/y` 当作世界系速度，再根据当前航向旋转到船体系：

```text
u_meas = vx * cos(psi) + vy * sin(psi)
```

随后该速度进入纵向速度内环：

```text
F = drag(u_cmd) + kp_u * (u_cmd - u_meas)
```

### 3.2 证据

使用两份现有 VRX bag，以相邻位置差分作为世界系速度真值，分别检验两种 twist 语义：

| Bag | 直接把 twist 当世界系的 RMSE | 先按船体系旋到世界系的 RMSE |
|---|---:|---:|
| `vrx_scheme_A_006_5state` | 约 1.67 m/s | 约 0.025 m/s |
| `vrx_twin_circle_007_fixed` | 约 0.88 m/s | 约 0.012 m/s |

结果表明这些 bag 中 `Odometry.twist` 已经是 `child_frame_id` 对应的船体系速度。当前内环再次旋转，等于重复变换。

### 3.3 影响

- 船头接近东西/南北方向时，反馈误差的幅值随航向改变；
- 转弯和绕圈时纵向反馈出现周期性失真；
- `kp_u` 调参会补偿错误的速度定义，参数难以迁移；
- 同一个里程计在 MPC 节点与执行内环中得到不同物理解释。

### 3.4 建议修改

对当前 VRX odometry，直接采用：

```text
u_meas = twist.linear.x
r_meas = twist.angular.z
```

同时把速度坐标系约定写入 `topic_contract.yaml` 或相关接口文档：

- `pose` 位于 `header.frame_id`；
- `twist` 位于 `child_frame_id`；
- MPC 内部的 `u/v/r` 均采用船体系；
- 若将来接入确实输出世界系 twist 的来源，应在独立适配节点中转换，并通过参数或消息来源显式区分。

### 3.5 验收标准

- 使用位置差分校验，船体系 twist 旋到世界系后的速度 RMSE 小于 0.05 m/s；
- 圆周路径中 `u_meas` 不再以航向角为周期产生明显起伏；
- 同一路径与速度下，CTE、推力饱和率不劣于修改前；
- 添加坐标轴旋转的单元测试，至少覆盖 `psi=0`、`pi/2` 和 `-pi/2`。

## 4. P0：为方案 A IPOPT 早停解增加可行性门禁

> 实施状态：已于 2026-09-12 完成。正常收敛解与早停候选解统一检查
> 初始状态、离散动力学、控制边界和控制变化率残差；不可行早停解进入
> 原有安全回退，相关最大残差通过 `/mpc/status` 发布。

### 4.1 当前行为

`casadi_kinematic_backend.cpp` 在 IPOPT 抛出 `Solver failed` 后，通过 `opti.debug()`回收最后一个迭代点。当前接收条件只检查：

- 第一拍控制、预测状态和预测控制是否为有限值；
- 未检查动力学等式、初始状态、控制边界和变化率约束残差。

通过有限值检查后，求解结果被设置为 `success=true`，节点会直接发布第一拍控制。

### 4.2 离线复现实验

使用 `N=20`、`dt=0.2 s`、初始纵向速度和变化率锚点均为 `1.5 m/s`，强制 `ipopt_max_iter=1`。由于 `du_max=1.3 m/s^2`，首步速度指令必须满足：

```text
u_cmd[0] in [1.5 - 1.3*0.2, 1.5 + 1.3*0.2]
         = [1.24, 1.76] m/s
```

实测早停迭代点：

| 指标 | 结果 |
|---|---:|
| 后端返回状态 | `success=true` |
| 求解备注 | `ipopt_early_stop` |
| 返回首步速度 | 约 0.045 m/s |
| 最大变化率违反 | 约 1.20 m/s |
| 最大动力学缺陷 | 约 0.33 |
| 求解耗时 | 约 69 ms，低于 200 ms deadline |

该解数值有限，但明显违反硬约束，因此不能作为可执行控制发布。

### 4.3 建议修改

建立统一的候选解检查函数，成功解和早停回收解都经过同一门禁：

1. 检查所有数值有限；
2. 检查 `X[:,0]` 与当前状态的无穷范数残差；
3. 逐步用离散模型重算 `f(X_k,U_k)`，检查与 `X_{k+1}` 的动力学缺陷；
4. 检查 `u_min/u_max`、`r_max`；
5. 检查首步相对实际下发控制的变化率，以及后续相邻控制变化率；
6. 可选读取 IPOPT 的 `return_status`、原始 primal infeasibility 和 dual infeasibility；
7. 只有全部残差小于明确容差时，才允许作为降级可行解发布。

建议将状态分类为：

| 类别 | 含义 | 节点行为 |
|---|---|---|
| `converged` | 正常收敛且通过可行性检查 | 发布新控制 |
| `early_stop_feasible` | 未完全收敛，但约束可行 | 发布并记录降级状态 |
| `early_stop_infeasible` | 数值有限但违反约束 | 不发布候选控制，进入安全回退 |
| `invalid` | NaN/Inf 或无法取得解 | 安全回退 |

安全回退应使用经过边界和变化率投影的控制。可以优先采用上次已验证可行的预测控制序列首项，并随连续失败逐步衰减到零。直接把任意早停 `u_0` 截断到边界不能修复其动力学轨迹和全部约束，应只作为最后一级输出保护。

### 4.4 对偶热启动修正

CasADi 官方 Opti 接口使用 `set_initial(opti.lam_g(), lam_g)` 初始化对偶变量。当前代码使用 `set_value`。虽然当前 CasADi 版本接受该调用，建议改为文档规定的 `set_initial`，减少版本行为差异。

参考：[CasADi Opti 文档](https://web.casadi.org/docs/#optiproblem-structure)。

### 4.5 测试要求

现有 `EarlyStopHarvestAndDualWarmStart` 只断言 `success` 和有限值，应增加：

- 强制早停时的初始状态残差；
- 动力学缺陷上限；
- 控制上下界违反量；
- 第一拍及全时域变化率违反量；
- 不可行候选解必须返回失败；
- 可行但未收敛候选解允许降级执行；
- 多拍连续失败时回退控制单调趋向安全输出。

## 5. P1：统一方案 B 的 acados 与 CasADi 代价定义

> 实施状态：已于 2026-09-12 完成。CasADi 现将完整阶段代价乘以
> `dynamic.dt`，终端代价保持单位缩放，与 acados 生成代码一致。配置和
> `MpcParams` 已明确权重语义，并增加两个真实后端的首拍控制一致性回归。

### 5.1 当前差异

acados 生成代码对每个阶段的 running cost 使用 `dt=0.2` 缩放，终端代价缩放为 1：

```text
J_acados = 0.2 * sum(l_k) + V_f
```

CasADi 后端直接累加：

```text
J_casadi = sum(l_k) + V_f
```

因此使用相同的 `Q/R/Rd/Qf_scale` 时，acados 中终端代价相对 running cost 的影响是 CasADi 后端的 5 倍。回退后端并未求解同一个 OCP。

### 5.2 建议的统一定义

建议采用连续时间代价的离散近似：

```text
J = sum(dt * l(x_k, u_k, delta_u_k)) + V_f(x_N)
```

并在两个后端中保持一致。随后重新解释和整定 `Qf_scale`。

对于变化率项还需明确物理含义：

- 若惩罚每步推力变化 `delta_T`，当前 `Rd * delta_T^2` 可保持；
- 若惩罚推力变化率 `dT/dt`，应使用 `Rd_rate * (delta_T/dt)^2 * dt`；
- 在 `dt` 可变或采用非均匀时域时，优先使用后一种定义，以保持权重物理意义稳定。

### 5.3 后端等价性测试

构造相同初始状态、参考、参数和控制锚点，比较：

- 第一拍控制差；
- 全时域目标函数值；
- 控制边界及变化率违反量；
- 预测终端状态；
- 直线、定常圆周、`+-pi` 航向跨界三类工况。

由于 SQP_RTI 与 IPOPT 的迭代策略不同，不要求轨迹逐元素完全相同，但应确保目标函数定义完全一致，第一拍控制差在工程容差内。

### 5.4 实施与验证结果

CasADi 目标函数现在按以下结构构建：

```text
stage_cost = state_cost + heading_cost + control_cost + increment_cost
J += dt * stage_cost
J += terminal_cost
```

`Rd` 当前明确为固定 `dt` 下的逐步推力增量 `delta_T` 平滑权重。此次修改只
统一两个后端的既有含义，没有改动数值权重；若未来允许改变 `dt`，仍应按
5.2 节建议进一步改成具有明确量纲的推力变化率代价并重新整定。

新增 `BackendConsistency.TerminalStepFirstControlAgrees` 回归：运行阶段参考保持
原点，只在终端设置 `x=0.5 m`，以放大运行/终端代价比例错误。实测结果：

| 版本 | acados 首拍单桨推力 | CasADi 首拍单桨推力 | 绝对差 |
|---|---:|---:|---:|
| 统一后 | 0.0580 N | 0.0722 N | 0.0142 N |
| 故障注入：CasADi 漏乘 `dt` | 0.0580 N | 0.0141 N | 0.0440 N |

测试容差设为 `0.03 N`。故障注入版本按预期失败，恢复统一缩放后通过，因此该
回归能够捕获本次错误。剩余差异来自 acados 的单次 SQP_RTI 与 IPOPT 完整收敛
策略不同，不代表目标函数缩放仍有差异。

## 6. P1：改善方案 B 航向代价的 Hessian 性质

> 实施状态：已于 2026-09-12 完成。acados 阶段与终端代价已改为
> `NONLINEAR_LS`，航向使用单位圆上的正弦、余弦残差，并重新生成 vendored
> 求解器。CasADi 使用代数等价的单位圆表达式，保持两个后端目标值一致。

### 6.1 当前航向代价

当前周期航向代价为：

```text
L_psi = 2 * Q_psi * (1 - cos(psi - psi_ref))
```

该表达式能正确处理 `+-pi` 周期，但二阶导数为：

```text
d2L_psi/de_psi2 = 2 * Q_psi * cos(e_psi)
```

当航向误差绝对值超过 90 度时，代价局部曲率为负。修改前的 codegen 使用 `EXTERNAL` cost，且没有显式自定义 Gauss-Newton Hessian或正则化。acados 对 EXTERNAL cost 在未给出自定义 Hessian 时会使用精确代价 Hessian；全局 `hessian_approx=GAUSS_NEWTON` 并不会自动把任意 EXTERNAL 表达式变成最小二乘 Gauss-Newton Hessian。

参考：[acados Hessian computation and regularization](https://docs.acados.org/developer_guide/index.html#hessian-computation-and-regularization)。

### 6.2 推荐形式

将航向误差写成单位圆上的两个残差：

```text
r_sin = sin(psi) - sin(psi_ref)
r_cos = cos(psi) - cos(psi_ref)
```

二者平方和满足：

```text
r_sin^2 + r_cos^2 = 2 * (1 - cos(psi - psi_ref))
```

因此可用 `NONLINEAR_LS` 表达与当前等价的周期代价，并获得半正定的 Gauss-Newton 代价 Hessian。实现时要检查 acados 的 `0.5 * residual^T W residual` 约定，正确设置权重，避免无意改变 `Q_psi` 的实际倍率。

### 6.3 备选方案

若暂时保留 EXTERNAL cost，则至少应：

- 配置合适的 Hessian 正则化或 Levenberg-Marquardt 项；
- 用 90、135、180 度初始航向误差测试 QP 状态；
- 记录 QP status、KKT 残差和约束违反；
- 比较 `SQP_RTI` 与完整 `SQP` 的离线收敛情况。

### 6.4 实施与验证结果

acados 的阶段残差现在为 11 维：

```text
y = [sqrt(2*Q_i) * e_i,                         i in {x,y,u,v,r},
     sqrt(2*Q_psi) * (sin(psi)-sin(psi_ref)),
     sqrt(2*Q_psi) * (cos(psi)-cos(psi_ref)),
     sqrt(2*R_i) * T_i,
     sqrt(2*Rd_i) * delta_T_i]
```

终端残差为 7 维，只保留 5 个线性状态残差和 2 个单位圆航向残差。使用
`W=I` 后，acados 的 `0.5*y^T*W*y` 恰好恢复原代价倍率。例如航向部分为：

```text
0.5 * 2*Q_psi * (r_sin^2 + r_cos^2)
= 2*Q_psi * (1-cos(delta_psi))
```

生成代码契约由编译期断言固定为 `NY0=11`、`NY=11`、`NYN=7`。生成器还会
依据 `usv_dyn_ocp.json` 清除旧 OCP 遗留的 C 文件，避免 `CMake GLOB` 编入
过期的 EXTERNAL 代价或连续模型源码。

验证覆盖：

- 重新生成后的 JSON 和 C 求解器均声明 `NONLINEAR_LS + GAUSS_NEWTON`；
- 原有名义、滚动热启动、运行时推力边界、变化率和航向跨界测试通过；
- 新增 90 度、135 度和接近 180 度的航向误差求解测试；
- 新增航向权重双后端回归，acados/CasADi 首拍左右推力差分别约为
  `0.0083 N` 和 `0.0098 N`，均小于 `0.02 N` 容差。
- 两个后端均在构造阶段拒绝 NaN、Inf 或负的 `Q/R/Rd/Qf_scale`，避免
  非法权重进入平方根预计算和求解器。

精确 180 度误差仍是周期航向代价的驻点，代价梯度为零。Gauss-Newton 修正
解决的是 Hessian 不定问题，并不会消除这一拓扑性质；闭环中通常由测量噪声、
参考渐变或上一拍热启动打破该对称点。

## 7. P1：使 MPC 模型与真实执行链路一致

> 实施状态：软件侧输入锚点已于 2026-09-12 完成。方案 B 会把 RC/PWM
> 映射后的等效推力或 VRX 最终发布推力写回两个求解后端，作为下一拍
> `delta_T` 的起点。方案 A 闭环响应辨识、实船 PWM 静态推力标定、死区、
> 电压影响和通信延迟仍需要试验数据，因此本节尚未全部完成。

### 7.1 方案 A 的闭环滞后

方案 A 使用一阶执行器模型：

```text
du/dt = (u_cmd - u) / tau_u
dr/dt = (r_cmd - r) / tau_r
```

当前 `tau_u=0.8 s`、`tau_r=1.78 s`。但 VRX 的 `cmdvel_to_thrust` 内环还包含阻力前馈和比例反馈，MPC 看到的是闭环执行器响应，不能只用船体开环惯性/阻尼估计。

忽略耦合和饱和，在零角速度附近，使用当前 VRX 参数可粗略得到：

```text
tau_r_closed ~= Iz_eff / (|Nr| + kp_r)
             ~= 5.537 / (3.105 + 4.0)
             ~= 0.78 s
```

该值与配置的 `1.78 s` 有明显差异。这个计算只用于说明需要闭环辨识，不能代替试验结果。

建议分别在 VRX 和实船上记录阶跃或 PRBS 响应，辨识：

- `u_cmd -> u_meas` 的增益、时间常数和纯延迟；
- `r_cmd -> r_meas` 的增益、时间常数和纯延迟；
- 不同速度、不同转向幅度下参数是否变化；
- 推力饱和、死区和正反向不对称。

### 7.2 方案 B 的 RC 映射

方案 B 优化的是物理推力，但实机输出还经过：

```text
[T_L, T_R]
  -> 合成 throttle/steering
  -> throttle_gain / steering_gain
  -> PWM
  -> ArduRover 混控与推进器
  -> 实际推力
```

当前 `throttle_gain=0.75`、`steering_gain=0.4` 意味着求解器中的推力并不一定等于植物实际收到的等效推力。建议标定 PWM 与静态推力/转艏力矩映射，并纳入：

- 中位死区；
- 正反推不对称；
- 左右推进器差异；
- PWM 到推力的非线性；
- 电池电压对推力的影响；
- 执行器一阶滞后和控制通信延迟。

若暂时保留当前 RC 抽象，至少应把“实际下发 PWM 对应的等效推力”写回求解器，作为下一拍 `delta_T` 的锚点，避免优化器锚点和实际执行输入漂移。

### 7.3 已完成的软件侧推力回写

节点现在先将求解器首拍推力映射为整数 PWM，再用同一组
`pwm_min/center/max`、`steering_sign`、`throttle_sign`、
`steering_gain` 和 `throttle_gain` 反算模型坐标下的等效输入。在线性混控
近似下：

```text
T_surge,eq = inverse_pwm(throttle_pwm) * throttle_sign * T_direction
T_yaw,eq   = inverse_pwm(steering_pwm) * steering_sign * max(T_max, |T_min|)
T_L,eq     = clamp(T_surge,eq - T_yaw,eq, T_min, T_max)
T_R,eq     = clamp(T_surge,eq + T_yaw,eq, T_min, T_max)
```

该过程保留了增益衰减、方向符号、整数 PWM 量化和单桨推力边界。例如当前
实机配置下：

```text
计划 [20, 20] N  -> 等效下发 [15, 15] N
计划 [-20, 20] N -> 等效下发 [-8, 8] N
```

`DynamicMpc::set_applied_control()` 将这个等效输入覆盖到 acados 增广状态的
`u_prev` 和 CasADi 的 `p_u_prev`。因此下一拍的首项变化率代价和
`|T_0-u_prev| <= dT_max*dt` 硬约束都从执行层输入出发。acados 同时修正移位
热启动首列中的增广控制状态，减少初值与初始状态硬约束的偏差。

VRX 路径不经过 RC 反算；节点把经过 `vrx_thrust_scale`、命令限幅和
`dynamic.T_min/T_max` 限幅后的最终发布牛顿值直接写回。状态消息中：

- `tl_cmd_n/tr_cmd_n` 表示求解器计划首拍；
- `tl_n/tr_n` 表示写回求解器的等效已下发推力；
- `actuation_mapping_error_n` 表示两者最大的绝对差；
- `actuation_anchor_source` 区分 `rc_linearized` 与 `vrx_published`。

回归测试覆盖 RC 直航/差动映射、acados 回写后的首拍变化率约束，以及
acados/CasADi 对同一回写值的约束一致性。

这里的 `rc_linearized` 仍是命令侧估计，不是测力计真值。它消除了代码中已知
的锚点漂移，但不能代替 PWM 到静态推力、ArduRover 混控、推进器滞后、死区和
电池电压的实船辨识。获得标定曲线后，应直接替换反算函数并保留相同的求解器
回写接口。

## 8. P2：完善方案 A 的代价函数

方案 A 已从 3 状态升级为 5 状态，但代价仍只跟踪位置和航向，并惩罚控制绝对值：

```text
L = position_error + heading_error + U^T R U
```

速度剖面已经包含 `v_ref` 和 `r_ref`，但构造方案 A 参考时未传入优化器。建议改为：

```text
L = q_xy * position_error
  + q_psi * heading_error
  + q_u * (u - u_ref)^2
  + q_r * (r - r_ref)^2
  + U^T R U
  + delta_U^T Rd delta_U
```

终端代价也应包含速度和角速度误差，特别是在终点要求停车时，避免位置已经接近终点但仍保留较大动量。

### 8.1 权重初始化方法

建议用允许误差归一化，而不是直接凭量级试调：

```text
q_i = alpha_i / e_i,max^2
r_j = beta_j / u_j,max^2
rd_j = gamma_j / delta_u_j,max^2
```

例如先定义可接受的横向误差、航向误差、速度误差和角速度误差，再生成同量纲的初始权重。随后用 bag 的闭环指标优化，而不是只观察单次轨迹图。

### 8.2 注意事项

- `R` 与 `Rd` 不应同时过大，否则控制器会严重滞后；
- `r_ref` 应来自曲率与速度 `r_ref=kappa*v_ref`；
- 接近终点时 `u_ref` 必须下降到零；
- 若保留硬变化率约束，`Rd` 用于改善平滑性，而不是代替约束；
- 增加速度参考后应重新评估 `reference_start_offset`，避免位置参考过度前置。

## 9. P2：用连续路径进度替代最近点加固定索引偏移

### 9.1 当前方法的问题

当前每个控制周期遍历整条路径寻找欧氏最近点，然后执行：

```text
idx = nearest + reference_start_offset
```

方案 B 默认 `reference_start_offset=8`，路径默认分辨率为 `0.5 m`，相当于把参考起点粗略前移约 4 m。该距离会随路径重采样密度改变。

潜在问题包括：

- 自交路径或相邻航段靠近时可能跳到错误航段；
- 最近点索引可在噪声下前后跳动；
- 固定点数没有稳定的物理单位；
- 转弯、低速和高速使用相同前视点数；
- 每拍全局搜索为 `O(M)`，长路径不必要地增加计算量。

### 9.2 建议方法

维护单调或有限回退的连续弧长进度 `s_progress`：

1. 在上次投影点附近的局部窗口搜索；
2. 将当前位置投影到路径线段，得到连续弧长 `s`；
3. 限制每拍允许回退的弧长，避免噪声导致进度倒跳；
4. 用米或秒定义前视：`s_ref = s_progress + lookahead_m`；
5. 根据速度和曲率自适应前视距离；
6. 以 `s/t` 连续插值位置、航向、速度和角速度参考。

进一步可以把位置误差分解为 Frenet 坐标：

- 横向误差 `e_y`：较高权重，决定贴合路径；
- 沿程误差 `e_s`：较低权重，允许受扰后在时间参考上稍微落后；
- 航向误差 `e_psi`：周期代价。

这比对全局 `x/y` 使用相同固定权重更适合路径跟踪。

### 9.3 降级参考修正

方案 B 在速度剖面不同步时使用匀速弧长采样。当前降级路径存在两点：

- 到达路径终点后仍设置 `u_ref=cruise_speed`；
- 弯道统一设置 `r_ref=0`。

建议降级参考也根据剩余制动距离生成终点减速，并用路径曲率计算 `r_ref=kappa*u_ref`。否则剖面短暂不同步会显著改变 NMPC 目标。

## 10. P2：方案 A 求解性能和控制延迟

现有日志显示：

| Bag | 平均求解时间 | P95 | P99 | 最大值 |
|---|---:|---:|---:|---:|
| `vrx_scheme_A_006_5state` | 约 85.1 ms | 约 114.7 ms | 约 153.2 ms | 约 762.8 ms |
| `vrx_twin_circle_007_fixed`（方案 B） | 约 0.4 ms | 约 0.49 ms | 约 0.60 ms | 约 0.84 ms |

方案 A 以 5 Hz 控制，P99 已占一个 200 ms 周期的大部分。最大值超过 deadline，且当前 `solve_time_ms` 只测求解调用，没有覆盖构造参考、消息发布和调度抖动。

建议依次实施：

1. 节点启动时做一次不下发的预热求解，避免首拍 JIT/初始化峰值；
2. 记录从状态快照到指令发布的完整控制周期延迟；
3. 把当前状态预测到预计控制生效时刻，再作为 MPC 初值；
4. 确认原始、对偶热启动均正确生效；
5. 评估 CasADi `Opti.to_function`，减少反复 `set_initial/solve/value` 的调用开销；
6. 如仍不能稳定满足控制预算，再为方案 A 生成 acados 求解器；
7. 统计 deadline miss 比例，而不只统计平均时间。

方案 B 的 acados 求解时间已明显小于控制周期，近期优化重点应放在模型、执行器和参考一致性。CasADi 备用后端还有一个容易修正的问题：当前缓存并移位了 `U_warm_`，下一拍却仍用全零控制序列初始化。应将移位后的 `U_warm_` 实际传给 `U_`。

## 11. 推荐实施阶段

### 阶段 1：消除基础错误

- 修复 VRX twist 重复旋转；
- 给 A 的早停候选解增加全约束门禁；
- 改正 IPOPT 对偶变量初始化方式；
- 补充坐标系和早停可行性测试；
- 在状态消息中发布最大动力学残差、最大边界违反和最大变化率违反。

完成标准：任何被标为成功的控制序列都满足设定的可行性容差；圆周工况中速度反馈不随航向产生坐标系伪振荡。

### 阶段 2：统一优化问题

- 统一 B 的 acados/CasADi 代价缩放；（已完成，2026-09-12）
- 统一 `Rd` 的物理定义；
- 将周期航向误差改为非线性最小二乘；（已完成，2026-09-12）
- 重新生成 acados 代码；（已完成，2026-09-12）
- 增加后端等价性测试。（已完成缩放和航向权重工况，2026-09-12）

完成标准：两个后端对同一候选轨迹计算的目标函数一致，关键工况的第一拍控制无异常突变。

### 阶段 3：提升跟踪性能

- A 增加 `u/r` 状态跟踪与 `delta_U` 代价；
- 参考生成改为连续弧长进度；
- 修正终点停车和降级曲率参考；
- 用允许误差归一化初始化权重，再用批量仿真整定。

完成标准：CTE P95、航向误差 P95 和终点剩余速度同时改善，控制变化率及饱和率不恶化。

### 阶段 4：实船模型闭环

- 将执行层最终等效推力写回方案 B 的 `delta_T` 锚点；（软件侧已完成，
  2026-09-12；实船标定模型待补充）
- 标定 PWM 到左右推进器实际推力；
- 辨识 A 方案闭环执行器模型；
- 加入延迟补偿；
- 对风浪和参数偏差做 Monte Carlo/批量回放；
- 在低速安全工况完成实船 A/B 对比。

完成标准：仿真与实船在稳态速度、转弯半径、角速度响应和控制饱和方面的差异处于预定范围。

## 12. 验证指标与数据记录

现有 `scripts/analyze_usv_bag.py` 主要统计平均 CTE、最大 CTE、平均求解时间和推力饱和率。建议扩展为以下指标：

### 12.1 跟踪指标

- CTE：均值、RMSE、P95、最大值；
- 航向误差：RMSE、P95、最大值；
- 速度误差和角速度误差：RMSE、P95；
- 终点位置误差和终点剩余速度；
- 路径进度是否发生异常倒跳或跨段跳变。

### 12.2 控制指标

- 左右推力或 `u/r` 指令的峰值、RMS；
- 饱和占比；
- 控制变化率峰值、P95；
- 单位航程能耗代理量 `sum((T_L^2+T_R^2)*dt)`；
- 左右差动推力的峰值和频谱，识别高频振荡。

### 12.3 求解器指标

- 完整控制周期耗时 P50/P95/P99/最大值；
- 求解器状态分布；
- deadline miss 比例；
- primal/dual/KKT 残差；
- 最大初始状态、动力学、边界和变化率违反量；
- 热启动与冷启动的迭代次数和耗时对比；
- 连续失败次数以及每种安全回退的触发次数。

### 12.4 建议标准工况

每次改动至少运行：

1. 静止到直线巡航；
2. 90 度和 180 度转弯；
3. 定常圆周；
4. S 曲线；
5. `+-pi` 航向跨界；
6. 终点停车；
7. 横向初始偏差；
8. 135 度以上反向初始航向；
9. 外力扰动或侧风；
10. 短时里程计延迟、求解器早停和参考剖面不同步。

## 13. 最小构建与回归命令

仅修改方案 A 时：

```bash
cd ~/USV/usv_mpc_ws
colcon build --symlink-install --packages-select usv_mpc_kinematic_cpp usv_simulation usv_bringup
source install/setup.bash
colcon test --packages-select usv_mpc_kinematic_cpp usv_simulation usv_bringup
colcon test-result --verbose
```

修改方案 B OCP 或重新生成 acados 代码时：

```bash
cd ~/USV/usv_mpc_ws
python3 src/usv_mpc_cpp/scripts/regenerate_acados_codegen.py --horizon 20 --dt 0.2
colcon build --symlink-install --packages-select usv_mpc_cpp usv_bringup
source install/setup.bash
colcon test --packages-select usv_mpc_cpp usv_bringup
colcon test-result --verbose
```

全工作区回归：

```bash
cd ~/USV/usv_mpc_ws
colcon build --symlink-install
source install/setup.bash
colcon test
colcon test-result --verbose
```

VRX 记录和离线分析示例：

```bash
ros2 launch usv_bringup vrx.launch.py scheme:=A record_bag:=True run_id:=mpc_a_after_fix
python3 scripts/analyze_usv_bag.py ~/usv_vrx_logs/mpc_a_after_fix
```

## 14. 风险与回归检查点

- 修正速度坐标系后，原有内环增益是在错误反馈上得到的，可能需要重新整定；
- 收紧早停门禁后，求解失败次数可能上升，这是诊断变得真实的结果，应同时完善安全回退；
- 统一代价缩放后，现有 `Qf_scale` 的实际强度会改变，不能直接沿用历史结论；
- 改为 `NONLINEAR_LS` 后必须确认代价的 `1/2` 系数和权重倍率；
- 修改 acados OCP 结构必须重新生成并提交完整生成代码，运行时只改 YAML 不够；
- 路径进度单调约束不能完全禁止倒退，否则船被扰动吹过航段后可能无法合理恢复；
- 执行器模型必须分别对应 VRX 与实船，不能把仿真辨识参数直接当作实船真值；
- 所有性能比较应使用相同路径、速度剖面、初始状态、风浪条件和分析时间窗口。

## 15. 本次分析依据

代码与配置主要依据：

- `src/usv_mpc_kinematic_cpp/src/casadi_kinematic_backend.cpp`
- `src/usv_mpc_kinematic_cpp/src/mpc_node.cpp`
- `src/usv_mpc_cpp/src/acados_backend.cpp`
- `src/usv_mpc_cpp/src/casadi_backend.cpp`
- `src/usv_mpc_cpp/scripts/regenerate_acados_codegen.py`
- `src/usv_simulation/usv_simulation/cmdvel_to_thrust.py`
- `src/usv_planning_cpp/src/speed_profile.cpp`
- `src/usv_bringup/config/mpc_params_A.yaml`
- `src/usv_bringup/config/mpc_params_B.yaml`
- `src/usv_bringup/config/path_config.yaml`
- `src/usv_bringup/config/usv_params_B.yaml`

现有验证数据：

- `usv_vrx_logs/vrx_scheme_A_006_5state`
- `usv_vrx_logs/vrx_scheme_A_005_best`
- `usv_vrx_logs/vrx_twin_circle_007_fixed`

当前测试均通过：

- 方案 A：13 项核心测试通过；
- 方案 B：9 项核心逻辑测试、8 项 acados 求解测试及 4 项
  acados/CasADi 一致性测试通过。

这些测试证明当前名义工况和既有接口可以运行；方案 A 已覆盖不可行早停候选
拒绝，方案 B 已覆盖代价缩放、航向权重、大航向误差、RC 等效推力映射和
执行输入回写工况。方案 B 的定常圆周全轨迹目标值对比仍可继续扩展。
