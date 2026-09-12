# ROS 2 工作空间迁移到树莓派 5 的计划

> 适用范围：将开发机 `/home/trevor/USV/usv_mpc_ws` 中经过确认的代码更新到树莓派 5，并恢复由 `usv-system.service` 管理的艇载运行环境。  
> 目标环境：Raspberry Pi 5 8 GB、Ubuntu/ROS 2 Jazzy、AArch64、工作空间 `/home/trevor/usv_mpc_ws_B`。  
> 文档状态：迁移执行计划，不代表已经完成部署。  
> 编制日期：2026-09-12。

## 1. 迁移目标与原则

本次迁移把一个**可追溯的源码快照**发布到树莓派，在树莓派上使用其 AArch64 版 acados、CasADi 和 ROS 2 Jazzy 重新编译，再完成静态检查、单元测试、无桨台架验证和方案 A/B 启动验证。

执行时遵循以下原则：

1. 不把开发机的 `build/`、`install/`、`log/` 或任何 x86_64 动态库复制到树莓派。
2. `src/usv_mpc_cpp/acados_generated/` 中已纳入源码管理的生成代码、JSON 和 CMake 文件属于发布源码，必须随版本迁移。
3. 部署前把当前未提交修改整理成一个明确的提交或发布归档。仅在树莓派执行 `git pull` 不能得到开发机尚未提交的修改。
4. 在新目录完成依赖检查和预编译；进入维护窗口后才停止艇载服务并切换正式目录。
5. `usv-system.service` 运行时禁止手工启动另一套 `mavros` 或 `real.launch.py`，否则两个进程会争用飞控串口。
6. 首次运行必须在船体固定、推进器断电或拆桨、飞控未解锁的条件下完成。
7. 文档、脚本和命令记录中不得保存 SSH、VPS 或其他明文密码；使用 SSH 密钥或现有安全凭据。

## 2. 当前基线

开发工作空间包含以下 6 个 ROS 2 包：

| 包 | 迁移用途 |
|---|---|
| `usv_mpc_cpp` | 运动学/动力学 MPC、CasADi/IPOPT 与 acados 后端 |
| `usv_mpc_kinematic_cpp` | 运动学 MPC 运行节点 |
| `usv_planning_cpp` | 路径规划和轨迹相关节点 |
| `usv_safety_cpp` | 安全监督与状态检查 |
| `usv_simulation` | 遥测桥、仿真及部分运行辅助组件 |
| `usv_bringup` | 真实艇、仿真和整体启动入口 |

截至编制本计划时，MPC 相关本地验证已通过：

- MPC 核心测试 9 项；
- acados 测试 8 项；
- 后端一致性测试 4 项；
- `usv_bringup` 启动配置测试 5 项。

这些结果仅作为当前开发基线。生成发布快照后仍需重新执行第 5 节的完整发布门禁，因为当前工作树含有未提交修改，而且尚未以最终发布快照运行全部 6 个包的完整构建。

## 3. 部署前必须确认的差异

下列信息在现有文档或配置之间不一致，不能直接采用旧文档值。迁移前应以树莓派当前服务文件、实际设备和本次发布配置为准，并填写第 13 节的发布记录。

### 3.1 飞控串口

- 旧艇载说明记载为 `/dev/ttyAMA0:921600`；
- 当前工作空间 README 记载为 `/dev/ttyAMA10:921600`。

在树莓派上核实：

```bash
ls -l /dev/ttyAMA* /dev/serial/by-id 2>/dev/null
systemctl cat usv-system.service
rg -n "ttyAMA|fcu_url|921600" /home/trevor/usv_mpc_ws_B/src /etc/default/usv-system 2>/dev/null
```

确认标准：实际存在的串口、MAVROS `fcu_url` 和 systemd 启动参数三者一致。不要为了匹配文档而更改一个正在正常工作的设备名。

### 3.2 遥测端口

艇载说明主体使用 TCP `8765`，文末另有 `7865` 的记录。迁移前检查当前服务实际监听端口：

```bash
systemctl cat usv-system.service
rg -n "8765|7865|telemetry|bridge" /home/trevor/usv_mpc_ws_B/src /etc/default/usv-system 2>/dev/null
ss -ltnp | rg ":(8765|7865)"
```

