# P1 真实 VRX 影子验证脚本

本文件说明 `run_p1_vrx_validation.py` 的启动契约及证据边界。当前交付仅是本地脚本和说明，尚未用这个脚本启动实验，不能据此宣称 M3、M4 或 M0b 通过。当前执行模式仍被未获资格的合同阻止；先完成根代理控制的 `no_output` 校准及审查，再启动独立的真实 VRX 影子实验。

## 启动组成

影子模式的三个控制相关原生进程是保留的 F5 `mpc_node`、新的 `p1_solver_worker` 和 `p1_regulator`。原 F5 控制器独占左、右物理输出，新 worker 和影子 regulator 不创建物理发布端点。Gazebo、桥接、原生规划器、录包器和有限 ROS CLI 子进程是额外的被监督基础进程，均保留实际启动身份。

`vrx.launch.py control_enabled:=false` 会同时关闭控制器和规划器。因此脚本先用该入口启动 plant、spawn 和 bridge，然后单独启动冻结的 F5 规划器。规划器保持原 `path_config.yaml`、同一组直行航点及原输入/输出 topic。脚本没有使用当前重编译的 legacy `mpc_node` 代替 F5。

| 冻结资产 | 实际路径或身份 |
|---|---|
| F5 baseline | `/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01` |
| F5 legacy 原生二进制 | `installed_snapshot/usv_mpc_ws/install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node`，SHA256 `bc753aa81d27e16e7df2570539e6bc66d34a3bc973afbee18fbf232ea85d41bc` |
| F5 规划器原生二进制 | `installed_snapshot/usv_mpc_ws/install/usv_planning_cpp/lib/usv_planning_cpp/path_planner_node`，SHA256 `3756f81f5bb35e97be2cfc2fe5dd7b7f0f364488f9621a695f17db4cee9a2d45` |
| F5 规划器配置 | `installed_snapshot/usv_mpc_ws/install/usv_bringup/share/usv_bringup/config/path_config.yaml`，SHA256 `53086a2ed0cbc60a7670a2137ac1d6f589ed7c54c564f969cccd3654b15dcb3a` |
| F5 源码父版本 | `source_snapshot/usv_mpc_ws/src/usv_mpc_cpp/src/mpc_node.cpp`；脚本检查其原 F5 SHA，源码保留在 Ubuntu |
| F5 固定直行航点 | `/home/trevor/USV/.sgh-research/experiments/p1_atomic_freeze_20261005_01/references/straight.yaml`，SHA256 `7294a7cb0813516433ebf7608eebf6d9420295443a2d1546918ead1d95061c9a` |
| F5 实际参数证据 | `/home/trevor/USV/.sgh-research/experiments/p1_f5_atomic_baseline_20261005_02/topic_graph.json` 中的 `effective_parameter_dump.stdout` 及其 SHA256 |
| F5 原启动输入证据 | 同一实验目录的 `launch_context.json` 中 `config_inputs` |

表中前三个 `installed_snapshot/...` 和 `source_snapshot/...` 路径都相对上述 F5 baseline 根目录。脚本在启动前读取冻结清单、验证这些文件的实际哈希及原生二进制执行权限；结束后复查所选 F5 资产。它不会改旧清单、旧实验或原文件权限。

影子模式的启动顺序为 recorder → VRX/bridge → 冻结规划器 → F5 legacy 端点与实际参数核验 → legacy 记录 armed 与真实 AppliedControl 身份 → worker/capability → regulator。worker 从自身启动后就开始有限 recording-ready 等待，必须看到 regulator 的 candidate 订阅；因此不能先启动 worker，再等待 legacy 的参数 dump、图发现和记录启用。此修复仅调整影子启动顺序，保留合同 timeout、原生进程身份与全源记录。execute 跳过 legacy 分支，仍保持 worker → regulator 两进程顺序。

## 六份固定输入与实际参数

脚本逐项复查 F5 `launch_context.json` 的六份原输入路径和原 SHA；这些文件用于证明模型、权重和参考输入保持不变：

1. `/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/p0_nominal_f3.yaml`
2. `/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/p0_plant_f3.yaml`
3. `/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/mpc_params.yaml`
4. `/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/mpc_params_vrx.yaml`
5. `/home/trevor/USV/usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml`
6. `/home/trevor/USV/.sgh-research/experiments/p1_atomic_freeze_20261005_01/references/straight.yaml`

legacy 参数从 F5 的真实参数 dump 生成，保留所有数学与准入参数；仅更换 `research_run_id`、`research_output_dir`、`research_config_hash` 和初始 `research_logging_armed=false`。启动后先 dump 实际 legacy 参数，并要求与准备的参数字典逐项相等，再通过真实参数服务将 logging armed 置为 true。`research_baseline_id` 保持 F5。新 worker/regulator 的 N20、dt0.2、19 项水动力、Q/R/Rd、Qf、原 solver 的 dT_max、参考 offset、fallback cruise 和 topic 必须与 F5 实际参数及被哈希的合同一致。

