# 方案 A：Ubuntu Codex 交接与全面推进计划

交接日期：2026-10-10，Asia/Shanghai。目标主机：`192.168.1.222`，用户 `trevor`。项目根：`/home/trevor/USV`。本文件不含连接密码或 NTRIP 认证配置原文。

Ubuntu 交接目录：`/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01`。主交接文件、关键方案/状态的原字节副本、技能阅读参考和文件清单放在一起；不是软件重新部署，也没有覆盖任何基线、实验、源码或安装目录。

## 1. 新会话先读这一页

**当前应从 P1 的“owned 端点归属与有效配置认证”接续。** 独立求解、固定 tick 监管、有界队列和大量影子工程机制已实现并做过有限验证；最新启动握手组件也已验证，但完整准备/关闭、真实 Source→bag storage→Witness 正链、有效动态域和最终统一版本资格仍未闭合。现在不是开始 GP 训练、PPO 重训、静态障碍避碰批量试验或新监管器物理接管的时点。

方案 A 的研究目标是：**在线残差模型切换时，已验证备份的执行一致性、数据年龄与有效期管理**。第一轮以单船、欠驱动 USV、有限已知模型、明确的输入/观测误差和静态障碍范围为对象，研究模型切换、超时和备份接续能否使用一致有效条件，并在相同计算资源下减少迟到/过期执行，同时保留任务进度。

名称必须区分：

| 名称 | 本项目的含义 |
|---|---|
| 研究“方案 A” | 本交接的研究方向；首先复用动态 NMPC。 |
| 仓库 `scheme=A/B/C` | 分别为运动学 MPC、动态 NMPC、PPO。**研究 A 使用 `scheme=B`**，不要误启动运动学 A，也不要把 B/PPO 串入 `cmdvel_to_thrust` 速度内环。 |
| 近期 P1 的 D0/D1 | 来源观察、启动和生产准备链工作包。 |
| 论文研究实验 D0/D1/D2 | 分别为固定物理宽界下均值切换、年龄/漂移、动作保持/执行器实验。尚未完成。 |
| P1 的 B0～B5 | 合同、诊断、正常对照、压力、来源、冻结等工程阶段门。 |
| 论文对照 B0～B4 | 后文的基线方法；不能用同编号的工程测试通过替代研究比较。 |

**当前资格：D1、B4/B5、M0b 正式冻结、M4、F6、P1 整体及 execute 均未闭合。** 某个子项已验收不等于整个阶段完成。P2～P5 没有完成阶段实现/验收；认证备份、GP 合格数据、学习缩界、递归可行性和概率避碰结论均未取得。

先读交接目录 `source_docs` 下这五份材料：

1. `首选A_现有ROS平台可行性与实施方案_2026-10-03.md`：研究定位、P0～P5、假设、对照和理论边界。
2. `P1_M0b_B4_D1_启动握手组件_实施与验收_2026-10-09.md` 与同名“状态”JSON：最新启动组件与尚未完成的全链条件。
3. `P1_M0b_B4_D1_owned端点与配置认证_最小计划_2026-10-09.md`：下一最小工作包。
4. `P1_剩余环境差异_最小修复与验证记录_2026-10-10.md` 及修复审计 JSON：最新环境变化处置和辅助资产版本。
5. `startup_handshake_build_manifest_v1.json`：publisher、observer、Worker、合同与 checker 的精确版本关系。

原主方案、P1 总进展和部分历史状态中仍有“25 项差异”、旧 worker/regulator 版本及旧“下一步”。**10 月 10 日修复记录更新为 26 项；其余阶段资格按 10 月 9 日最新启动状态继承。** 不编辑历史 JSON 来使它们看起来同步；按证据日期、源码/二进制/合同 SHA 和适用范围判定。

## 2. 平台和资产在哪里

| 用途 | Ubuntu 实际位置或当前事实 |
|---|---|
| 项目及 Git 根 | `/home/trevor/USV` |
| ROS2 工作空间 | `/home/trevor/USV/usv_mpc_ws` |
| VRX 工作空间 | `/home/trevor/USV/vrx_ws` |
| PPO 训练/导出项目 | `/home/trevor/USV/usv_rl` |
| ROS/P1 常用 Python | `/usr/bin/python3`；ROS Jazzy |
| PPO 虚拟环境 | `/home/trevor/USV/usv_rl/.venv/bin/python`；路径已确认存在，仍须核对该环境实际依赖。不要只看它最终解析到系统 Python 就认为虚拟环境相同。 |
| 当前 Git 分支与 HEAD | 本轮只读确认 `codex/scheme-c-rl`、`1e5becae622782526f20fc93928339133c94ec23`；工作区有未提交修改。HEAD 不能代表已部署修复版本。 |
| F5 原冻结基线 | `/home/trevor/USV/.sgh-research/baselines/F5_20261005_atomic_freeze_01` |
| P1 实验与版本根 | `/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01` |
| 最新启动组件隔离根 | 上述实验根下 `authored_D1_startup_handshake_20261009_v1` |
| 10 月 10 日修复与备份 | `/home/trevor/USV/.sgh-research/repairs/remaining_drift_20261010_01` |
| 原始 bag | `/home/trevor/USV/data/sim_bags`；不要把旧缺失动作的 bag 补写成新数据。 |

