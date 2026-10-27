# 独立 nominal / plant 配置实施包

本目录只准备局部补丁、可部署的新文件、独立来源检查和试验预注册。未连接 Ubuntu、未修改 production、未修改 F3、未新跑 ROS/Gazebo。日期虽沿用工作包目录 2026-10-04，本次收尾发生在 2026-10-05。

## 已核对的来源

F3 metadata SHA256 为 `f597cfc3f4a8826d6b721205bfb97cc399014225b957b7cece4438545d68c80a`，F3 manifest 为 `9c64426cc68d3eb1949fa63d564725499870bbb02d649022a2116088a0bfeb35`。以下本地镜像已逐字节核对：

| 来源 | F3 SHA256 |
|---|---|
| `vrx.launch.py` | `090f40616d15567d03517632d41293b80fec762d2cb80915d00f68fa986e3259` |
| `p0_contract_recording.launch.py` | `039a161b07631e8e11ffdfc16476012369648d19a083e45b9b00c0df34d39b42` |
| 原 plant `usv_params_sim.yaml` | `39ee9a22f71b66c9a8c805d34cb939ab657f871a24fa97a10ca49d8121892d35` |
| `vrx_model.yaml` | `edcd9d129357651c8bc9c0ca9d081e91bc6467db5420fd88e305e3e77281093a` |
| `usv_bringup/setup.py` | `ed3a5482a30a3915fe719bb0397c2e97ec0148c0a5cba830886e6c3d7ec13728` |

renderer 原文未导出。实现使用 root 核对的实际接口 `build_model(vehicle_file, simulation_file, output_dir, name='wamv')` 和现有 `launch_vrx(context)`；后者读取 `vehicle_config`、`simulation_config`，写出 `effective_vehicle.yaml` 和 `model_report.json`，设置原 `effective_vehicle` 与 `plant_*` launch configuration。没有改 renderer。

## 部署映射

所有目标位于 `/home/trevor/USV/usv_mpc_ws/src/usv_bringup`。

| 本目录文件 | Ubuntu 目标 |
|---|---|
| `research_config_sources.py` | `usv_bringup/research_config_sources.py` |
| `__init__.py` | `usv_bringup/__init__.py` |
| `p0_config_reference_recording.launch.py` | `launch/p0_config_reference_recording.launch.py` |
| `p0_nominal_f3.yaml` | `config/p0_nominal_f3.yaml` |
| `p0_plant_f3.yaml` | `config/p0_plant_f3.yaml` |

五个目标均为新增文件，应在现场先检查不存在。不要用已有同名文件覆盖用户改动。现场已核对 setup.py 的 data_files 用 glob 自动安装新 launch/config，但 `packages=[]`，因此原先 helper 模块不能被安装导入。补充 `apply_bringup_setup_patch.py` 把唯一 `setup(packages=[])` 改为 `packages=[package_name]`，配合新增 `usv_bringup/__init__.py` 安装 helper；不改 setup 其他字段。要求上表 F3 setup SHA、唯一 package_name='usv_bringup'、唯一 setup call 和空 packages keyword，重复应用或已有备份拒绝，独占备份名 `.pre_p0_python_helper_package`。

```bash
python3 apply_bringup_setup_patch.py --target /home/trevor/USV/usv_mpc_ws/src/usv_bringup/setup.py
python3 apply_bringup_setup_patch.py --target /home/trevor/USV/usv_mpc_ws/src/usv_bringup/setup.py --apply
```

root 应实际 colcon build usv_bringup，source ROS 与新 install 后在工作树外（如 /tmp）运行 `/usr/bin/python3`，验证 `import usv_bringup.research_config_sources`；保存 `module.__file__`、实际文件 SHA 和 package prefix。必须来自新安装 overlay，不能把 local cwd/PYTHONPATH 临时塞入源码后声称安装成功。对于 symlink-install，同时记录安装路径及 resolved 源码路径和匹配 SHA。本地 isolated subprocess 的 package-layout smoke 只证明新布局可导入，不能代替该现场安装门禁。

`apply_config_launch_patch.py` 只对现场 `launch/vrx.launch.py` 的四个唯一锚点作局部替换，保留原文件换行方式；要求 SHA 匹配且没有 `P0_INDEPENDENT_CONTROLLER_CONFIG` marker。默认只预览，`--apply` 才写目标；写入前用独占新文件保存 `.pre_p0_independent_config` 原件。重复运行、目标已有改动、重复锚点、混合换行、已有备份都拒绝。F3 原字节的预期补丁后 SHA 为 `a04d9b10a5924a647604f35abc337d8118bfacf6826e21fb0f0bf6477db1d5b5`。

先应用本四锚点补丁，再应用 recording_entry 的观测 args 补丁；如反过来，必须先只读核对新增差异和锚点，显式提供已核对的新 expected SHA，不能忽略 guard。

```bash
python3 apply_config_launch_patch.py --target /home/trevor/USV/usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py
python3 apply_config_launch_patch.py --target /home/trevor/USV/usv_mpc_ws/src/usv_bringup/launch/vrx.launch.py --apply
```

## 实际来源和保留边界

新入口为 `p0_config_reference_recording.launch.py`，参数为 `nominal_vehicle_config`、`plant_vehicle_config`、`simulation_config` 和显式新的 `config_output_dir`。`bag_path`、`research_output_dir`、`model_output_dir`、`config_output_dir` 都必须不存在且不相互包含，父目录提前创建。旧入口保持原共享默认，A/C 和 PPO 未改。

