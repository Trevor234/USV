# USV 仓库整改计划 v5

> 状态：**待批准**（批准后按 B→C→D→E 顺序执行，A 先行）
> 日期：2026-10-26
> 侦察基线：x86 `~/USV`（10.0.0.222）、树莓派 `~/usv_mpc_ws_B`（10.0.0.3）、GitHub `Trevor234/USV` 远端实际分支状态

---

## 0. 背景与目标

三端设备协作缺乏统一仓库结构：

| 设备 | 角色 | 现状 |
|---|---|---|
| x86 Ubuntu 主机（trevor-Vostro-5880） | 开发 + VRX/SITL 仿真 + RL 训练 | `~/USV`（1.3GB .git），当前 checkout 在 `codex/scheme-c-rl`，另有 16 文件未提交 |
| 树莓派 5（trevor-desktop） | 实船部署 A/B MPC | `~/usv_mpc_ws_B`，本地分支 `fix/safety-and-planning` @feb2e8c，另有 ③ 的 5 文件未提交 |
| Jetson Orin | 实船部署（未来 PPO 推理） | 差异在远端 `codex/jetson-orin-port` 分支，未评审 |

**目标**：单一稳定主线 + 每设备一个"部署预设"薄分支 + 实验分支隔离；配置目录化承载方案（A/B）与设备（pi5/orin/x86_sim）两个正交维度；仓库停止膨胀；三端部署与回退流程文档化。

---

## 1. 侦察事实（决策依据）

### 1.1 远端与本地分支全景

远端（GitHub `Trevor234/USV`）现存分支：

| 远端分支 | 提交 | 判定 |
|---|---|---|
| `main` | cbf3f9e | 集成基底（9 月以来 28 个独有提交：Python→C++ 全迁移、VRX 数字孪生、推力饱和修复等） |
| `codex/scheme-c-rl` | feb5082 | 实验线（47 独有提交），**改名为 exp/scheme-c-rl 保留** |
| `codex/jetson-orin-port` | 8edb443 | Orin 适配，评审后拆解合并，然后删除 |
| `pi5/fix-safety-planning` | feb2e8c | Pi 实机修复（5 独有提交），合入 main 后删除 |
| `pi5/workspace-20261021` | b505cc5 | Pi 工作区首导入快照，若被 main 包含则删除 |

### 1.2 三条线分叉关系（x86 实测）

```
10cf6891 (scheme-c-rl 的分叉基底，迁移前)
   ├──→ origin/main         独有 28 提交（含完整的 Python→C++ 重新迁移）
   │      └──(同基底另演化)→ pi5 线: b505cc5 ──→ feb2e8c (独有 5 提交)
   └──→ codex/scheme-c-rl   独有 47 提交（usv_rl + 平行的 C++ 迁移 + 契约/安全工作）
```

- **scheme-c-rl 与 main 的共享包差异：123 文件 / +31029 行 / −309 行**，且 grep 无任何构建开关（`USV_BUILD_RL` 类不存在）→ **git 无法直接 merge，毕业只能人工移植**。
- x86 工作区 16 个未提交文件（+158/−42）为契约/安全工作的延续，归属 scheme-c-rl 线。

### 1.3 仓库体积问题（Pi 慢链路的根因）

- `.git` = **1.3GB**；`vrx_ws`（378 文件，**150MB**）与 `usv_vrx_logs`（**15MB**）被 git 跟踪。
- `ardupilot` 为正规 submodule（gitlink），不初始化零成本 ✓。
- 树莓派经 WiFi fetch 该仓库长时间无进展，根因即此。

### 1.4 结构性好消息

- `usv_rl` 是独立顶层包（configs/docs/tests），**纯增量结构**，毕业移植时对现有 6 包零冲突。训练产物（`models/`、`runs/`）已于 2026-10-26 移到仓库顶层 `artifacts/rl_models|rl_runs/`（gitignore，仅 `artifacts/README.md` 被跟踪），因此 `usv_rl` 不再自带产物目录。
- 三端实跑代码相同（6 包跨 x86/ARM 可编译）；设备假设仅 3 处：mavros 串口 `fcu_url=/dev/ttyAMA10`、acados/casadi 库路径（real.launch.py 硬编码）、注释。
- CI **已删除**（原 `.github/workflows/usv_mpc_ci.yml`，2026-10-26）：该 workflow 自 2026-09-12 建立起即无法通过——`usv_mpc_cpp` 无条件编译 `acados_backend.cpp` 并 `#include <acados_c/...>`，而 CI 从未安装 acados；另有 PEP 668 阻断 pip、`usv_rl` 未安装等问题。reorg 完成、分支模型定型后按第 D 节重建。
- Pi 端 SSH 密钥已配好（Trevor234 账号认证通过）。