本轮在北京时间约 15:47～15:49 只读确认目录、Git 身份、关键源码/二进制和清单 SHA；没有重新运行所有历史测试、整套资产扫描或业务进程审计。历史动态结果均有自己的日期和运行身份。新会话第一次启动前仍须检查 boot、进程、ROS domain、实际链接、配置和源码/安装产物。

最小继承身份：

| 资产 | 固定 SHA256 |
|---|---|
| 原 3864 项清单 `D1_prerequisite_closed_assets_20261009.json` | `27df4957d21c29a9d724bc97a1221f0fee814d99d53f9f7be041b1e23a7124a0` |
| 启动组件 scoped 清单（3365 文件，有限范围） | `5606551d69a441d220b0d734fdb2897b08e10732b0622a5b383f0d939748d6a4` |
| 共同 `startup_handshake_build_manifest_v1.json` | `765aa9270024820eaa150fb173a6cbae4055079f42cdf5bfad7fd123866bd733` |
| 派生 held publisher 二进制 | `21019c23823f8f8f86d856e66158ef73ff784c56cb6822ec69cf7faf632189d4` |
| 派生 ready observer 二进制 | `58e72a003782aa783f78e81cebf12260c378a7dcfa21f7de254415aa8b183bd6` |
| 最新父 Worker 二进制（从共同 manifest 继承） | `dd7d253b420aff8283a4869ae804e5f49fcb76c3357829c5c6c12f020324c35c` |
| 最新父 contract（从共同 manifest 继承） | `0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933` |
| 共享辅助资产锁（141 路径） | `1016674dda427dba0b20ecfc31cb56500552300b26e7d330ea6f5c8ef3226d35` |

两套清单不能合并成一个“全部通过”结论。原 3864 项整体 guard 在最新完整部署扫描中仍为 false、26 项差异；启动 scoped 清单仅覆盖当时隔离构建及其明确依赖；141 项新锁仅声明共享辅助资产身份。未来派生版本必须有自己的受影响输入与回归记录，不能继承旧版全部资格。

### 2.1 下一工作包的实际代码入口

以下均以启动组件隔离根为基目录，关键源码和二进制已在本轮只读复核；完整绝对路径列于 `source_docs/remote_continuation_assets.json`。

- `publisher/src/mpc_node.cpp`：派生 F5 publisher，已有 hold/release 门。
- `publisher/include/usv_mpc_cpp/p1_startup_gate.hpp`：startup manifest、release/shutdown 协议。
- `publisher/build/p1_F5_held_publisher`：当前派生 publisher，不称原 F5 冻结二进制。
- `observer/src/shadow/regulator_shadow_observer.cpp`：实际 ready、失效与候选接纳逻辑。
- `observer/src/shadow/p1_shadow_entry.hpp`、`observer/readiness_protocol.json`：共同协议。
- `observer/build/p1_regulator_shadow_observer_ready_v1`：当前派生 observer。
- `owned_release.py`、`test_owned_release.py`：认证辅助与针对测试；**现有 authorize_release 有意在生产写入前拒绝，不能直接删门开 release**。
- 实验根下 `authored_D0_observability_20261009_v1/runtime`：已继承运行工具。Worker 实际路径按共同 manifest/lineage 继续核验，不从 10 月 6 日旧章节代填。

启动 scoped 清单位于**实验根**的 `startup_handshake_scoped_closed_assets_20261009.json`，不是上述 authored 子目录。共同 build manifest 的已知原字节副本随本交接放在 `source_docs`；本轮没在 authored 子目录找到同名文件，不假设原先已经存在该路径。

## 3. 之前已经完成的工作

### 3.1 三项最初修复（10 月 3 日）

| 修复 | 已完成行为 | 仍有限的证据边界 |
|---|---|---|
| NMPC 迟到解 | 使用完整调用耗时判断 deadline，250/400 ms 返回后拒绝迟到候选，保留原拒绝/重复命令分支。 | 同步节点仍要等 solve 返回；这不是第 200 ms 独立接管，也不是认证备份。 |
| v5 ONNX 推力缩放 | 原 checkpoint 重新导出 `policy_physical_n.onnx`；图内一次 `25×clip(actor_mean,-1,1)`，输出 `[T_L,T_R]` 为 N、±25 N；旁置 manifest 与模型 hash、维度、单位绑定，未重新训练。 | ROS 节点不再额外乘 25。43 维观测末两维为已发布 N；不能因此推断训练端历史动作时序全部正确或 plant 实测力已知。 |
| PPO bag 记录动作 | 新录制入口补齐实际发布的左右命令、相关状态/时钟并验证记录。 | 旧缺动作 bag 不回填；发布记录不是推进器实测力。 |

