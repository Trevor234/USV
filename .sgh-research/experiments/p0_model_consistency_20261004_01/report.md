# P0 补充实施：模型与参考一致性核验、四元数控制门禁修复

日期：2026-10-04（Asia/Shanghai）。实际执行主机：Ubuntu `192.168.1.222`，工作空间 `/home/trevor/USV`。接续首选 A 的 F2 发布端数据契约，不更改已有 v5 策略、控制权重或参考速度。

**本工作包已执行并验收。** 完成显式同参数 Python/C++/当前 native acados 生成 C 离散函数对拍、真实参考函数回归、旧 pilot 的只读分阶段诊断、odom 退化四元数控制准入修复、57 个 C++ GTest、F3 冻结及一组新的正常直行记录。P0 整阶段仍为部分完成：plant/controller 参数尚未独立，训练端历史时序、plant 接受/精确执行时序及 GP 标签合同仍未闭合。P1 尚未实现。

## 1. 本次变更与证据身份

生产控制变更仅位于 `usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp` 的 `odom_callback_`：组件有限性检查之后、yaw 转换之前，增加四元数模长平方检查。其余新增内容是测试和契约说明。没有重新生成 acados、调整 MPC 权重、改变默认水动力参数、重训 PPO 或覆盖旧基线。

新基线为 `F3_20261004_quaternion_gate_01`，目录 `/home/trevor/USV/.sgh-research/baselines/F3_20261004_quaternion_gate_01`。它包含 136 项源代码/配置、153 项安装产物、5 项模型资产；采集前后及快照重新计算哈希通过。静态 manifest 的 runtime 标记仍为 false；实际新 pilot 用独立 context 完成运行资产和有效参数核对，不能修改静态历史记录来伪造运行事实。

| 身份 | SHA256 |
|---|---|
| F1 原始三修复冻结 manifest | `fc5da9d219e1eba73326d3f1ca1ee61e101882bace9c49c587709f11dea6e23d` |
| F2 发布端契约 manifest | `6e967d07de4f4232977f7b8fca1d6f6e4582812ea0d6ac1273159566d0214b75` |
| F3 本次修复 manifest | `9c64426cc68d3eb1949fa63d564725499870bbb02d649022a2116088a0bfeb35` |
| F3 安装后的 mpc_node | `019f29593dda4baffc93b2764be990233156369a8e7f543249cfb1c375a69dc2` |
| F3 当前 mpc_node.cpp | `c3c8384ee9ccba0849448fd47bcac5f82a5413d0a10183e4e591a9627d5ded7b` |
| v3 distinct fixture | `b70827f11c404a968aec8a1996b393d5a182a7aa910a35aefeb8f3a002d58756` |

Git HEAD 仍为 `1e5becae622782526f20fc93928339133c94ec23`，工作区包含未提交改动。HEAD 本身不能代表当前安装版本，以 F3 source/install SHA 为准。F1/F2 manifest 和所有冻结快照再次逐项通过核验；五项 v5 模型资产保持原哈希。此前有可靠历史哈希的六个文件再次逐项通过，三个 F2 pilot bag 本次读取前后不变；这不扩大为全部历史 bag 均有改前证明。

## 2. 显式同参数模型对拍结果

真实 Python `usv_rl.dynamics` 与当前 C++ `USVDynamicModel` 分别计算；C++ 独立 CLI 直接编译实际 `usv_model_dynamic.cpp`。native acados 通过当前两份生成 C 编译共享库，先核验 ABI、稠密 sparsity 和 workspace，再调用 `p_global_precompute` 与 `dyn_disc_phi_fun`。没有用另写的公式替代这些实现。

使用三组完整 19 参数：运行 effective 参数、原始非对称辨识参数、非零交叉项的软件测试参数。每组 45 个 RHS、45 个单步、7 条轨迹，共 **291 次执行、291 种不同的 mode+参数+状态+控制输入**；其中 135 RHS、135 单步、21 条轨迹。18 条固定轨迹各 50 步，3 条固定种子随机轨迹各 40 步。随机种子 `20261004`，dt=0.2 s，RK4 四子步。