本次迁移不顺带修改公网映射。先保持当前已验证端口，部署后再验证树莓派、frp 和岸站三端一致。

### 3.3 RC 输入与电机输出编号

当前代码的 RC 覆盖输入约定为转向 CH1、油门 CH3；旧艇载说明中的 SERVO1/SERVO2 是飞控电机输出。两者属于不同接口，不能按相同编号互相替换。迁移验收应分别检查：

- ROS/MAVROS 发布的 RC override 通道编号；
- ArduRover 的 SERVO 输出功能和左右电机接线。

### 3.4 ROS 话题名称

旧说明中部分话题带有重复的 `/mavros/mavros/` 前缀。执行验证时以当前 [topic_contract.md](topic_contract.md) 和 `ros2 topic list` 的实测结果为准。

### 3.5 包依赖声明

静态检查发现 `usv_bringup/package.xml` 没有完整声明启动文件引用的运行时包，其中包括工作空间内的 `usv_mpc_kinematic_cpp`、`usv_simulation`，以及特定启动路径可能使用的 `ntrip_client`。VRX/Gazebo 依赖只用于开发机仿真，不应因此在艇载系统安装完整仿真栈。

发布前应完成以下二选一动作：

1. 补齐真实艇启动所需的 `exec_depend`，让 `rosdep` 能复现依赖；或
2. 在发布记录中明确这些包由同一工作空间或系统预装提供，并用 `rosdep check` 和真实启动测试证明依赖完整。

## 4. 分阶段迁移与放行门禁

| 阶段 | 主要动作 | 放行条件 |
|---|---|---|
| G0 发布冻结 | 清理变更、生成唯一版本号 | 快照可追溯，预期文件全部纳入 |
| G1 开发机验证 | 完整构建、测试、依赖和生成代码检查 | 构建与测试无失败 |
| G2 树莓派预检 | 核对架构、ROS、acados、CasADi、串口和服务 | 环境差异已记录并解决 |
| G3 预发布 | 传输到独立目录并在树莓派原生编译 | AArch64 构建与测试通过 |
| G4 正式切换 | 停服务、备份、部署到固定工作空间、重编译 | 服务能启动且无缺失库 |
| G5 台架验收 | 验证节点、话题、MAVROS、方案 A/B 和遥测 | 无重复进程、无控制输出异常 |
| G6 水试 | 低速短时试验并观察求解器和安全状态 | 无持续求解失败或控制跳变 |

任一门禁失败就停止向下一阶段推进。G4 之后失败时按第 11 节回滚。

## 5. G0/G1：在开发机生成发布快照

### 5.1 审核变更范围

```bash
cd /home/trevor/USV
git status --short
git diff --stat
git diff --check
```

逐项确认以下文件属于本次部署：

- MPC 源码、配置和测试；
- `acados_generated/` 下的生成 C 源码、头文件、JSON 和 CMake 文件；
- `usv_bringup` 的真实艇启动配置；
- 安全、规划和遥测桥的相关修改。

不得把 bag、运行日志、临时生成物、密码文件或个人配置加入发布快照。

### 5.2 建立可追溯版本

推荐使用 Git 提交作为唯一发布源：

```bash
cd /home/trevor/USV
git add <本次迁移确认过的文件>
git commit -m "Prepare Raspberry Pi MPC deployment"
git tag -a pi5-<YYYYMMDD>-<序号> -m "Raspberry Pi MPC release"
git rev-parse HEAD
git status --short
```

要求 `git status --short` 在发布范围内为空。若保留与本次部署无关的本地修改，应使用明确的文件列表制作归档，不能把整个脏工作树当成发布版本。

若树莓派无法访问 Git 远端，可从该提交生成传输目录或归档；仍需记录提交 SHA 和归档 SHA-256。

### 5.3 完整构建和测试

```bash
cd /home/trevor/USV/usv_mpc_ws
source /opt/ros/jazzy/setup.bash
export ACADOS_SOURCE_DIR="$HOME/acados"
export LD_LIBRARY_PATH="$HOME/acados/lib:${LD_LIBRARY_PATH:-}"

colcon build \
  --symlink-install \
  --cmake-force-configure \
  --cmake-args -DCMAKE_BUILD_TYPE=Release

source install/setup.bash
colcon test --event-handlers console_direct+
colcon test-result --verbose
```