总归档：`USV_三次修复汇总_2026-10-03.md`。旧模型与失败证据保留；新模型 SHA 为 `ff60e0f70a142dc0c76ac0e1b8e1d113bcff892d7999fad9ef41cf5a83147278`，使用前还需核对旁置 manifest 和运行节点。

### 3.2 P0 与 F1～F5：基线、数据与模型前置

| 工作包 | 已完成内容 | 尚不能声称 |
|---|---|---|
| F1/F2 | 冻结源码/安装/模型与配置身份；发布端 StateSnapshot、AppliedControl、CycleTiming 最小数据契约；直行/左转/右转短程 pilot 和源计数/实际 bag 记录核验。 | 全传感器到 plant 时延、实际应用、推力实测、碰撞安全、GP 标签就绪。 |
| F3 | 同参 Python/C++/native acados 数值对拍；291 种不同输入；真实 reference 函数测试；退化四元数控制准入修复。 | 软件数值一致不等于模型等于真实船或 VRX 6DOF；并未证明 OCP 最优性。 |
| F4 | nominal/controller 与 plant 配置来源分开；真实 reference 与同次 X/U 的 ReferencePrediction；三次配置运行与 24 项跨运行检查。 | plant 质量探针同时改变生成几何，不是固定几何纯载荷实验；不是学习收益或性能提升。 |
| F5 | 动态 B 求解资格复核与 state/reference 输入在同锁临界区冻结；67 个不同 GTest；一组新基线 pilot。 | clear 后在途同步 solve 取消、左右物理原子应用、完整独立执行监管。 |

F5 冻结为 146 项 source/config、177 项 installed、5 项模型，共 328 项。最新 10 月 10 日修复前后核对了 146 份冻结源码与 280 项 MPC/interface 依赖保持原 SHA；这不代表整个旧 live 环境仍匹配。F5 的 193 条 reference、6×21/共 24,318 元素已做逐项来源重建；其原 bag 有 40,613 消息，缺新的 P1 主题时严格检查器正确拒绝，不把旧 bag 升级成新 P1 正例。

参考/profile 已澄清：同步 profile 的实际参考速度可为 0.8 m/s，fallback 配置 0.6 不能冒充实际参考；profile 第二列是曲率。参考速度不是实际航速上限。原正常仿真速度偏差要用真实 reference、plant/config、时序和阶段解释，不能交给 GP 掩盖。

### 3.3 P1：独立执行架构与有限工程验证

已逐批实现或验证的范围包括：共享动态 B 数值核心、solver 进程隔离、不可变 job/candidate、有界 active/pending、固定 tick 的准备/提交/激活分离、状态/参考/clock/目标/模型身份门、完整候选与异常接纳、退出和非空准备队列处理、Worker 活进程能力失联诊断、调度跳拍、部分 raw CDR 接收责任分账、资源与合法 typed 输入上限、Source→实际 storage 应用流分账。

之后的 M0b 工程子项已完成正式合同校验 B0、独立诊断/固定 Witness B1、正常无输出 C0、特定旧版本 R5 日志压力机制、Decision 入队失败即时失效、B4 来源登记和 D0 静止来源观察。每个结果绑定自己的版本；新修改不自动继承旧 R5 压力、恢复或关闭资格。

历史 shadow 运行由 F5 动态 B 独占实际左右推力，新 Worker/regulator 无物理输出。虚拟接纳、合法拒绝或算法一致性都不是新监管器闭环接管证明。能力消息 v1 没有源时间戳/源序号；600 ms 接收租约只约束有效 callback 提交间隔，不证明源新鲜度、抗重放或优化持续进展。受控屏障不是自然 native 永久挂死证明；typed 输入帽不是反序列化前任意恶意字节内存上界。

### 3.4 最新启动握手组件（10 月 9 日证据）

已完成：publisher 构造期 create-only startup identity、显式 hold/release、release/shutdown 同锁、release 前关闭无动作；observer 实际 callback 的一次 legacy_ready 和永久失效；v2 Source/bag 共同 readiness 协议及 owned/参数/隔离图辅助。

最终 **260 次组件 case invocation＝131 Ubuntu＋129 checker，0 skip**。这证明当时具体组件和协议兼容，不证明真实 Recorder storage、全 Worker/Witness 生产链或 D1 动态域。`prepared_acceptance` receipt 不是 Released；组件 positive 不是生产 release 授权。

### 3.5 环境差异和辅助修复（10 月 10 日）

原 25 项变化/缺失已查明主要涉及 develop 安装迁移、配置说明和 visualizer。实际部署 7 个文件：bag/QoS/safety/topic 及 smoke 说明更正；visualizer/telemetry 绝对游标消费修复。bag、QoS、safety 解析运行值保持部署前一致，含 HOLD；topic 的两个 GPS QoS 文档字段改为待实际端点核验。