| 对拍路径 | 最大分量绝对数值差 | 预设纯绝对门槛 | 结果 |
|---|---:|---:|---|
| Python / C++ 连续导数 | 8.882e-16 | 1e-10 | 通过 |
| Python / C++ RK4 单步 | 2.220e-16 | 1e-09 | 通过 |
| Python / C++ 短轨迹 | 2.220e-15 | 1e-08 | 通过 |
| native acados / Python RK4 单步 | 4.899e-16 | 1e-09 | 通过 |
| native acados / Python 短轨迹 | 5.773e-15 | 1e-08 | 通过 |

表中跨不同单位分量的最大差仅用于软件对拍摘要，不是物理误差范数或模型精度保证。驱动使用 atol+rtol 判定；实际最大差也远小于单独的纯 atol，未依赖相对容差放宽。heading 单独比较圆周误差，并保留 raw 差；连续导数第三维为角速度，不作角度 wrap。acados 增广状态的两项上一控制记忆下一步精确等于当前控制，物理六维对三组不同 previous control 不变。native 函数共 1428 次调用，含 3 次全局预计算与 1425 次离散模型调用。

最初 v2 的 291 次执行中有 6 次重复轨迹，实际只有 285 种不同输入。原 v2 结果保留；独立审查发现覆盖缺口后，新建 v3，把等推力轨迹设为 `[10,10] N` 持续 50 步、正艏摇轨迹设为 `[-3,3] N` 持续 50 步，其他输入、种子、参数、驱动和门槛不变。上表只使用真实 F3 上的 v3 结果。没有把两次运行计成 582 种不同场景。

默认参数仍有明确差异：Python 的 `Nr_dot/Nr/Nrr=-3.41/-3.105/-0.71`；C++ 类默认值为 `-1.62122/-4.286144/-0.001`。当前 B 加载 YAML 中的显式运行值，不能用类默认值推断它。原辨识 `Yr_dot=0,Nv_dot=-0.363545` 与当前对称投影 `Yr_dot=Nv_dot=-0.1817725` 也必须分别标识。本次未修改默认值，避免混入训练环境变更。

验收覆盖 nominal 的 RHS/离散状态和 native memory，尚未直接执行 CasADi fallback 本体的专项对拍、Jacobian 专项核验、运行中全局参数 cache/stage 派发测试或完整 OCP 最优性证明；不能由本表自动宣称这些已经通过。

## 3. 实际参考函数与旧 pilot 诊断

profile 实际列为 **`[u_ref, kappa, r_ref, relative_profile_time]`**；第二列是曲率，不是横向 body 速度。C++ 使用第 0、2、3 列，横荡参考固定为 0。上一份 `参考剖面诊断.json` 把第二列写成 v，是命名错误；0.8 m/s 来自第一列，因此原统计数值不变。旧诊断原件不覆盖，本报告和上一报告的补充勘误提供修正解释。

新增四个测试直接调用当前节点私有 `build_reference_`，已实际编译运行：

1. 直线路径点距 0.5 m，offset=2；state.x=0/0.1/0.3 时参考位置锚点分别为 1/1/1.5 m；同步 profile 下后续点每 0.2 s 前进 0.16 m，u_ref=0.8，v_ref=0。
2. stamp 或长度失配时进入实际 fallback，速度为 0.6 m/s，每拍参考前进 0.12 m。
3. offset=0 仍通过 `max(1,offset)` 至少前进一个点，不能用 0 作为关闭前瞻的实验开关。
4. heading 跨 ±π 时，实际相位展开连续。