通过标准：

- 6 个包均完成构建；
- `colcon test-result --verbose` 无失败；
- `git diff --check` 无错误；
- `usv_mpc_cpp` 的 core、acados 和 backend consistency 测试全部通过；
- `usv_bringup` 配置测试全部通过。

### 5.4 检查 acados 生成代码

```bash
cd /home/trevor/USV/usv_mpc_ws
rg -n '"cost_type"[[:space:]]*:[[:space:]]*"NONLINEAR_LS"' \
  src/usv_mpc_cpp/acados_generated
find src/usv_mpc_cpp/acados_generated -type f \
  \( -name '*ext_cost*' -o -name '*external_cost*' \) -print
```

第二条命令应无输出。若 OCP 结构、代价形式、状态或控制维度发生变化，必须先重新生成并验证 acados 代码，再建立新的发布快照。

## 6. G2：树莓派只读预检

使用 SSH 密钥登录，不在命令、文档或日志中写密码。以下命令不会更改运行状态：

```bash
ssh trevor@192.168.1.220

uname -m
cat /etc/os-release
source /opt/ros/jazzy/setup.bash
printf 'ROS_DISTRO=%s\n' "$ROS_DISTRO"
python3 --version
df -h /home
free -h

systemctl is-active usv-system.service
systemctl cat usv-system.service
cat /etc/default/usv-system 2>/dev/null
readlink -f /home/trevor/usv_mpc_ws_B
```

期望结果：架构为 `aarch64`，ROS 发行版为 `jazzy`，Python 与本机安装的 CasADi/acados 兼容，磁盘空间足以同时保留当前版本、预发布目录和一次备份。

### 6.1 验证树莓派原生 acados

```bash
test -f "$HOME/acados/lib/libacados.so"
file "$HOME/acados/lib/libacados.so"
ldd "$HOME/acados/lib/libacados.so" | rg "not found" || true
git -C "$HOME/acados" describe --tags --always --dirty 2>/dev/null || true

python3 - <<'PY'
import casadi
print("CasADi", casadi.__version__)
PY
```

目标基线为树莓派本地编译的 acados v0.5.4。`file` 应显示 AArch64/ARM64；`ldd` 不得报告 `not found`。不要从开发机复制 `~/acados` 或其 `.so` 文件。

### 6.2 保存当前运行基线

```bash
systemctl status usv-system.service --no-pager
journalctl -u usv-system.service -n 100 --no-pager
ps -ef | rg "mavros|mpc_node|safety|telemetry" | rg -v "rg "
ros2 node list
ros2 topic list
```

记录当前方案、正常节点、关键话题、串口和遥测端口。这些信息用于部署后的同项对比。

## 7. G3：传输到预发布目录

本计划使用：

```text
/home/trevor/usv_mpc_ws_B                    正式运行目录
/home/trevor/usv_mpc_ws_B_staging/<DEPLOY_ID> 预发布目录
/home/trevor/usv_backups/<DEPLOY_ID>          回滚备份目录
```

`DEPLOY_ID` 使用固定值，例如 `20260912_mpc_update_01`，不要在多台机器上分别生成不同时间戳。

### 7.1 Git 方式（推荐）

在开发机提交并推送精确版本后，在树莓派执行：

```bash
export DEPLOY_ID=20260912_mpc_update_01
mkdir -p "$HOME/usv_mpc_ws_B_staging"
git clone <项目仓库地址> "$HOME/usv_mpc_ws_B_staging/$DEPLOY_ID/repo"
cd "$HOME/usv_mpc_ws_B_staging/$DEPLOY_ID/repo"
git checkout --detach <已记录的提交SHA>
git rev-parse HEAD
```

工作空间位于仓库内的 `usv_mpc_ws` 子目录：

```bash
cd "$HOME/usv_mpc_ws_B_staging/$DEPLOY_ID/repo/usv_mpc_ws"
```

### 7.2 rsync 方式（树莓派不能访问 Git 时）

先在树莓派创建空的发布目录：

```bash
export DEPLOY_ID=20260912_mpc_update_01
mkdir -p "$HOME/usv_mpc_ws_B_staging/$DEPLOY_ID/usv_mpc_ws"
```

再从开发机执行一次预览：