正常 source 链模块导入 6/6、实际源码回调语义 8/8、已有配置 smoke 5/5、Ubuntu 辅助检查器正反用例 15/15 通过。新 `SIM_SHARED_SUPPORT_20261010_01` 在另一次调用按固定 SHA 独立验证 141/141 路径，包含 100 普通文件、39 文件链接、2 目录链接，解析到 94 不同路径。它检查内容与链接目标，但不是完整传递依赖冻结。

原 3864 清单没有改写，最新完整扫描仍 false、**26 项差异**；新增 telemetry_bridge 是本次有意修复路径。NTRIP 配置、代码和 relay 入口保留，所审阅仿真入口不加载它们，实机启用再验证。最新修复没有启动/重启节点；新 Python 进程可加载修复，旧进程是否已加载必须另查。

## 4. 目前的真正阻塞及下一最小计划

### 4.1 不应越过的六项缺口

| 缺口 | 为什么已有证据不足 | 下一工作包应产出 |
|---|---|---|
| owned DDS endpoint 归属 | 图上同名节点、非零 GID、有订阅，不能绑定已认证 PID/start_ticks/exe。 | 由实际创建端点的受管角色提供端点身份，外部认证作者与进程，再与图和类型/唯一归属核对。 |
| publisher 全有效配置 | 配置文件 SHA 声明不证明进程实际参数未被覆盖。 | 启动后的有效全参数快照、规范 digest、源码/bin/contract/run 身份绑定。 |
| Worker 真实零 hook | helper 单元用例不等于生产外部 Worker 实际 argv、source FD、能力来源认证。 | 实际受管 Worker 的 effective argv、相关 hook 全零、消息 GID/source/合同关系。 |
| production prepare/close | 当前 release 写入被有意拒绝，driver 未完成。 | 有界准备和完整关闭的真实受管角色链，失败与 IO 歧义也纳入账本。 |
| Source/storage/Witness 正链 | 共同 readiness fixture 没有真实 bag storage 和完整 Worker/Witness 总体。 | Recorder 真实写 storage、actual reader 解码、同一完整 stream 的源/typed/bag/Witness 对账。 |
| 动态域、时间理由和最终版本资格 | 原域内冻结覆盖仅末两帧/0.2 s；新统一版本无完整压力/恢复资格。 | 合法工况 recipe、完整非零动作窗口、独立时钟/来源证据及受影响版本回归。 |

### 4.2 Ubuntu 首个工作包的执行顺序

**S0：接收与只读核验。** 阅读上述五份材料和 `handoff_manifest.json`；确认工作区未提交修改、基线/源码/bin/链接目标、实际进程和 domain。核对旧 guard 的身份及现有 26 项处置记录，核对新 141 项辅助锁；若再有变化，先追加变化事实和影响，不更新 expected 消除失败。不要为迁移会话清理旧失败文件或 reset 工作区。

**S1：核对接口能力并明确实现边界。** 检查本机 Jazzy/rclcpp/rclpy/rosbag Recorder 是否能从实际创建角色取得端点 GID 和有效参数。若 Recorder 需要最小 wrapper，先写明新增角色、真实 storage 写入、身份关系和影响范围；外部图查询不能改名当内部证据。若接口确实不能提供所需证据，说明技术限制和可审查替代方案，保持对应条件 false，不能用 synthetic 清单填补。

**S2：最小派生版本。** 从已封存 startup v1 派生新隔离版本，保留原数值核心、reference、权重、阈值和 hold/release/shutdown 行为。为 publisher 增加实际输出 GID、全有效参数快照/digest；为 observer/recorder/Worker 增加实际创建端点与 owned 作者绑定。保存 before/after SHA 和受影响输入清单；不覆盖 live install、原 F5 或 v1。

**S3：有界 driver。** 认证成立后实现严格顺序：

`recorder → held publisher manifest 外部认证 → 带完整 pins 的 observer + Worker/source/Witness → 实际 endpoint/config/zero-hook 门 → create-only 有效 release → 两路实际 Applied + postpair odom/history → 一次 legacy_ready`

不能等 legacy_ready 才 release，也不能先构造缺 producer pins 的 observer 再补身份。pre-release 失败不制造 shutdown 推力；release 后先结束 publisher，保留观察/录制到最后 Applied/session 并对账，再关闭其他 owned 角色。准备、测量和末帧都纳入总体；boot/PID 复用、未知子进程和可见提交/落盘歧义都不能标 clean。

**S4：有限隔离集成。** 在新隔离 ROS domain、无 Gazebo/plant/实船连接下，用明确标记的 synthetic 传感器与参考，验证真实受管角色、Recorder/storage 和共同检查器。针对正路径及同名外来端点、错误 type/GID、参数覆盖、PID 复用、超时/重复/过期 release、IO 歧义、末帧守恒做必要负例。每次新目录，固定 prepare/测量/close 总预算和输出预算；保留第一轮失败，超时不在原目录补跑。