nominal YAML 直接读出 19 个 `vehicle` 参数，不作 plant 的交叉项对称投影；它只允许 vehicle、thruster 两部分，不能夹带控制代价、logging、topic 或其他覆盖。nominal thruster forward/reverse 两个正幅值产生 B 的 `dynamic.T_max/T_min`。新 wrapper 传 `controller_vehicle`、`controller_tmax`、`controller_tmin`；旧 vrx 的这三个值没被覆盖时分别 fallback 到原 effective YAML、plant_tmax、plant_tmin。

plant 输入单独冻结，并作为现有 renderer 的唯一 `vehicle_config`。`simulation_config` 仍决定 plant 的 `symmetric_mean/strict` 投影；此设置不会重新投影 nominal。设置、两方原始输入、nominal effective YAML 分别存文件和 SHA。

默认 nominal 来自 F3 成功 `_03` 的实际运行参数，19 数值与 F3 一致；默认 plant 保留原辨识输入字节，经过原 symmetric_mean 后有效交叉项与 F3 一致。默认 nominal 文件 SHA 为 `78d7133fd4f11d47bd534d820b02489e440bd8664bef254893e830fe4bc7dc84`。默认 plant 文件 SHA 与原 plant 相同为 `39ee9a22f71b66c9a8c805d34cb939ab657f871a24fa97a10ca49d8121892d35`。它们是两个独立资产，不能传同一个 inode。

本次默认三个 normal pilot 的 physical plant 命令边界仍为 ±25 N，vrx_thrust_scale、旧 publish clamp、PPO、权重和参考速度未改。solver 输入约束来自 nominal，plant Thruster 命令限制来自 plant；helper 分列二者。±25 N 是配置的 plant 命令边界，不能自动解释为某次消息已接受、实际推力已测量或输出已原子执行。本实现没有声称所有非模型参数都独立，原其他参数仍由 mpc_params/overlay/research 开关控制。

## 记录与运行门禁

新 recorder 共 13 话题，新增 `/research/reference_prediction`。`enable_reference_prediction_logging` 默认为 true；`research_nominal_config_hash` 自动取本次 `nominal_effective.yaml` 的 SHA。调用者显式提供不一致 hash 会拒绝，已生成的配置证据保留为失败尝试。此身份包含 19 水动力数值和独立 thruster 限值，两个 solver constraints 由同一份限值推导。

`config_output_dir/config_sources.json` 是静态来源证据。它不会把 runtime 或 plant generated 标为已验证。新 runtime 检查入口：

```python
from usv_bringup.research_config_sources import verify_runtime_sources
evidence = verify_runtime_sources(config_output_dir, model_output_dir, actual_ros_parameter_dump_path)
```

传真实 dump 文件路径可保留精确文件 SHA；传 dict 仅核对 caller 映射，必须外部另绑真实 dump 身份。检查要求控制器实际 19 参数和 Tmax/Tmin 与独立 nominal 一致，生成 plant report/effective YAML 与明确投影后的 plant 一致，两份源快照未改，SDF 的两个 Thruster 边界与 plant 限值一致。返回新 evidence，不回改静态 config_sources。它不构成 6DOF 响应、执行确认、P1 或 GP 标签验收。

root runner 还必须绑定新 frozen source/install/model 清单、真实 overlay 与 dump、config_sources SHA，以及 reference_prediction_contract 的 schema、矩阵 layout、horizon/dt/backend、记录/预测策略和 nominal_config_hash。这些实际协议字段由 recording_entry/checker 提供，helper 不猜它们。

## 预注册与测试

`preregistered_fixture.json` 三个 normal pilot 为 default、plant.mass 14.2→17.04（+20%）、nominal.mass 14.2→17.04（+20%），每次60秒墙钟。初稿15.62只因与 root 已注册的 preflight/run_f4_pilot 输入17.04不一致而修正；初稿完整保存为 `preregistered_fixture_initial_15p62.json`，SHA为 `56e3ac7113506724710a9a6d725438dcae8a81d6bbfb2b2ae8702d43c46444fa`。此协调只统一预定单因素幅度，未改变任何验收比较、阈值、运行长度或输出后判定。unit helper中的15.62保留为任意单因子分支测试，不是实际pilot设定。

另有两项只作 helper/实际 launch wiring 对照：单改 plant thruster forward 25→20、单改 nominal thruster forward 25→20，证明 solver 与 plant 边界不隐式互改；它们不计入默认保持 ±25 N 的三个 normal pilot。全部失败保留，不调整参数取得验收。

质量单因素比较要比实际有效参数和 SHA；不同 run 的 producer、baseline、output 路径等身份字段须列明排除，不能拿全 dump 字节差异误判耦合。名义质量变化下 SDF 的 mesh/output 路径可能不同，保留原始 SHA，另仅规范化这些生成路径做语义比较，不能任意删字段让结果相同。

```powershell
& 'C:\Users\sgh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s 'work/p0_config_reference_2026-10-04/config' -p 'test_*.py' -v
```

本地 helper/guard/launch Python wiring 和 setup/package-layout 的 22 项测试通过。launch wiring 使用小型 API doubles 执行真实 launch Python，未运行 ROS；生成 fixture 是 synthetic 验证 checker 分支，未把 synthetic report 当实际 renderer 结果。现场仍须构建、核验真实安装import、运行真实 launch、采集 parameter dump/SDF、新四流合同检查及不可覆盖新基线后才能写已实施。
