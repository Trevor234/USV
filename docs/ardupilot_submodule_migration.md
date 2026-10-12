# ArduPilot Submodule 迁移指南

## 变更概述

**日期**: 2026-01-12  
**提交**: db6d9fe

将 `ardurover-argus` 从嵌套独立仓库改为标准 Git submodule 管理。

## 变更内容

### 1. Git 配置
- 新增 [.gitmodules](../.gitmodules) 配置文件
- 将 `ardurover-argus/` 从 `.gitignore` 排除列表中移除
- ArduPilot 仓库现在作为 submodule 被主仓库跟踪

### 2. 版本锁定
- **ArduPilot 版本**: Plane-4.6.3
- **Commit SHA**: 3fc7011a7d3dc047cbb17d8bd98ee94577d144c6
- **远程仓库**: https://github.com/ArduPilot/ardupilot.git

### 3. 文档
- 新增 [ARDUPILOT_VERSION.md](../ARDUPILOT_VERSION.md) 说明依赖关系和更新流程

### 4. 向后兼容
- 保留符号链接 `ardupilot -> ardurover-argus`（未被 git 跟踪）

## 团队成员操作指南

### 新克隆仓库

```bash
# 克隆主仓库时自动初始化 submodule
git clone --recurse-submodules <repo-url>

# 或者先克隆，再初始化 submodule
git clone <repo-url>
cd USV
git submodule update --init --recursive

# 切换到锁定版本
cd ardurover-argus
git checkout Plane-4.6.3
```

### 已有本地仓库（迁移前克隆的）

**重要**: 在拉取这次变更前，需要先处理现有的 `ardurover-argus` 目录。

#### 方案 A：备份后重新初始化（推荐）

```bash
# 1. 备份当前的 ardurover-argus（如果有本地修改）
cd /home/trevor/USV
mv ardurover-argus ardurover-argus.backup

# 2. 拉取包含 submodule 配置的变更
git pull origin codex/scheme-c-rl  # 或你的分支名

# 3. 初始化 submodule
git submodule update --init --recursive

# 4. 切换到锁定版本
cd ardurover-argus
git checkout Plane-4.6.3

# 5. 如果备份中有本地修改，手动迁移
# （通常不需要，ArduPilot 是上游只读依赖）
```

#### 方案 B：就地转换

```bash
# 1. 确保 ardurover-argus 工作区干净
cd ardurover-argus
git status  # 应该没有未提交的修改

# 2. 回到主仓库
cd ..

# 3. 拉取变更
git pull origin codex/scheme-c-rl

# 4. 初始化 submodule（会识别现有目录）
git submodule update --init --recursive

# 5. 验证
git submodule status
# 输出应为：3fc7011a7d3dc047cbb17d8bd98ee94577d144c6 ardurover-argus (AION-Orca-Alpha2-20886-g3fc7011a7d)
```

### 切换分支

```bash
# 切换到包含 submodule 的分支后
git submodule update --init --recursive
```

### 更新 ArduPilot 版本（维护者操作）

```bash
# 1. 进入 submodule
cd ardurover-argus

# 2. 拉取最新标签
git fetch --tags

# 3. 切换到新版本
git checkout Plane-4.7.0  # 例如

# 4. 回到主仓库
cd ..

# 5. 提交 submodule 版本变更
git add ardurover-argus
git commit -m "chore: 升级 ArduPilot 到 Plane-4.7.0"

# 6. 更新 ARDUPILOT_VERSION.md 中的版本信息
```

## 验证清单

- [ ] `git submodule status` 显示正确的 commit SHA
- [ ] `cd ardurover-argus && git describe --tags` 显示 `Plane-4.6.3`
- [ ] 符号链接 `ardupilot` 指向 `ardurover-argus`
- [ ] SITL 仿真正常启动：`cd ardurover-argus/Tools/autotest && python sim_vehicle.py`

## 故障排查

### Submodule 目录为空

```bash
git submodule update --init --recursive
```

### Submodule 指向错误的 commit

```bash
cd ardurover-argus
git checkout Plane-4.6.3
cd ..
git submodule update --init --recursive
```

### 提示 "fatal: 无法添加子模组"

检查 `.gitignore` 是否仍然包含 `ardurover-argus/`（应该已被注释）。

### ArduPilot 内部 submodule 未初始化

```bash
cd ardurover-argus
git submodule update --init --recursive
```

## 参考资料

- [Git Submodule 官方文档](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
- [ARDUPILOT_VERSION.md](../ARDUPILOT_VERSION.md) - 依赖版本说明
- [ArduPilot 官方仓库](https://github.com/ArduPilot/ardupilot)

## 迁移理由

**原问题**：
- ardurover-argus 是嵌套的独立 git 仓库
- 主仓库无法跟踪 ArduPilot 的具体版本
- 团队成员克隆后可能得到不同版本的 ArduPilot
- 符号链接被主仓库跟踪，但目标目录未被跟踪

**改进后**：
- ✅ 主仓库明确记录依赖的 ArduPilot 版本（commit SHA）
- ✅ 团队成员使用 `git submodule update` 自动获取正确版本
- ✅ 标准的 Git 工作流，无需特殊处理
- ✅ 版本升级通过 git commit 可追溯