**S5：复判并停止扩大本工作包。** 仅把已取得证据的 owned prepare/close、零 hook、全链 fixture 标为通过；D1 动态、M0b、M4 继续按独立条件判定。交付一份实施报告、状态 JSON、证据/版本清单和下一工作包。已有用例满足当前行为且没有新变化/失败时，不重复重跑或递归扩大任意原始消息测试；把工作推进到具体未闭合条件。

S0～S5 的结果是完整隔离准备链；**不是论文实验 D1，也不是 Gazebo 动态域验收。**

### 4.3 随后 P1 的闭合顺序

1. 全准备链成立后，单列当前域内 recipe 调查：精确场景、reference、初值、nominal/plant、实际速度/转弯/mixed、非零动作和时钟覆盖。
2. 按原条件做 P1 D1 的事前 Go、严格 shadow 来源窗。旧 F5 的参考 0.8 m/s、低速零动作尾段都不能拼成 20 s 域内资格。当前来源窗口的速度门是平面范数 `sqrt(u²+v²)≤1.2 m/s`，不是只检查 u；连续 stamp gap 门为 `≤250 ms`，其余条件按当前 recipe 精确固定。该速度门和 20 ms 工程门不能临场放宽凑通过。
3. 闭合 B4 参数来源、适用域和时间/恢复/关闭/部分发布政策。20 ms 工程检查和 150 ms 截止设计都不是主时钟硬界证明；如果采用有限工程保证，应明确假设和域外处理，不伪称硬实时。
4. 对最终统一版本做必要压力、恢复、退出、关闭和版本兼容验证。旧版本 R5 资格不自动转移；避免把各批 case 简单相加成当前整机资格。
5. B5/M0b：冻结不可变执行合同与政策、源码/bin/模型/配置/工具版本，明确能力消息和时钟保证范围，再决定正式 execute 条件。
6. M4：单独设计有限接管运行。停止 F5 物理输出，由新 regulator 成为左右推力唯一出口，核验固定 tick 激活、实际发布间隔/变化率锚点、反馈历史、双路发布预算和故障分支。没有有效备份时只能称工程降级，不能称碰撞安全。
7. 在唯一执行链下完成 P1 所需的有限已知模型真实切换事务，区分不可变模型快照、准备提交和固定 tick 激活；尚未完成这一子项时 P1 继续部分完成。相关运行身份和受影响回归闭合后再冻结 F6、复判 P1。P2 再赋予证书/备份完整安全语义；工程 execute 条件不自动授予 GP 数据准入或真实推进器保证。

## 5. 未来完整路线：P2～P5 与理论/实机扩展

### 5.1 P2：静态障碍、有效包络和有限备份

**输入条件：** P1 唯一执行链和版本/时间合同清楚；nominal 与 plant 来源分开；动作保持、估计误差和执行器假设可审查。

先使用有限已知 plant 集和固定物理宽界，建立初始状态集合与独立传播验证。加入静态圆形障碍、实际船体水平投影、位置/航向积分误差和整个持有区间占据；检查采样间风险，不能只检查预测节点。外包络需覆盖声明域和数值误差，密集点检仅作辅助验证。

同步新增版本化障碍阶段参数和 acados 硬碰撞约束，完成 codegen/backend 布局及几何数值对拍。不能将几何安全约束用 slack 软化后仍宣称安全；独立验证也不替代候选优化中的明确障碍处理。

备份策略库先做保持航速、左转、右转、减速，按当前状态集合、已知 plant 与执行器条件重新验证未来约 4 s。反馈策略必须连同输入可达界一起验证，不能把开环名义序列套上任意反馈就称认证。每份证书绑定模型/包络/障碍/状态/锚点、激活 tick、有效期、剩余时域和最大保持时长；到期无接续就记失败。

初始设计可沿用船体半径 0.7 m、障碍 0.5 m、附加几何余量 0.2 m、±25 N/80 N/s，但都不是实机测量或已获安全结果。先核对 SDF 几何覆盖，再加可达管和估计/区间裕度；必要改值须事前理由、重新冻结并用于全部对照。

性能均值改变时必须重心化误差集合：物理宽界为 `F0 ⊕ B G0 ⊕ E0`，性能中心改成 `F0+B mu_v`，对应集合用 `B(G0−mu_v)⊕E0`。固定有效真实包络下单纯均值变化不必使原备份失效。先验证这种等价性，排除实现错误制造的伪创新。

**交付/验收：** 包络来源说明、独立候选/备份验证器、证书 schema、几何/codegen 对拍、有限模型机制和反例、证书衰减/接续/域外记录。宽界使所有备份不可行时先改策略/传播或收窄工况，不能无依据缩界。

### 5.2 P3：先合格数据，再 GP 性能模型，再年龄机制

