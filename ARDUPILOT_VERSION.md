# ArduPilot 依赖版本

本项目依赖 ArduPilot 固件用于 Rover 仿真和 SITL 测试。

## 当前版本

- **仓库**: https://github.com/ArduPilot/ardupilot.git
- **版本标签**: `Plane-4.6.3`（同 commit 另有 `Rover-4.6.3`、`Tracker-4.6.3`，三个 tag 指向同一个提交）
- **Commit SHA**: `3fc7011a7d3dc047cbb17d8bd98ee94577d144c6`
- **分支**: `master`（仅用于 `git submodule update --remote` 跟踪；实际工作区 checkout 在 tag 上，处于 detached HEAD）

> **注意**：本项目跑的是 **ArduRover** 固件（`rover` SITL），核对参数与行为时请以 `Rover-4.6.3` 的文档为准。`Plane-4.6.3` 只是同一提交上的等价 tag，ArduCopter/ArduPlane 的参数表不适用。

## 管理方式

从 2026-01-12 开始，ArduPilot 已从嵌套仓库改为 **Git Submodule** 管理：

```bash
# 初始化和更新 submodule
git submodule update --init --recursive

# 切换到指定版本（首次克隆后需要执行）
cd ardurover-argus
git checkout Rover-4.6.3
```

## 符号链接

为保持向后兼容，项目根目录保留了 `ardupilot -> ardurover-argus` 符号链接。该链接**不被 git 跟踪**。

## 更新 ArduPilot 版本

如需升级到新的 ArduPilot 版本：

1. 进入 submodule 目录：
   ```bash
   cd ardurover-argus
   ```

2. 拉取最新标签并切换：
   ```bash
   git fetch --tags
   git checkout <new-tag>  # 例如 Rover-4.7.0（ArduPilot 会同时打 Plane/Copter/Rover/Tracker 的 tag，
                           # USV 请用 Rover-* 前缀的那个；同一提交的 tag 内容完全相同）
   ```

3. 返回主仓库，提交 submodule 变更：
   ```bash
   cd ..
   git add ardurover-argus
   git commit -m "chore: 升级 ArduPilot 到 <new-tag>"
   ```

4. 更新本文档的版本信息。

## 本地构建环境

ArduPilot 编译需要独立的 Python 虚拟环境：

- **venv 路径**: `/home/trevor/venv-ardupilot`
- **Python 版本**: 3.12.3
- **主要依赖**: numpy, scipy, matplotlib, pymavlink

详见 `usv_mpc_ws/docs/runbook.md` 中的 SITL 仿真章节。

## 注意事项

- **不要直接在 ardurover-argus 内提交修改**。这是上游 ArduPilot 的只读镜像。
- 如需自定义固件，应 fork ArduPilot 仓库，并修改 .gitmodules 中的远程地址。
- Pi5 实机部署**不需要** ArduPilot 源码，只需预编译的固件二进制文件。
