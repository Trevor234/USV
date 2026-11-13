# 树莓派 5 部署配置

本目录存放**不在 ROS 包内、但实机运行必需**的配置。原先它们只存在于
Pi 的文件系统里（`/etc/systemd/system/` 与 `~/.ros/`），重装时必须靠人工
回忆重建。2026-10-21 审查后纳入版本控制。

## systemd/

| 文件 | 部署位置 | 说明 |
|---|---|---|
| `usv-system.service` | `/etc/systemd/system/` | 控制系统（方案 A/B 由 `/etc/default/usv-system` 的 `SCHEME` 切换） |
| `usv-record.service` | `/etc/systemd/system/` | rosbag2 录制，独立服务，**刻意不依赖** usv-system |
| `usv-system.default` | `/etc/default/usv-system` | `SCHEME=A` |
| `usv-system.service.d/20-release.conf` | `/etc/systemd/system/usv-system.service.d/` | 仅把 `ExecStart` 的 workspace install 换成运行时软链 `usv_runtime` |
| `usv-record.service.d/20-release.conf` | `/etc/systemd/system/usv-record.service.d/` | 同上，录制入口 |
| `usv-rtk.service.d/20-release.conf` | `/etc/systemd/system/usv-rtk.service.d/` | 同上，RTK 入口（base unit 仅存在于 Pi，本 drop-in 只覆盖 ExecStart） |

### 关键设计约束（改动前务必读）

**usv-record 不能加 `Requires=`/`BindsTo=` usv-system**
：录制属于旁挂功能，不能因为录制失败反过来拖死控制栈。

**usv-record 不能加 `RequiresMountsFor=/mnt/usv_bags`**
：会绕过 fstab 的 `x-systemd.automount` 惰性挂载，在开机时强制真实挂载，
与 USB 冷插枚举（实测 13~17s）竞速；而 `Restart=` 对 dependency 失败无效，
服务将永不启动（2026-10-06 定位）。挂载等待放在 `ExecStartPre` 里触发
automount，失败由 `Restart=always` 兜底。

**录制不通过 `real.launch.py record:=true` 启动**
：早期这样做会连带拉起第二套 mavros，与 usv-system 抢 `/dev/ttyAMA10`
串口，导致 MAVLink 帧损坏。

## ros/

| 文件 | 部署位置 | 说明 |
|---|---|---|
| `fastdds_lan.xml` | `~/.ros/` | DDS 只走 lo + eth0，排除 wwan0（5G）。否则 wwan0 的 10.x/8 地址会被 FastDDS 通告为回程单播定位符，数据发进蜂窝口黑洞 |
| `mcap_realtime.yaml` | `~/.ros/` | MCAP `noChunking` 实时落盘。默认 zstd_fast 有 768KB chunk 缓冲，700B/s 下要 18 分钟才 flush，断电丢数据 |

### 部署命令（首次装机，旧工作空间入口）

```bash
sudo cp deploy/systemd/usv-system.service deploy/systemd/usv-record.service \
        /etc/systemd/system/
sudo cp deploy/systemd/usv-system.default /etc/default/usv-system
sudo systemctl daemon-reload

mkdir -p ~/.ros
cp deploy/ros/fastdds_lan.xml deploy/ros/mcap_realtime.yaml ~/.ros/
```

⚠️ **版本化部署（下文第 1~6 节）不再使用上面的 workspace 入口。**
`/etc/default/usv-system` 里当前的 `SCHEME` 是实船状态（现为 `B`），
**禁止**用仓库中的 `usv-system.default`（`SCHEME=A`）覆盖它。

## 版本化 Release 构建与切换（2026-11-12 起）

目标：同一份冻结源码产出 NoOpt 与 Release 两套构建，实测对照后由
`/home/trevor/usv_runtime` 软链决定实际运行哪一套，且运行身份可取证。

固定目录布局（`$R=/home/trevor/usv_releases/<RELEASE_ID>`）：