因此“最近点前瞻 + 每拍重新绑定 profile 时间原点”是已证实机制；其对位置/速度代价的影响仍是速度偏差的候选原因。0.8 m/s 是软代价参考，现有优化器未施加 u<=0.8 的硬约束。

以下按 bag receive 事件顺序，只统计存在有效参考路径的窗口。状态为 raw odom 快照，不冒充每次 solver 实际混合输入：

| 旧 run | 路径有效期 u 最大值 m/s | 路径有效期平面速度模长最大值 m/s | 首次清空路径时最近状态至终点距离 m | 完成日志条数 |
|---|---:|---:|---:|---:|
| p0_contract_straight_20261004_03 | 1.257541 | 1.257600 | 1.920233 | 5 |
| p0_contract_left_20261004_01 | 1.288144 | 1.334284 | 1.907887 | 6 |
| p0_contract_right_20261004_01 | 1.315051 | 1.334813 | 1.487584 | 6 |

上述数值证实纵向速度也超过软参考；单看平面速度模长不足以推出这个结论。三个旧 pilot 的 planner 均记录“所有航点任务已完成”。真实源码按航点到达半径推进并在 mission_complete 时清空路径；空路径也可能来自等待、生成失败或空航点指令，不能对任意 run 一概解释为任务完成。这三次首次清空后只观察到 `standby_release` 和最终 `shutdown_zero`，并非继续用 NMPC 求解跟踪。终点到达半径事件、之后的惯性滑行和动态跟踪误差应分层统计；原全窗口 CTE 仍是有限折线距离的描述性指标，不能重命名为严格终端停船误差。

三个 F2 成功 pilot 的 wall/sim 约同步、发布间隔中位约 200 ms/0.2 sim s，没有实测证据表明它们已经存在低 RTF 错配。但 wall timer 与物理 dt 不同时间域的机制仍在，应逐 run/epoch检查。旧包没有完整实际参考矩阵及 path/profile 版本，离线重算参考不可冒充原 solver 实际输入。下一次因果实验前应记录 actual ref、nearest/idx、profile_t0 与预测 X/U；本次未直接调参掩盖未知原因。

## 4. VRX 配置来源核对及结论边界

安装版本为 libgz-physics7 7.8.0-1~noble, libgz-sim8 8.15.0-1~noble。实际 SDF 与运行 effective YAML 的 19 项平面参数核对通过。总刚体质量为 14.2 kg，模型报告原点 yaw inertia=2.13 kg·m²，质心 yaw inertia=1.92552 kg·m²；主链接和两个 0.02 kg 桨链接分配不能只看主链接 14.16 kg 就报错。d_thruster=0.25 m 是半桨距。

SDF 使用 DART 原生 `fluid_added_mass`（xx=2, yy=8, yr=0.1817725, rr=3.41），Hydrodynamics 设 `disable_added_mass=true`、`disable_coriolis=true`，阻尼采用负稳定性导数及 abs 二次项，静水 current 为 0。这个配置避免插件和原生附加质量双重计入；原生物理引擎是否与三自由度模型在全部工况响应等价仍需独立实验。对照的是对应安装版本的[Gazebo 8.15.0 Hydrodynamics 源码](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/hydrodynamics/Hydrodynamics.cc)。

左右 Thruster 使用 `use_angvel_cmd=false`、物理推力输入 ±25 N、velocity_control=true。相应源码使用 force command 并向 link 施加 wrench；这说明配置/插件代码路径语义，不说明某次 DDS 消息已被 plant 接受，也不提供实际力传感测量。[Gazebo 8.15.0 Thruster 源码](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.15.0/src/systems/thruster/Thruster.cc)

当前控制器与 plant 仍同源使用生成的 effective 参数，未实施配置独立。Gazebo 另含浮力、heave/roll/pitch、刚体组合、推进器位置和 odom 滚动平均等机制。软件对拍通过不能把 `plant_equivalence_proven` 置 true，也不能用同源参数避免研究模型失配问题。