```bash
rsync -anv \
  --exclude='.git/' \
  --exclude='build/' \
  --exclude='install/' \
  --exclude='log/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  /home/trevor/USV/usv_mpc_ws/ \
  trevor@192.168.1.220:/home/trevor/usv_mpc_ws_B_staging/20260912_mpc_update_01/usv_mpc_ws/
```

确认预览列表后去掉 `n` 执行正式同步。不要使用 `--delete` 覆盖当前正式工作空间。传输完成后，为源码归档生成校验值并保存到发布记录：

```bash
cd "$HOME/usv_mpc_ws_B_staging/20260912_mpc_update_01"
tar --exclude='build' --exclude='install' --exclude='log' \
  -czf usv_mpc_ws_source.tar.gz usv_mpc_ws
sha256sum usv_mpc_ws_source.tar.gz
```

## 8. 树莓派依赖与原生预编译

### 8.1 依赖检查

在预发布工作空间执行：

```bash
cd <预发布工作空间路径>
source /opt/ros/jazzy/setup.bash
rosdep check --from-paths src --ignore-src
```

先保存缺失依赖列表，再按系统维护策略安装：

```bash
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
python3 -m pip install --user -r requirements.txt
```

确认至少具备：编译工具、colcon、Eigen3、nlohmann-json、MAVROS、`mavros_msgs`、`geographic_msgs`、rosbag2/MCAP，以及真实艇启动所用的其他 ROS 包。CasADi Python 版本与 C++ 链接库必须来自同一套树莓派环境。

`rosdep` 不会自动安装项目自编译的 acados。其版本和动态库检查按第 6.1 节单独完成。

### 8.2 原生预编译

树莓派 8 GB 建议限制并行度，避免编译阶段挤占运行服务资源。预编译应在船只不执行任务时进行：

```bash
cd <预发布工作空间路径>
source /opt/ros/jazzy/setup.bash
export ACADOS_SOURCE_DIR="$HOME/acados"
export LD_LIBRARY_PATH="$HOME/acados/lib:${LD_LIBRARY_PATH:-}"

colcon build \
  --executor sequential \
  --symlink-install \
  --cmake-force-configure \
  --cmake-args -DCMAKE_BUILD_TYPE=Release

source install/setup.bash
colcon test --executor sequential --event-handlers console_direct+
colcon test-result --verbose
```

预编译通过后检查主程序的动态库：

```bash
ldd install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node | rg "not found" || true
```

若输出任何 `not found`，不得切换正式版本。

## 9. G4：维护窗口、备份和正式切换

### 9.1 进入安全状态

1. 船体上岸或牢固系泊；
2. 推进器断电、拆桨或采取等效隔离；
3. 飞控保持未解锁；
4. 记录当前运行方案；
5. 确认可通过本地网络或物理终端登录树莓派，避免只依赖公网隧道。

停止服务并确认没有残留进程：

```bash
sudo systemctl stop usv-system.service
systemctl is-active usv-system.service
ps -ef | rg "mavros|mpc_node|safety|telemetry" | rg -v "rg "
```

`systemctl is-active` 应返回 `inactive`，进程检查不应出现旧的控制节点或 MAVROS。

### 9.2 备份

```bash
export DEPLOY_ID=20260912_mpc_update_01
mkdir -p "$HOME/usv_backups/$DEPLOY_ID"

cp -a "$HOME/usv_mpc_ws_B" \
  "$HOME/usv_backups/$DEPLOY_ID/usv_mpc_ws_B"
sudo cp -a /etc/default/usv-system \
  "$HOME/usv_backups/$DEPLOY_ID/usv-system.default" 2>/dev/null || true
sudo cp -a /etc/systemd/system/usv-system.service \
  "$HOME/usv_backups/$DEPLOY_ID/usv-system.service" 2>/dev/null || true
systemctl cat usv-system.service \
  > "$HOME/usv_backups/$DEPLOY_ID/usv-system.service.effective.txt"
```

确认备份目录可读，并记录旧版本提交 SHA 或源码归档校验值。

### 9.3 更新固定工作空间

systemd 和 `usv-scheme` 当前预期使用固定目录 `/home/trevor/usv_mpc_ws_B`。为避免把预发布目录中带有旧绝对路径的构建产物直接搬入正式目录，只同步源码，然后在固定目录重新构建。