```
$R/src                冻结源码（六包 + deploy 工具，含 untracked 文件）
$R/source_git.txt     冻结时的 git HEAD 与限定范围 dirty/diff 清单
$R/build_noopt        Debug + -O0 -g 构建目录（不搬移）
$R/install_noopt      非优化安装树 = 首次切换与 Release 回退目标
$R/log_noopt          colcon 日志
$R/build_release      Release 构建目录
$R/install_release    Release 安装树
$R/log_release        colcon 日志
$R/evidence           身份 JSON、基准原始数据、对照报告、测试结果
$R/deploy             冻结的部署工具（本目录副本）
```

### 1. 冻结源码

```bash
export RELEASE_ID=pi5-$(date -u +%Y%m%dT%H%M%SZ)-<源码哈希前12位>
export R=/home/trevor/usv_releases/$RELEASE_ID
test ! -e "$R" || { echo "候选目录已存在, 换 RELEASE_ID"; exit 1; }
mkdir -p "$R"/{src,evidence}
rsync -a --exclude .git --exclude build --exclude install --exclude log \
      /home/trevor/usv_mpc_ws/src/ "$R/src/"
rsync -a /home/trevor/usv_mpc_ws/deploy/ "$R/deploy/"
rsync -a /home/trevor/usv_mpc_ws/docs/deploy_records/ "$R/docs_deploy_records/"
{
  echo "HEAD $(git -C /home/trevor/usv_mpc_ws rev-parse HEAD)"
  git -C /home/trevor/usv_mpc_ws status --porcelain -- src deploy docs
  echo "--- diff stat"
  git -C /home/trevor/usv_mpc_ws diff --stat -- src deploy docs
} > "$R/source_git.txt"
# 复制前后各枚举一次文件清单与 SHA-256, 不一致则候选无效
(cd "$R/src" && find . -type f -printf '%p %s ' -exec sha256sum {} \; | sort) \
  > "$R/evidence/source_manifest_release.txt"
```

`RELEASE_ID` 里的源码哈希取冻结后 `src/` 的文件清单摘要（内容 + 路径 + 大小），
Git HEAD 只作附加信息 —— 改名后的新包在 `git status` 里仍是 untracked，
`git archive HEAD` 会漏掉它们。

### 2. 双变体干净构建

每个变体独立子 shell，只 source `/opt/ros/jazzy/setup.bash`，不继承旧工作空间的
AMENT/CMAKE/LD overlay；`CMAKE_BUILD_PARALLEL_LEVEL=2`，顺序构建，不并行。

```bash
colcon --log-base "$R/log_noopt" build \
  --base-paths "$R/src" --build-base "$R/build_noopt" \
  --install-base "$R/install_noopt" --executor sequential \
  --packages-select usv_acados usv_mpc usv_nmpc usv_safety usv_planning usv_bringup \
  --cmake-args -DCMAKE_BUILD_TYPE=Debug \
  "-DCMAKE_C_FLAGS_DEBUG=-O0 -g" "-DCMAKE_CXX_FLAGS_DEBUG=-O0 -g" \
  -DBUILD_TESTING=ON -DUSV_BUILD_BASELINE_BENCHMARK=ON \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

colcon --log-base "$R/log_release" build \
  --base-paths "$R/src" --build-base "$R/build_release" \
  --install-base "$R/install_release" --executor sequential \
  --packages-select usv_acados usv_mpc usv_nmpc usv_safety usv_planning usv_bringup \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DUSV_BUILD_BASELINE_BENCHMARK=ON \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

构建后按各自 build base 跑测试并留存：

```bash
colcon --log-base "$R/log_noopt" test \
  --base-paths "$R/src" --build-base "$R/build_noopt" \
  --install-base "$R/install_noopt" --executor sequential \
  --packages-select usv_acados usv_mpc usv_nmpc usv_safety usv_planning usv_bringup \
  --event-handlers console_direct+