先闭合“最终执行输入与实际持有区间”。AppliedControl 目前是最终发布命令，不是 plant ACK 或实测力。仿真应增加 plant 接收/输入保持、效率/饱和/滞后与实际力状态观察，或建立明示且验证过的执行模型；实机需另辨识。时序/动作错误不能交给 GP 补偿。

第一版标签定义为 `y_k = nu_(k+1) − [F0(x_k, q_exec,k; Δt_k)]_nu`，`nu=[u,v,r]`；输入 `[u,v,r,T_L,T_R]`，输出为三维**离散速度增量**，单位 m/s、m/s、rad/s，注入离散预测时不再乘 Ts。先用合成已知残差、两次不同命令和执行区间验证标签。

固定 200 ms 五维模型先只收实际 `Δt∈[0.198,0.202] s`、区间单一最终命令的样本。400 ms 保持、多次切换、应急接管、执行滞后样本单列；若使用必须扩展 Δt/历史/执行器状态或换模型。速度残差并不使位置/航向误差为零。海流/方向影响可能需要姿态或流特征，通过留出误差判断。

主方案计划数据为 60 段×60 s、5 Hz，最多 18,000 区间，六类运动各 10 段；这些都是未来计划量。按完整 episode 做 60/20/20 训练/校准/最终测试，保留未用于训练的版本与工况，不把相邻拍跨集合造成泄漏。

先固定核超参数、标准化和诱导点，比较 32/64 点；1 Hz 异步更新，每批最多 5 个合格标签，形成不可变快照，不能阻塞 5 Hz regulator。先只更新性能中心，安全保持固定宽界。acados 新残差/障碍参数必须同步 codegen、backend 布局、重新生成/构建和数值对拍；改 C++ 数值模型不会自动改生成图。

沿旧候选逐阶段预计算冻结 GP 均值是近似方法，不称完整状态依赖 GP-NMPC。留出校准后才在影子模式讨论学习界、误差年龄扩张与退宽界。每输出 99% 经验覆盖只是筛选，不能推出多输出/多拍/全域联合 99% 安全概率。学习界到期退有效宽界；宽界也失效则明确域外。

**交付/验收：** 数据构建器与准入报告、episode manifest、合成标签测试、离线模型/校准/版本回放、最差工况误差与漏界、更新开销和年龄/宽界回退机制报告。数据准入未过时先修数据，不训练用于闭环部署的模型；合格数据已过、但经验安全覆盖未达门槛时，GP 只用于性能学习，不进入安全缩界。

### 5.3 P4：冻结 PPO 作为建议器与策略无关机制验证

复核训练 `step()` 返回观测历史动作的时序，包含 reset、两拍不同动作、延迟队列；随后改 PPO 为建议器，统一经过候选/验证/执行层。限幅、过滤、备份接管后的最终命令反馈到下一拍，不能反馈未执行建议。

保持已验证 43 维策略、归一化统计和物理 N 模型冻结，不先重训。建立共同 evaluator，使 B 与 PPO 获得同 plant、障碍、初值、时间、约束、故障和资源。PPO 若性能明显退化，继续用 B/LOS 检验方案 A，PPO 重训作为独立成本；不让策略问题阻断机制研究。

**交付/验收：** PPO 建议消息和统一执行反馈、历史时序测试、同场景 B/PPO 分层结果、固定策略/数据身份。不能拿旧默认关闭 DR 的 evaluate 脚本代替共同安全实验。

### 5.4 P5：强基线、消融、统计和论文贡献判断

先从小规模可证伪实验开始，机制通过后再扩大：

研究 D0 和有限 D2 随 P2 原型开始小样本诊断；研究 D1 随 P3 年龄机制开始。P5 冻结协议后完成系统比较、消融和独立确认集，不将前期设计/调试数据混入最终确认结果。

| 论文实验 | 要回答的问题 | 关键观察 |
|---|---|---|
| 研究 D0 | 固定物理包络下，仅均值切换是否仍物理等价？ | 集合重心等价、误拒绝、版本/证书条件；人工残差偏置明确标记。 |
| 研究 D1 | 漂移和数据年龄管理是否提供独立价值？ | 年龄 2/5/10 s、拒绝/允许更新、固定宽界/紧界/年龄扩张、任务进度。突变违背慢漂移假设时单列压力结果。 |
| 研究 D2 | 返回延迟、执行滞后和保持区间会不会使节点安全检查失效？ | 250/400 ms 计算返回、执行滞后 0/0.15/0.30 s、采样间距离、保持上限、有效接续。 |

必需强基线：修正时序且同验证/执行/备份的固定宽界 B1；固定宽界＋GP 性能模型 B2；同安全层代价接受规则 B3；满足对应终端/控制律条件的安全回返 B4。原仓库 B0 只用来诊断 bug，击败它不够证明新贡献。RTI 只给近似代价时，B3 称 Maiworm 风格工程门禁，不宣称复现其最优值定理；没有对应安全终端/控制律的 B4 只能称有限时域回返实现。对 A-full 做 no-age、no-hold、no-applied、no-version 消融；故障消融均限于有界、受控仿真。