```bash
mkdir -p "$HOME/usv_mpc_ws_B_next_source"
rsync -a \
  --exclude='build/' \
  --exclude='install/' \
  --exclude='log/' \
  <预发布工作空间路径>/ \
  "$HOME/usv_mpc_ws_B_next_source/"

mv "$HOME/usv_mpc_ws_B" \
  "$HOME/usv_backups/$DEPLOY_ID/usv_mpc_ws_B_runtime"
mv "$HOME/usv_mpc_ws_B_next_source" "$HOME/usv_mpc_ws_B"
```

如果前面的完整备份已占用较多磁盘空间，可把“完整备份”和“运行目录移动”合并为一次操作；必须保证旧目录仍完整存在于 `$HOME/usv_backups/$DEPLOY_ID/`，且回滚命令已经检查无误。

### 9.4 在正式路径干净构建

```bash
cd "$HOME/usv_mpc_ws_B"
source /opt/ros/jazzy/setup.bash
export ACADOS_SOURCE_DIR="$HOME/acados"
export LD_LIBRARY_PATH="$HOME/acados/lib:${LD_LIBRARY_PATH:-}"

colcon build \
  --executor sequential \
  --symlink-install \
  --cmake-force-configure \
  --cmake-args -DCMAKE_BUILD_TYPE=Release

source install/setup.bash
colcon test --executor sequential --event-handlers console_direct+
colcon test-result --verbose
ldd install/usv_mpc_cpp/lib/usv_mpc_cpp/mpc_node | rg "not found" || true
```

所有测试通过且没有缺失动态库后，才能启动 systemd 服务。若本次发布没有修改 service 或 `/etc/default/usv-system`，不要覆盖它们。

## 10. G5：启动和台架验收

### 10.1 先验证方案 A

```bash
sudo usv-scheme A
systemctl status usv-system.service --no-pager
journalctl -u usv-system.service -n 150 --no-pager
```

检查：

- 服务为 `active (running)`，没有连续重启；
- 只有一个 MAVROS 实例；
- 飞控串口已连接，没有重复打开或权限错误；
- 方案 A 的运动学 MPC 节点和安全节点均存在；
- 飞控未解锁时推进器保持中性。

### 10.2 再验证方案 B

```bash
sudo usv-scheme B
systemctl status usv-system.service --no-pager
journalctl -u usv-system.service -n 200 --no-pager
```

方案 B 应确认：

- `backend=acados`；
- `dynamic_N=20`、`dynamic_dt=0.2` 与发布配置一致；
- 日志没有 acados/CasADi 动态库加载失败；
- 求解器状态正常，没有持续超时或连续失败；
- 推力锚点、左右推力命令和实测推力状态字段有合理值；
- VRX 内环坐标变换修正后的数据流没有重复旋转迹象。

### 10.3 ROS 图和话题

```bash
source /opt/ros/jazzy/setup.bash
source /home/trevor/usv_mpc_ws_B/install/setup.bash

ros2 node list
ros2 topic list
ros2 topic echo /mpc/status --once
ros2 topic hz /mavros/local_position/odom
ros2 topic hz /mavros/imu/data
```

实际话题名以 `topic_contract.md`、启动参数和 `ros2 topic list` 为准。检查关键传感器数据持续更新、时间戳新鲜、坐标系和 QoS 与节点订阅一致。

如需手工运行 `real.launch.py` 诊断，必须先停止 `usv-system.service`；诊断结束后退出全部手工节点，再恢复 systemd 服务。

### 10.4 遥测与远程链路

```bash
ss -ltnp | rg ":(8765|7865)"
journalctl -u usv-system.service -n 200 --no-pager | \
  rg -i "telemetry|bridge|frp|error|failed"
```

从岸站核对状态字段、MPC 参数和数据更新时间。树莓派监听端口、frp 转发端口和岸站连接端口必须完全一致。

## 11. 回滚计划

出现下列任一情况立即回滚：

- systemd 连续重启或服务无法保持 `active`；
- MAVROS 无法连接飞控或串口被争用；
- MPC/acados 动态库缺失；
- 方案 A 或 B 无法启动；
- 传感器话题中断、坐标系明显错误；
- 未解锁状态出现非中性推进器输出；
- 求解器持续失败、输出跳变或安全节点反复触发。