colcon test-result --verbose --test-result-base "$R/build_noopt"
```

Release 变体把 `noopt` 换成 `release`。两个变体的实际测试数量与结果写进发布记录，
不能用历史通过替代。

静态身份（必须在切换前生成，`identity_ok` 必须为 true）：

```bash
python3 deploy/capture_release_identity.py static \
  --release-root "$R" --variant release --output "$R/evidence/identity_release.json"
python3 deploy/capture_release_identity.py static \
  --release-root "$R" --variant noopt --output "$R/evidence/identity_noopt.json"
```

### 3. 基准对照

```bash
python3 -m unittest discover -s deploy/tests -v
# 唯一验收入口: 采集全部数值/耗时/迁移证据 (固定 CPU 亲和、线程数 1、
# 起止实时节流读数, 顺序固定 N->R->R->N 与 Old->New->New->Old)
#
# 每个 benchmark 进程前后各记三组证据, 任一变化即该段无效:
#   1) 实时环境: 起始温度 <=60 °C、governor=performance、throttled=0x0、boot_id;
#   2) 生产服务只读快照: usv-system active 且 MainPID/NRestarts 不变,
#      usv-record / usv-rtk 保持 inactive;
#   3) 产物哈希: benchmark 可执行文件、共用后端库、OCP JSON、参数文件、
#      冻结源码清单 (旧 B 二进制另核对固定 SHA)。
# `production_service_untouched` 由上述快照推导, 不是写死的断言。
#
# get_throttled 需要 /dev/vcio (root:video)。普通用户下必须让 runner 能从
# 密码文件经 sudo -S 读取: 用 `sudo -S` 起 runner 最直接;
# 否则设 USV_SUDO_PASSWORD_FILE=<文件> (密码只经 stdin, 不落盘不进证据)。
sudo -S python3 deploy/run_release_baseline.py \
  --release-root "$R" --reference-root "$R0"

# 同算法 NoOpt/Release 对照 (只比同一算法, 不跨算法)
python3 deploy/compare_release_baseline.py \
  --noopt "$R/evidence/bench/noopt" --release "$R/evidence/bench/release" \
  --output "$R/evidence/bench/comparison"

# 算法迁移对照 (旧 IPOPT A + 原 B -> 共用 acados 后端)
python3 deploy/compare_acados_migration.py \
  --reference-root "$R0" --candidate-root "$R" \
  --output "$R/evidence/migration/comparison"
```

两个方案现在都是 acados 后端，求解器预算烘焙在生成码里：`check_acados_profile`
从 runner 写入的 `provenance` 绑定 OCP JSON，核对 `nlp_solver_type`
(A: SQP+MERIT_BACKTRACKING / B: SQP_RTI)、迭代/超时、`cost_scaling`
(A: ones, B: [dt...,1])。缺 provenance 或字段不符一律失败。

迁移对照额外要求：A 重放旧 IPOPT 输入 (1e-12 同源)、独立重算四残差、
`acados_cost` 与解析目标 1e-8 相对一致、目标不劣于旧参照 1%+0.01、
200 拍闭环位置/航向 RMSE 门禁、Release p95<=20ms/p99<=50ms；B 抽取前后
逐元素回归 + 同轮 p95 退化门禁。

`comparison.json` 的 `ok` 必须为 true，`comparison.md` 是中文对照表。
四份报告与原始 JSON 一起归档。

### 4. 首次切换：非优化版成为可信回退目标

前提：船固定、未解锁、推进器动力物理隔离、无航行任务；近 60 s 无新 odom/命令。

```bash
# 快照 (不动服务状态)
systemctl is-active usv-system usv-record usv-rtk
systemctl show usv-system -p NRestarts -p ExecStart --no-pager
cat /etc/default/usv-system
```

切换顺序（**只**恢复快照里原本 active 的服务）：

```bash
sudo systemctl stop usv-system            # 若 usv-record 在跑, 先停它
sudo ln -sfn "$R/install_noopt" /home/trevor/usv_runtime
sudo install -d /etc/systemd/system/usv-system.service.d \
                /etc/systemd/system/usv-record.service.d \
                /etc/systemd/system/usv-rtk.service.d