## 5. 四元数控制准入修复与验收

旧 helper 对全零四元数计算 `atan2(0,1)=0`，yaw 有限检查无法拒绝它；研究快照 invalid 也不会自动阻止控制状态写入。本次新增实际 gate：模长平方非有限或 `<1e-12` 时立即返回。有限组件平方溢出也被拒绝。

研究记录启用时，原始研究接收和 invalid 快照仍先保存。坏消息只增加 received 计数，不更新 accepted 身份/采样戳、六维控制状态、`last_odom_time_` 或 IMU 混合来源。关闭记录时，同样拒绝坏姿态，但不生成研究接收计数或快照。共享 yaw helper 和 path 回调未改，避免改变其他入口的契约。一般非单位四元数未新增归一化；IMU 消费有限 gyro z，不因未消费的 orientation 为零而拒绝有效 yaw rate。

新增四组真实节点测试覆盖首次坏输入（日志关/开且求解次数为 0）、六类坏姿态与 watchdog、单位 q/-q、IMU 有效率及非有限率。另有四组实际参考函数回归。完整结果为 **57 个不同 C++ GTest 全部通过**；colcon 汇总 **376 tests, 0 errors, 0 failures, 72 skipped**。72 跳过包括原有工具规则，不能声称全静态检查实际执行；cppcheck 按原 ament 性能规则未作完整分析。没有把 wrapper 数量当 376 个不同控制行为用例。

首轮编译因 test helper 引用 TU 私有 steady_now 失败；改用同域 std::chrono::steady_clock。第二轮功能 GTest 通过但格式检查失败；修正格式后第三轮整体通过。失败构建日志全部保留，没有更改断言或关闭 lint 来取得成功。此前 111 项 Python 回归属于 F2 已验收记录，本次没有 Python 生产变更，未重复跑并冒充新的 111 项结果。

## 6. 新 F3 正常运行回归

成功 run：`p0_f3_gate_straight_20261004_03`。目录 `/home/trevor/USV/.sgh-research/experiments/p0_f3_gate_straight_20261004_03`，原始 bag `/home/trevor/USV/data/sim_bags/p0_f3_gate_straight_20261004_03`。60 秒墙钟 armed 窗口，唯一隔离 ROS/Gazebo 域，动态 B、dt=0.2、horizon=20、200 ms 求解预算、±25 N、输出 scale=1；有效参数和 19 项生成模型参数匹配，实际 source/install/model 与 F3 全清单核对通过。

| 项目 | 实测 |
|---|---:|
| 源端记录窗口 wall s | 59.977102 |
| 有效 raw state 的 sim 覆盖 s | 59.960000 |
| StateSnapshot / AppliedControl / CycleTiming | 2999 / 301 / 300 |
| 队列丢弃 | 0 |
| 全窗口有限折线 CTE RMSE m | 0.248746 |
| 全窗口 body 速度模长最大值 m/s | 1.257138 |
| 控制器 CPU，单核等效百分比 | 6.617 |

源端摘要、bag 实扫、联合动作发布配对及时间诊断通过。只作为一次正常工况回归；启动/arm 边界、最后未知保持区间仍按契约保留，不是性能改善的统计结论，不证明独立实时监管或端到端执行时刻。正常 pilot 未替代坏姿态 GTest，也未在航行中的模拟传感器上注入异常。

两个早期 F3 采集尝试保留为未验收：新增 runner 分别误读清单容器结构和嵌套 vehicle 参数结构，完成采集后未生成通过结果；不计入成功 pilot。已用现有实际 dump 预检修正解析，再以新目录完成本成功运行。原失败文件及原 bag 均未覆盖。最终检查没有遗留 mpc_node 或 Gazebo 进程。

## 7. 复现与归档