nominal 与 plant 通过已安装的 `usv_bringup.research_config_sources.prepare_config_sources` 分别保存到本次新目录，Gazebo 从新的 plant snapshot 生成本次 SDF/mesh。nominal 有效配置 SHA 必须等于合同的 `nominal_hash`。plant.mass 会影响 renderer 的水线宽和 hull mesh；这个脚本固定 baseline 的两份配置，没有将质量变化试验混入此次时间架构验证。

F5 原生二进制固定并不等于所有动态库都重新使用 F5 snapshot：ROS、消息类型库、acados 等仍由实际已 source 的环境加载。根代理应将当前 source/install 及相关运行依赖纳入独立 prelaunch 清单，并保留环境证据。脚本接收该清单，对所有列出的绝对路径执行前后哈希核验；不把调用者遗漏的资产宣称为已审计。

## 新合同与部署要求

脚本必须与 `owned_process_supervisor.py`、`run_no_output_calibration.py` 放在同一 Ubuntu runtime 目录，使用系统 `/usr/bin/python3`，source `/opt/ros/jazzy/setup.bash` 和 `/home/trevor/USV/usv_mpc_ws/install/setup.bash`。不得使用 PPO venv 代替 ROS 系统 Python。`usv_bringup`、`usv_simulation`、`usv_planning_cpp`、`usv_research_interfaces`、`usv_research_safety_cpp` 的真实 `ros2 pkg prefix` 都须属于声明的当前工作空间。

根代理应先部署、构建并记录实际 worker/regulator SHA，形成只读 prelaunch manifest 和新诊断合同的 SHA，然后调用脚本。清单格式为 `{"files":[{"path":"/absolute/file","sha256":"64 lowercase hex"},...]}`，必须由独立构建与来源门禁给出，不应在失败后重算预期值以掩盖资产变化。`--expected-assets` 所有路径必须绝对、唯一且实际哈希匹配。

当前脚本只接受 `p1-execution-contract-v2` schema 且 `diagnostic_contract_revision=2`；旧 v1 合同保留作历史证据，不能用于本脚本当前部署。新合同须包含真实 `expected_imu_frame="wamv/wamv/base_link/imu_sensor"`、有限正整数 `recording_ready_timeout_ns`，以及正整数 `odom_sim_lag_ns`、`imu_sim_lag_ns`、`source_future_slack_ns`、`mixed_skew_ns`。odom 的 `map` / `wamv/base_link` 与 IMU frame 单独核验，脚本不改 bridge 或 SDF frame。shadow 合同必须明确 `execute_qualified=false`、`parameters_are_diagnostic_only=true`。cleanup/watchdog/recording-ready 的单项界限必须大于 0 且不超过 60 秒。

regulator 启动显式传入 `recording_observer_node:=p1_vrx_validation_driver`，其首个 tick 的实际 publisher 匹配门禁需要匹配本 driver 与 recorder。脚本也核对这个实际参数。旧冻结 legacy 没有新增的远端 writer-match API；脚本仅能在 logging arm 前记录它的 writer/recorder 图已发现，后续通过实际 `AppliedControl` 身份确认它在输出。

下面命令只展示 root 在完成独立门禁后应填写的调用方式。本脚本不生成有效资格、不自动改合同，也不替根代理启动实验：

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/USV/usv_mpc_ws/install/setup.bash
/usr/bin/python3 /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/runtime/run_p1_vrx_validation.py \
  --mode shadow \
  --workspace /home/trevor/USV/usv_mpc_ws \
  --contract <ROOT_VERIFIED_DIAGNOSTIC_CONTRACT_PATH> \
  --contract-hash <ROOT_VERIFIED_CONTRACT_SHA256> \
  --expected-assets <ROOT_VERIFIED_CURRENT_SOURCE_INSTALL_MANIFEST_PATH> \
  --worker-sha256 <ROOT_VERIFIED_BUILT_WORKER_SHA256> \
  --regulator-sha256 <ROOT_VERIFIED_BUILT_REGULATOR_SHA256> \
  --experiment-root /home/trevor/USV/.sgh-research/experiments \
  --run-id p1_vrx_shadow_20261005_01 \
  --duration 60 --ros-domain 97