全部方法保持同信息、plant 先验、障碍、初值、±25 N/率限、CPU/线程及端到端预算。真值 oracle 只用于离线判断；如果 A 需要额外资源，另做等资源比较，不给新方法隐含优势。

每个 episode 同时记录四类指标：实际约束/碰撞/域外；迟到/混版/过期执行与备份接续；CTE/进度/到达率/干预；标签/漏界/丢样/端到端 P50/P95/P99/最大、CPU/内存。没有电流电压时 `∑(TL²+TR²)Δt` 只能称控制努力，不称实测能耗。

按 episode、同 seed 成对比较，不能把相关逐拍样本当独立重复；校准和最终确认集分开。保留提前终止、无备份、永久停滞、域外和不利 seed。一次“证书已接受但真值违反”就暂停相应安全结论并追查实现/假设。零事故、P99 达标不等于概率安全或硬实时。

**交付/验收：** 冻结比较协议、同资源原始结果、失败/域外全集、统计与图表、条件—实现—证据对应表，以及是否值得继续的贡献判断。若 B1/B2 同成本同进度已解决问题，应缩小贡献或转为系统/工程论文；不能制造有利反例。GP+NMPC、更新门禁、双模型本身不能宣称首次，新颖性仍需针对年龄/执行器/保持/一致接续条件做查新和证明。

### 5.5 理论、Pi5、实机和扩展

第一目标是声明条件下有限剩余时域约束保持和接续。升级递归可行性/无限时域保证，需要初始可行集、统一有效误差事件、采样间外界、执行器/消息延迟界、安全终端集合与反馈及接续存在性。欠驱动静止点不能直接加 DARE/终端代价就假定有不变集。当前只有待证明框架。

有限机制与强比较成立后，再评估 Pi5 的实际算力/尾延迟、底层 watchdog、推进效率/滞后、估计误差、流扰动、实船故障与 NTRIP 配置。HOLD/零推力/RTL 不等于碰撞安全；飞控模式请求、确认与物理停船要分开验证。动态障碍、COLREGs、多船协同和 PPO 重训属于后续扩展，不加入首轮原型必需清单。

## 6. 进度与成本管理：让后续工作向研究问题收敛

当前大量工作属于工程证据闭合，真正的 P2 备份有效期、P3 年龄/残差和强基线创新实验尚未取得结果。继续增加组件测试数本身不会增加论文贡献。每个新检查必须对应一条明确失败路径或未闭合条件；没有新变化、失败或未解决问题时，不反复重跑同样测试。

建议用以下里程碑管理接续，而不是承诺总天数：

| 顺序 | 单批目标 | 停止该批的条件 | 下一批入口 |
|---|---|---|---|
| 1 | S0/S1：接收事实、接口能力和影响范围 | 有准确身份与可实施端点/参数方案 | 最小代码派生 S2 |
| 2 | S2～S4：完整 owned prepare/close fixture | 正路径与针对负例、Source/storage/Witness 全链闭合 | 域 recipe 与严格 D1 预声明 |
| 3 | D1、参数来源与最终版本资格 | 实际域/时间/政策及必要回归满足 | B5/M0b 冻结 |
| 4 | M4、有限模型事务与 F6 | 唯一出口、最终反馈、时序、工程故障与版本切换验收 | P2 |
| 5 | P2 | 有效宽界/备份/证书及有限实验可用 | 合格数据与 P3 |
| 6 | P3/P4 | GP 数据、性能/年龄机制和冻结 PPO 分层结果 | P5 确认比较 |
| 7 | P5 | 新条件或经验优势可解释，失败边界完整 | 论文、理论或明确转向 |

主方案 3～8 天各阶段、完整首轮 25～40 个工作日等是最初粗估，当前已发现额外来源/身份/执行条件，不能作为从今天起的承诺。下一次实现前先估本批代码范围、构建/记录体积和退出预算；批量实验先做少量 pilot，以实际墙钟、RTF、CPU、磁盘估算成本。Python 批量和关键 VRX 验证分工，VRX 一次一个实例；不立即运行原方案几百次扫描。

每批保留设计/事前决定、参数与 manifest、实际命令、raw 首次失败、source/bag/Witness、解析报告、postrun 和状态更新。明确区分“事实”“待测设计值”“待证明命题”。只对受影响版本补必要验证，更新一份 Ubuntu 当前状态索引，避免多份长文档各自指向不同下一步。

## 7. Ubuntu 新会话可直接使用的接续指令

在 Ubuntu Codex 中打开 `/home/trevor/USV`，让它读取本交接文件。可复制下面的文字作为首条任务：