sudo install -m 644 deploy/systemd/usv-system.service.d/20-release.conf \
  /etc/systemd/system/usv-system.service.d/
sudo install -m 644 deploy/systemd/usv-record.service.d/20-release.conf \
  /etc/systemd/system/usv-record.service.d/
sudo install -m 644 deploy/systemd/usv-rtk.service.d/20-release.conf \
  /etc/systemd/system/usv-rtk.service.d/
sudo install -m 755 deploy/usv-scheme /usr/local/bin/usv-scheme
sudo systemctl daemon-reload
sudo systemctl start usv-system
```

验收（连续观察 ≥60 s，两次快照对比）：

```bash
python3 deploy/capture_release_identity.py runtime \
  --expected-install /home/trevor/usv_runtime \
  --output "$R/evidence/runtime_noopt_t0.json"
sleep 60
python3 deploy/capture_release_identity.py runtime \
  --expected-install /home/trevor/usv_runtime \
  --baseline "$R/evidence/runtime_noopt_t0.json" \
  --output "$R/evidence/runtime_noopt_t60.json"
```

`identity_ok` 必须为 true：控制器 ELF 落在 `install_noopt`、无 `(deleted)`、
后端 acados、参数与安装配置一致、只有一个 MAVROS 且只有它持有串口、
`usv-record`/`usv-rtk` 保持 inactive、`NRestarts` 未增加。
首次切换失败即安全停机，**不**承诺恢复已被删除的旧控制器。

### 5. 切换 Release

只有 NoOpt 验收通过 **且** 第 3 节对照通过才可执行：

```bash
sudo systemctl stop usv-system
sudo ln -sfn "$R/install_release" /home/trevor/usv_runtime
sudo systemctl start usv-system
# 同样的 t0 / t60 两次 runtime 取证, 期望 install_release 路径 + install_release ELF 哈希
```

`SCHEME` 不变，不覆盖旧工作空间 `install/`，不重命名版本目录。

### 6. 回退

```bash
sudo systemctl stop usv-system
sudo ln -sfn "$R/install_noopt" /home/trevor/usv_runtime
sudo systemctl start usv-system
python3 deploy/capture_release_identity.py runtime \
  --expected-install /home/trevor/usv_runtime --output "$R/evidence/runtime_rollback.json"
```

回退目标必须是**已实际验收过**的 NoOpt 安装树。回退本身失败则保持控制停止，
不循环盲目重启；旧工作空间的 `(deleted)` 进程不可复活。
`usv-record`/`usv-rtk` 的 active 状态按切换前快照恢复，不擅自启用。

### 未覆盖范围（每次发布都要重述）

- 只改构建优化与部署身份，不改 NMPC 控制逻辑、执行器映射、预测模型与飞控参数；
- 不验证 5 Hz ACTIVE 闭环周期、实船跟踪效果、推力输出 —— 需要新鲜 odom/路径与
  水面试验；
- 服务重启不等于开机自启验证；整机重启后的自启行为需另行确认；
- 方案 A 与 B 都只有 acados 后端，`--backend casadi` 会明确报错；
  方案 A 不再链接/import CasADi (只保留离线 codegen 用途)。
- 隔离烟测 `deploy/smoke_a_node.py` 只在本机 ROS_DOMAIN_ID 213/214/215 的
  空域里跑独立 A 节点, 不接飞控; 它不等于实船验证。该 harness 与节点必须
  落在同一个 domain (父进程也设 ROS_DOMAIN_ID), 且本机实测
  `ROS_LOCALHOST_ONLY=1` 会让 discovery 完全失效, 因此隔离只靠独立 domain +
  `/migration/smoke` 命名空间。`--acados-lib-dir` 用于给直接 exec 的节点补
  acados/hpipm/blasfeo 的 LD 路径 (launch 文件在正式部署里负责这件事)。

## 变更记录

- 2026-10-21：首次纳入版本控制（原仅存于 Pi 文件系统）