---

## 2. 目标分支模型（三层，各回答一个问题）

```
main                ← "什么是稳定的、三端共有的"      稳定共同主线
├── device/pi5      ← "每台设备部署哪个已验证版本"     薄预设分支 = main + 1 个预设提交(<10 行)
├── device/orin     │   预设提交只钉 launch 默认值(device:=/scheme:=)
├── device/x86      │
├── exp/scheme-c-rl ← "正在试验、未定型的东西"        厚实验分支(含 usv_rl PPO)
└── (毕业) exp → PR → main(带开关) → 验证后 merge 到 device/*
```

**纪律（写入 docs/branching.md）**：
1. 功能/修复只进 main；device/* 永不接功能提交；
2. device/* 相对 main 只允许一个预设提交；同步单向 main → device/*（实船验证后 merge，落后数个提交 = 已验证版本语义，验证点可加 `release/<device>-YYYY.MM` tag）；
3. 实验一律 exp/*；exp 分支改共享包必须加构建开关（CMake option 默认 OFF）或纯增量，否则不予毕业；
4. exp 毕业走 PR 进 main（开关默认关），绝不直接 merge 进 device/*。

---

## 3. 配置目录化（main 上，承载方案×设备两个正交维度）

```
usv_mpc_ws/src/usv_bringup/config/
├── common/              ← safety_params, path_config, topic_contract, bag_topics,
│                          rosbag_qos_overrides, waypoints/（原样迁移）
├── scheme_A/            ← mpc_params_A→mpc_params.yaml, usv_params_A→usv_params.yaml
├── scheme_B/            ← mpc_params_B→mpc_params.yaml, usv_params_B→usv_params.yaml
└── devices/
    ├── pi5/             ← mavros_config.yaml(fcu_url=/dev/ttyAMA10), ntrip_params.yaml,
    │                      env.yaml(新: acados/casadi 库路径，替代 launch 硬编码)
    ├── orin/            ← mavros_config.yaml, env.yaml（从 codex/jetson-orin-port 差异提取）
    └── x86_sim/         ← usv_params_sim.yaml, mpc_params_vrx→mpc_params_vrx_overlay.yaml,
                           mavros_config_sitl.yaml(新: 收拢 sitl.launch 覆盖参数)
```

- 归属原则：随**方案**变 → `scheme_*`；随**机器**变 → `devices/*`；其余 → `common/`。
- `real.launch.py` 增加 `device:=` 参数（默认值由 device/* 分支的预设提交钉住）；参数链 `scheme_* → devices/<device> → 显式参数`（ROS2 参数数组后覆盖前，天然 overlay）。
- 删除 `ntrip.launch.py.bak_rtk_20261009`；`test_config_smoke.py` 路径断言同步。
- 三端启动方式：Pi5/Orin `git clone -b device/pi5|orin && colcon build && ros2 launch usv_bringup real.launch.py`（无参数）；x86 `git clone -b device/x86`，vrx/sitl 直接起；实验时 x86 checkout exp/scheme-c-rl。
- 仓库边界：VRX/Gazebo/ArduPilot SITL 本体在仓库外；Pi 克隆得到的"多余内容"仅 x86 专属的 4 个 KB 级文本文件；6 个包三端都需要（Pi 实船在用 usv_simulation 的 visualizer/telemetry_bridge）。

---

## 4. 执行步骤

### A. 仓库瘦身（main 上，x86 执行，最先做）

1. `git rm -r --cached vrx_ws usv_vrx_logs`（文件保留在 x86 磁盘，加入 .gitignore）——控制仓库停止膨胀。
2. 历史重写（git filter-repo 压掉 1.3GB）列为**可选后续项**，本次不做；设备克隆一律浅克隆/bundle 绕开历史体积。

### B. 分支整合（x86 执行）

1. 以 origin/main(cbf3f9e) 为基底建集成分支 `integration/reorg-2026.10`。
2. 合入 pi5 线：merge `pi5/fix-safety-planning` 的 5 提交（冲突预计集中在 usv_safety_cpp/mpc_node，逐个按实测修复语义解决）；附加 ③ 的 5 文件提交（B 包参数默认值对齐实船 yaml + test_backend_consistency 容差修正，内容已有完整副本）。Pi 本地整合前先 `git add -A && git commit` 留快照。
3. scheme-c-rl 处置：`git branch -m codex/scheme-c-rl exp/scheme-c-rl`（本地+远端）；x86 未提交的 16 文件逐 diff 确认后收拢为一个提交放到该分支。**不合入 main**。
4. `codex/jetson-orin-port` 评审（`git diff main...codex/jetson-orin-port`）→ 共同改动进集成分支、设备差异进 `devices/orin/` → 建 `device/orin`；原分支删除。
5. 建 `device/pi5`、`device/x86` 薄预设分支。
6. 远端清理（每个删除前先 `git tag backup/<branch>@<sha>`）：删 `pi5/workspace-20261021`（若已被包含）、`pi5/fix-safety-planning`、`codex/jetson-orin-port`。
7. 集成分支验证通过后 merge 回 main，推送。**最终远端 = main + device/{pi5,orin,x86} + exp/scheme-c-rl**。

### C. 配置目录化（集成分支上）

按第 3 节矩阵 `git mv` + launch 改造 + smoke 测试路径同步。

### D. 文档与 CI

- `docs/branching.md`：三层模型 + 第 2 节纪律 + 同步/毕业流程。
- `docs/devices.md`：设备×方案矩阵、每端部署/验证步骤、回退方法。
- 迁入 `docs/pi5_deploy.md`（现被 `regenerate_acados_codegen.py` 引用却不在仓库）。
- **重建** `.github/workflows/usv_mpc_ci.yml`（原文件已于 2026-10-26 删除，原因见 §1.4）：main 与 device/* 触发 colcon build+test（4 个 C++ 包 + config smoke；usv_rl 若无开关默认不构建）；存量 lint（cpplint/uncrustify）只跑不阻塞。重建时必须解决三个前置：① CI 内从源码装 acados（或给 `usv_mpc_cpp` 加 `BUILD_ACADOS_BACKEND` 开关，关掉时排除 `acados_backend.cpp`）；② 用 venv 或 `--break-system-packages` 绕开 noble 的 PEP 668；③ `pip install -e ../usv_rl` 并装 onnxruntime，否则 `usv_rl_ros` 的 pytest 采集即失败；另需为不属于任何 colcon 包的 `scripts/tests`（P0 契约 177 例）单列 pytest 步骤。
- GitHub main 与 device/* 分支保护：给出网页勾选清单，由用户操作。

### E. 三端落地与验证

- **x86**（助手执行）：整改本体 + 全量 build/test + vrx/sitl 冒烟 → 推进 `device/x86`；重新 checkout `exp/scheme-c-rl` 恢复实验现场。
- **Pi5**（助手执行）：x86 上 `git bundle`（浅历史）→ 局域网 scp 直传 → checkout `device/pi5` → colcon build → gtest 全跑 → `ros2 launch usv_bringup real.launch.py` 冒烟；旧 `usv_mpc_ws_B` 转归档（staging/backups 清理先经用户确认）；设置全局 git identity。
- **Orin**（用户操作或提供 SSH）：checkout `device/orin`，同 Pi 流程。

### F. 回退与风险

- 每步操作前打 `backup/<name>@<sha>` tag；设备回退 = `git reset --hard <验证点>` 或 checkout release tag。
- 风险清单：
  1. pi5fix 与 main 的 merge 冲突量未知（两线各自改过 usv_safety_cpp）——逐文件按实测语义裁决；
  2. orin 分支内容未评审，可能混有实验内容——拆解合并；
  3. scheme-c-rl 毕业移植工作量大（123 文件/+31k 行）——已隔离为 exp 分支，不阻塞本次整改；
  4. 分支纪律若被破坏（直接在 device/* 提交功能）会重演漂移——docs + 分支保护缓解。

---

## 5. 分工

| 事项 | 责任 |
|---|---|
| A–D 全部执行、Pi 侧 E、整合报告 | 助手（经 x86 SSH + Pi SSH） |
| GitHub 网页分支保护 | 用户（按提供的勾选清单） |
| Pi 旧备份/staging 清理确认 | 用户 |
| Orin 落地（或提供 SSH 由助手执行） | 用户/助手 |

## 6. 验收标准

1. 远端分支集合 = `main + device/{pi5,orin,x86} + exp/scheme-c-rl`，无杂草分支；
2. main 上 `colcon build + colcon test` 全绿（A/B 两套 gtest）；
3. 任一设备可按 docs/devices.md 三条命令内完成部署；回退一条命令；
4. vrx_ws / usv_vrx_logs 不再被跟踪，仓库新增提交体积正常；
5. 三端各自分支上的工作互不可见性符合预期（Pi/Orin 看不到 usv_rl，x86 device 分支无实船串口配置干扰）。顶层 `artifacts/` 同理：被 gitignore，不进任何分支。
