# Jetson Orin 迁移执行记录

> 状态：G0/G1 已完成；本文件记录检查结果、Git 发布规则和后续放行门禁。

## 1. 范围和目标

目标是在 Jetson Orin 上部署真实艇运行所需的 ROS 2 工作空间。运行时只需要以下 6 个包：

- `usv_bringup`
- `usv_mpc_cpp`
- `usv_mpc_kinematic_cpp`
- `usv_planning_cpp`
- `usv_safety_cpp`
- `usv_simulation`（当前同时包含遥测桥和 VRX 辅助代码）

VRX/Gazebo、ArduPilot SITL、参数辨识数据和 rosbag 保留在开发机，不作为 Orin 运行时输入。

推荐目标基线：JetPack 7.x 对应的 Ubuntu 24.04 + ROS 2 Jazzy + AArch64 原生构建。具体 Jetson 型号、载板和外设驱动确认前，不执行刷机或正式部署。

## 2. G0 目标机只读清单

在 Orin 上执行：

```bash
bash usv_mpc_ws/scripts/orin_inventory.sh
```

重点记录：

| 项目 | 必须记录 |
|---|---|
| 硬件 | Orin Nano/NX/AGX、内存、载板、启动介质 |
| 系统 | JetPack/L4T、Ubuntu、Kernel、架构 |
| ROS | `ROS_DISTRO`、RMW 实现、已安装的 MAVROS |
| 计算 | Python、GCC、CUDA/TensorRT（若后续接入视觉） |
| 通信 | `/dev/ttyTHS*`、`/dev/ttyUSB*`、`/dev/serial/by-id/*`、网卡名 |
| 存储 | 根分区、日志盘、外接 bag 盘剩余空间 |
| 服务 | 当前 systemd 服务、运行用户、环境文件和启动目录 |

串口不假定为 `/dev/ttyAMA10`；优先使用 udev 固定别名 `/dev/usv-fcu`，并确认 3.3 V 电平、console 占用、`dialout` 权限和 921600 波特率。

## 3. G1 当前 Git 基线

首次记录时间：2026-09-17

```text
仓库：/home/trevor/USV
当前提交：cbf3f9e
本地 remote-tracking：origin/main = 6620d3e
原始分支：main；当前工作分支：codex/jetson-orin-port
工作树：不干净，包含算法、配置、文档、删除项和未跟踪文件
```

当前工作树必须先备份，再按功能拆分提交到迁移分支；不得直接在 `main` 上做 Jetson 现场修改。

本轮已完成的开发机侧动作：

- 创建本地分支 `codex/jetson-orin-port`；
- 创建并验证 Git 全历史 bundle、工作树补丁、索引补丁和未跟踪文件归档；
- 将 `usv_mpc_ws/CMakeFiles/`、`usv_mpc_ws/artifacts/` 和本地备份目录加入忽略规则；
- 运行 `git diff --check` 和 `orin_inventory.sh`，结果通过；
- 目标 Orin 尚未连接，JetPack、Ubuntu、ROS、串口和载板信息仍待 G0 现场采集。

### 3.1 安全备份

在开发机执行以下命令。备份目录已加入 `.gitignore`，不会进入发布内容：

```bash
set -e
BACKUP_ID="jetson-orin-20260917"
BACKUP_DIR="/home/trevor/USV/.local-backups/${BACKUP_ID}"
mkdir -p "${BACKUP_DIR}"

git status --short > "${BACKUP_DIR}/status.txt"
git diff --binary HEAD > "${BACKUP_DIR}/working-tree.patch"
git diff --cached --binary > "${BACKUP_DIR}/index.patch"
git ls-files --others --exclude-standard > "${BACKUP_DIR}/untracked.txt"
git show-ref > "${BACKUP_DIR}/refs.txt"
git rev-parse HEAD > "${BACKUP_DIR}/HEAD"
git bundle create "${BACKUP_DIR}/usv-history.bundle" --all
git bundle verify "${BACKUP_DIR}/usv-history.bundle"
find "${BACKUP_DIR}" -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
  | sort -z | xargs -0 sha256sum > "${BACKUP_DIR}/SHA256SUMS"
```

不要把 `data/`、`ardurover-argus/`、`build/`、`install/`、`log/` 或本地密码文件打包进发布快照；如需保留实验数据，单独备份到数据盘。

### 3.2 Git 清理顺序

1. 从当前提交创建 `codex/jetson-orin-port` 分支；保留现有未提交修改，不执行 reset 或 checkout。
2. 将当前修改拆成“算法/配置”“构建依赖”“部署脚本”“文档”几个逻辑提交。
3. 在推送前清理 `ntrip_params.yaml` 的未推送历史，并更换曾经使用过的 NTRIP 凭据。仓库只保留 `ntrip_params.yaml.example`。
4. 补充 `CMakeFiles/`、仿真 artifacts 等忽略规则，并确认 `git diff --check`、秘密扫描和 `git status` 结果。
5. 通过 CI 后创建不可变标签，例如 `orin-v0.1.0`；Orin 只部署标签，不跟踪 `main`。

本轮提交只包含迁移记录、Orin 清单脚本和 Git 忽略规则；算法、仿真和其他未提交改动保持在本地，不混入迁移提交。

## 4. 后续放行门禁

### G2 代码可移植性

- 参数化 FCU 串口、acados、CasADi 和配置目录；移除 `~/.local`、Python 3.12 等硬编码。
- 修复 `package.xml` 与 `CMakeLists.txt` 的依赖闭环，优先处理 `rclcpp_components`、Python3、Eigen、nlohmann-json、yaml-cpp 和 acados/CasADi 探测。
- 将遥测桥与 VRX/Gazebo 依赖解耦，避免 Orin 安装完整仿真栈。
- 添加 systemd unit、udev 规则、环境模板、部署脚本和健康检查脚本。

### G3/G4 Orin 构建和部署

- Orin 本机编译 acados v0.5.4，禁止复制开发机 `.so`。
- 安装锁定版 CasADi，使用 Release、低并行度 `colcon build`。
- `colcon test`、`colcon test-result --verbose` 全部通过。
- `file` 确认 ELF 为 AArch64，`ldd` 无 `not found`。
- 版本目录部署，`current` 软链接切换；保留至少一个上一版本用于回滚。

### G5/G6 台架和水试

- 断桨/断电/未解锁状态验证 MAVROS、odom、IMU、电池、任务、MPC 和安全节点。
- 方案 A、方案 B 分别启动，确认求解器后端、周期、推力输出和安全接管。
- 验证串口断开、定位超时、网络断开、重启自动恢复和温度降频。
- 低速、短距离、人工可接管条件下进行首次水试，并保存 Git SHA、系统日志和 rosbag。