```text
请先完整读取：
/home/trevor/USV/.sgh-research/handoffs/scheme_A_20261010_01/方案A_UbuntuCodex交接与全面推进计划_2026-10-10.md
以及它指定的 source_docs 五份优先材料和 handoff_manifest.json。

我继续的是研究方案 A：在线残差模型切换时，备份执行一致性、年龄与有效期管理，首先基于仓库 scheme=B 动态 NMPC。当前 P1 的 owned 端点归属/有效全配置和完整 prepare/close 链未闭合，D1、M0b、M4、F6、P1、execute 仍未合格。

先执行 S0/S1，只读确认当前代码/bin/合同/链接/进程、旧 guard 与新辅助锁，以及本机 ROS/Recorder 的实际端点接口。接着承接“P1_M0b_B4_D1_owned端点与配置认证_最小计划”，准备具体受影响版本和有界隔离实现，不重新从最初三修复开始，也不要直接启动 Gazebo、GP训练、PPO重训或物理接管。

工作要持续推进到当前最小工作包有可审查结果；每次只对明确变化、失败或缺口补必要检查。禁止 reset/覆盖未提交改动、更新旧 expected 制造 guard 通过、把组件 receipt 当实际 release，或者把发布命令当 plant 实测。保留失败和原始数据。每批更新当前状态、证据与下一步，并区分事实、设计值和理论保证。
```

### 7.1 首次辅助锁复核的只读命令

以下只读命令不启动 ROS context 或业务节点；先核对 checker 和 manifest 自身 SHA，再按固定 expected 调用。若失败，记录变化和影响，不现场重新计算 expected 当通过条件。

```bash
sha256sum /home/trevor/USV/.sgh-research/repairs/remaining_drift_20261010_01/support_checker/check_support_assets.py
sha256sum /home/trevor/USV/.sgh-research/repairs/remaining_drift_20261010_01/SIM_SHARED_SUPPORT_20261010_01.json
python3 -B /home/trevor/USV/.sgh-research/repairs/remaining_drift_20261010_01/support_checker/check_support_assets.py \
  /home/trevor/USV/.sgh-research/repairs/remaining_drift_20261010_01/SIM_SHARED_SUPPORT_20261010_01.json \
  --expected-manifest-sha256 1016674dda427dba0b20ecfc31cb56500552300b26e7d330ea6f5c8ef3226d35
```

checker 代码 expected SHA：`0700d7b3cb0e0b2f1eba0155bffe80f195a2cff0ea568b1426dcbcdcd90254ea`。只通过辅助身份，不授予 execute。此文件不提供尚未实现的研究 launch 命令；不要复制主方案中“未来接口参数”当当前可运行入口。

### 7.2 skill 和创新记录迁移

本轮只读查询 `/home/trevor/.codex/skills` 与 `/home/trevor/.agents/skills` 的常见用户技能位置，未找到所查的 sgh-research/实验设计/控制反思技能；这不是对插件或所有其它路径的穷尽检查。Windows 技能不会随新聊天自动迁移。本交接 `skill_reference` 提供已读科研流程参考；它们是阅读副本，**没有安装为 Ubuntu 技能，也不代表脚本/依赖全套已配置**。新会话先发现实际可用 skill；普通工程接续可按已核验代码/计划推进，不因缺少技能名停止所有工作。

Ubuntu 项目根 `.sgh-research/research-innovations.md` 本轮未找到；Windows 的统一创新登记随附为 `source_docs/research-innovations.md` 原字节副本。后续核对是否已有其它登记位置，再选定一个累计登记并归并，勿为每篇论文再新建创新文件。本次没有直接创建/覆盖 Ubuntu 的全局创新登记。

运行新控制实验时，应遵循可用的 sgh-experiment-design、control-preflight-reflect、control-theory-veto、control-postrun-retro 流程：先明确假设、实现与理论边界、事前预算和 Go；按实际结果复盘；不把低速/零动作/HOLD 或统计覆盖等同证明。单纯文档、只读检查和语义单元测试不是新的控制实验。

## 8. 附件、证据与维护规则

`source_docs` 是交接时的原字节快照；其中内部 Windows 链接未改写，旧日期、状态和失败保持原样。请在此目录按文件名阅读，或按本交接给出的实际 Ubuntu 资产路径访问原始证据；不要假定任何 `C:\Users\...` 路径在 Ubuntu 可用。所有附件的原路径、bytes 和 SHA 见 `handoff_manifest.json`。本交接不会复制 bag、模型库或二进制，这些原件已经在 Ubuntu；也不会把副本当成重新运行的证据。

新会话建议另建版本化的 `current-status.md`，写清当前最小任务、源码/bin/合同、已通过/未通过、最新运行证据和下一条件；保留本交接作为 2026-10-10 快照。未来状态变化必须有新证据和适用版本，不能回写旧历史 JSON 改资格。

用户要求的判断原则持续适用：执行前检查错误前提、逻辑跳跃和缺失信息；独立判断，不迎合；数字和结论尽量核验来源；错误要直接指出并说明风险；主动提醒变量、成本和偏差。当前最大的风险是把工程组件验证误当安全/科研贡献，或让证据维护持续扩大而迟迟不验证真正研究问题。