数值对拍入口为当前实验目录的 `parity/run_nominal_parity.py`，真实 fixture 为 `fixture_v3_distinct.json`，结果在 `parity_results_v3`；原 v2 在 `parity_results`。输出目录已存在会拒绝，复现须改成新目录，避免覆盖证据：

```bash
ROOT=/home/trevor/USV
EXP=$ROOT/.sgh-research/experiments/p0_model_consistency_20261004_01
$ROOT/usv_rl/.venv/bin/python $EXP/parity/run_nominal_parity.py \
  --workspace $ROOT \
  --baseline $ROOT/.sgh-research/baselines/F3_20261004_quaternion_gate_01 \
  --fixture $EXP/fixture_v3_distinct.json \
  --output $EXP/parity_results_replay_NEW_ID
```

建模和测试原始源码、生成 C、独立编译二进制、逐案例数值、完整命令与日志留在 Ubuntu。Windows [验收元数据](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/outputs/P0_模型参考核验_2026-10-04/验收元数据.json)仅包含数值、身份、配置及 hash，不含连接密码、完整环境或私有源码正文。F3 freeze 后若 source/install/model hash 改变，不可继续使用同一个 baseline_id 声称一致。

## 8. 当前进度和下一项的执行依赖

| 门槛 | 当前状态 |
|---|---|
| 三次原修复与 F1/F2 发布端合同 | 已验收，旧原件保持 |
| Python/C++/native acados nominal 同参对拍 | 已完成，本次 v3 291 种不同输入 |
| 实际参考函数/列语义与旧运行诊断 | 已完成最小核验；速度偏差因果解释仍未闭合 |
| 退化 odom 四元数准入 | 已修复并回归 |
| F3 冻结与新正常 pilot | 已验收 |
| plant/controller 参数独立、6DOF响应对照 | 未完成 |
| PPO训练端动作历史与延迟队列 | 未完成，策略资产保持冻结 |
| P1 独立 worker / 固定 tick / 唯一出口 | 未完成 |
| plant 接受、实测力、精确执行时序、GP标签准入 | 未完成，相关 flags 保持 false |

**下一工作包先补配置独立和实际参考证据，再推进 P1 执行监管。** 最小顺序如下：

1. 新研究入口分别接受 nominal YAML 与 plant YAML；默认双份数值先与 F3 相同，以独立 SHA 和运行有效参数证明隔离。只修改 plant 一项参数时 controller dump 必须不变，反向也成立。不要把 current effective YAML 同源关系误当已经解耦。
2. 只作观测地记录 actual reference matrix、path/profile 身份、nearest/idx/t0、预测 X/U。核对插桩开关前后相同输入产生同一动作，先测开销。若后续扩消息 schema，应冻结新 baseline，并拒绝用旧包补造字段。
3. 保持 F3 权重和有效模型，建立 solver worker 与提交监管的分离；监管持有最新不可变候选，按固定 tick 检查状态/参考/模型/版本与年龄，并作为唯一物理输出者。一个线程若仍被同步 solver 和单线程 executor 阻塞，不能标作独立监管；现有 HOLD/零输出尚非经过证明的安全备份。
4. 首批故障覆盖 250/400 ms 求解、连续失败、旧候选、状态过期、clock reset、模型版本变更、停机；验收必须观察阻塞期间的提交/保持时刻、实际两路序列及唯一发布者。按已观察的保持间隔检查变化率，不能仍默认每次为 0.2 s。
5. 通过 P1 后再进入有限模型和备份证书的 P2；GP 先影子评估，等待真实输入区间/数据标签合同，PPO 继续使用冻结策略作为后期性能建议器。

GO：以 F3 开始上述配置/观测与 P1 工程工作。NO-GO：现在训练残差 GP、宣称无限时域/递归安全保证、用一次 pilot 声称性能显著改善，或把发布成功写成执行器已执行。速度超调、终点半径和滑行、非单位四元数、混合状态来源、低 RTF 及实际输入反馈都仍是需要显式处理的变量。