```

`--run-id`、本次目录、bag、源 JSONL、各 CLI console 和新配置必须是新目标；脚本不覆盖或删除旧结果，不在一次运行中切换 shadow/execute。`--mode execute` 只有在精确哈希合同同时满足 `execute_qualified=true`、`parameters_are_diagnostic_only=false` 时才允许启动；当前阶段禁止使用该模式。资格应由 M0b 真实校准、指标门槛与审查另行决定。shadow 中观察到的性能不能作为 execute 的资格证据。

## 录包与证据范围

recorder 首先建立 18 个 topic 的实际订阅，随后启动 VRX、规划器和控制相关进程。ROS CLI 使用 `ros2 bag record --storage mcap --qos-profile-overrides-path ...`，不使用 `--use-sim-time`；bag 时间戳为存储接收时间，不能与 `CLOCK_MONOTONIC` 或仿真时间直接相减。原消息内的 stamps、typed job/candidate/decision 中的各时间域保持原值。

- 新四流：`/p1/solve_job`、`/p1/solve_candidate`、`/p1/worker_capability`、`/p1/execution_decision`。
- 旧四流：`/research/state_snapshot`、`/research/control/applied`、`/research/cycle_timing`、`/research/reference_prediction`。
- 原始流：`/clock`、合同中的 odom/IMU/path/profile、左右物理推力、`/mpc/status`、`/mpc/predicted_trajectory`、`/p1/stop`。

原始 clock/odom/IMU recorder QoS 为 best effort；typed 观察流为 reliable，worker capability 为 transient local，录包深度 1024。driver 不创建假传感器、不创建占位物理 publisher，不伪造 producer 或 worker identity。

本次实验保留 `run_context.json`、`runner_summary.json`、`owned_process_ledger.jsonl`、实际参数 dumps、topic 图、两份 P1 源 JSONL、旧 legacy 源目录、全 raw bag、新模型配置、CPU 实际样本和前后资产门禁。CPU 使用同 PID/start_ticks 的实际 `/proc` CPU tick 差及每个进程实际采样时段，给出一个 CPU 核心的百分比。

新 typed 三个业务流要求全 source identity sets 与全 bag 对账，不能仅剪裁验证窗口或丢弃最初 sequence。真实 VRX 的 clock/odom/IMU/path/profile 没有提供全运行 publisher-side 计数，因此 `raw_input_recording_complete=null`，原始前缀/后缀完整性未知。旧 legacy source/bag 需要独立对账，runner 也保留 unknown，不以 logging arm 或“bag 存在”代替完整性证明。`driver_receive_counts` 仅是 driver 自己收到的计数。

物理 publisher 图在启动门禁与每秒样本中要求各 channel 恰好 1 个，节点名为 shadow 的 `mpc_controller_node` 或将来获资格 execute 的 `p1_regulator`。summary 给出 checker 约定的四字段：`graph_new_physical_publishers_zero`、`graph_sole_physical_owner_verified`、`graph_physical_owner_node`、`graph_physical_publishers_per_channel`。shadow 的全图 `graph_no_physical_publishers=false`。这些图样本不是持续图监控，也不证明 Gazebo plugin 已接纳动作、真实物理力、两通道物理原子性或精确 plant 步长。

根代理在收尾后单独运行 `check_p1_execution.py --experiment RUN --bag RUN/raw_bag --contract EXACT_CONTRACT`。checker 独立扫描实际 storage，并对 source、typed bag、进程及 flush 事实绑定。runner 的退出码 0 仅表示完成数据采集和本脚本的资源收尾，状态仍为 `runtime_data_collected_pending_checker`；不赋予正常合同通过、GP 标签资格或执行资格。

## 停止与故障保留

正常窗口后先重复发布 `/p1/stop=true` 并等待合同的 shutdown grace，shadow 的 legacy、传感器与 recorder 保持到新 regulator 收尾。之后按 regulator、worker、legacy、planner、VRX 的顺序有限 SIGINT → SIGTERM → SIGKILL；在停止 recorder 前补清理真实观察到的 Gazebo 跨进程组后代，使 recorder 保留可收到的关闭尾部，再停止 recorder 并复查。

`OwnedTree` 只通过本 runner 实际创建的 root PID/start_ticks 与真实父子关系捕获跨组后代。发送信号前重新核验 boot、PID start_ticks、domain 和 partition；同 partition/domain 的未知进程不能因环境相同获得所有权，也不会被杀。未知残留、身份变更、PID 重用、group 清理失败或监督日志写入失败会使实验失败并保留。其他 UID 的 `/proc/environ` 通常无法读取，本 runner 不对其建立所有权；same-UID 环境审计失败不能被当作清理成功。没有 `pkill` 或按全系统名字删除进程。

`--test-delay-ms 50/150/250/400` 是 worker result 的受控延迟，`--test-native-block-ms` 是进入原生求解前的受控屏障；两者必须被哈希合同明确允许，而且是独立新 run。屏障用例不能证明真实 acados 内部死锁。path clear、clock pause/reset 等额外故障注入未在本 runner 实现，后续应使用独立新用例、明确输入来源和原始记录，不能自行把正常 baseline 标签改为这些故障已验证。