回滚步骤：

```bash
export DEPLOY_ID=20260912_mpc_update_01
sudo systemctl stop usv-system.service

mv "$HOME/usv_mpc_ws_B" \
  "$HOME/usv_backups/$DEPLOY_ID/usv_mpc_ws_B_failed"
mv "$HOME/usv_backups/$DEPLOY_ID/usv_mpc_ws_B_runtime" \
  "$HOME/usv_mpc_ws_B"

sudo cp -a "$HOME/usv_backups/$DEPLOY_ID/usv-system.default" \
  /etc/default/usv-system 2>/dev/null || true
sudo cp -a "$HOME/usv_backups/$DEPLOY_ID/usv-system.service" \
  /etc/systemd/system/usv-system.service 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl start usv-system.service

systemctl status usv-system.service --no-pager
journalctl -u usv-system.service -n 150 --no-pager
```

若采用的是完整复制备份而非 `usv_mpc_ws_B_runtime` 目录，回滚时从对应备份路径恢复。执行正式切换前必须根据实际采用的备份方式演练并修正这组路径。

## 12. G6：水试计划

台架验收全部通过后再安排水试：

1. 开阔、低风险水域，具备人工接管和紧急断电条件；
2. 首次只启用低速、短距离、简单直线路径；
3. 先验证方案 A，再验证方案 B；
4. 记录 rosbag、systemd 日志和岸站遥测；
5. 观察求解时间、状态误差、左右推力、饱和率、连续失败计数和安全接管；
6. 逐步增加曲率和速度，不在首次水试同时调整推进器辨识参数和 MPC 权重。

水试后将新数据与部署前基线对比，确认 VRX 内环坐标修正没有引入符号反转、航向振荡或横向误差增大。

## 13. 发布记录模板

每次迁移复制并填写一份记录：

```text
部署编号：
部署日期/执行人：
开发机提交 SHA：
Git 标签或源码归档 SHA-256：
工作树是否干净：

树莓派主机/架构：
Ubuntu 版本：
ROS 发行版：
Python 版本：
acados 版本/提交：
CasADi 版本：

正式工作空间：/home/trevor/usv_mpc_ws_B
备份路径：
systemd 服务文件校验值：
/etc/default/usv-system 校验值：

实际飞控串口和波特率：
实际遥测监听端口：
实际 RC 输入通道：
实际 SERVO 输出映射：

开发机 colcon build/test：通过/失败
树莓派预发布 build/test：通过/失败
树莓派正式目录 build/test：通过/失败
方案 A 台架：通过/失败
方案 B 台架：通过/失败
遥测链路：通过/失败
水试：通过/失败/未执行

异常、处置和回滚情况：
```

## 14. 执行清单

### 发布前

- [ ] 确认本次发布文件范围；
- [ ] 生成提交 SHA/标签或归档校验值；
- [ ] 开发机 6 包完整构建和测试通过；
- [ ] acados 生成代码与 OCP 配置一致；
- [ ] 补齐或记录真实艇运行依赖；
- [ ] 核实串口 `/dev/ttyAMA0` 与 `/dev/ttyAMA10` 的实际值；
- [ ] 核实遥测端口 `8765` 与 `7865` 的实际值；
- [ ] 确认磁盘空间、SSH 和物理应急登录可用；
- [ ] 准备固定部署编号和发布记录。

### 树莓派预发布

- [ ] 源码传输到独立目录；
- [ ] 未传输 x86 `build/install/log` 或动态库；
- [ ] ROS、Python、acados、CasADi 版本已记录；
- [ ] `rosdep check` 已通过或例外已记录；
- [ ] AArch64 原生构建和测试通过；
- [ ] `ldd` 没有 `not found`。

### 正式切换

- [ ] 船体和推进器处于安全状态；
- [ ] 停止 systemd 且无残留 MAVROS/控制节点；
- [ ] 当前工作空间和服务配置已备份；
- [ ] 正式路径完成干净构建与测试；
- [ ] 方案 A 启动和台架检查通过；
- [ ] 方案 B 启动和台架检查通过；
- [ ] 关键 ROS 话题、飞控链路和遥测正常；
- [ ] 回滚路径保持完整；
- [ ] 发布记录已归档且不含密码。

