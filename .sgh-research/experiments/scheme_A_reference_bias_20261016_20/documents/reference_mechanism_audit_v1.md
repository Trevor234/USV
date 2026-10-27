# 参考生成机制与稳态速度偏高审计

整理日期：2026-10-17；原始运行与原生对照来自 2026-10-16 的第 19/20 批。

## 结论与证据边界

已定位一个有实际后端反事实支持的主要机制：旧参考构造器以 **Job 的预测 target_state** 找最近路径点，再固定向前取两点。路径点间隔为 0.2 s，导致参考首点持续领先目标状态约 0.3–0.5 个“按目标速度行驶的秒数”。每拍重新选点后，这段位置领先又被重新引入，位置代价会推动船追赶前视点。

profile 速度与参考位置序列的步进速度都保持声明值；没有发现速度被意外写成 1.25 倍、预测 dt 被改大、或低速档误用 0.6 m/s fallback。旧 408 次接纳证明其时序/输入一致性守卫通过，不等于速度跟踪精度合格。

本审计证明有限样本中的参考机制及后端首控因果；尚未证明该因素单独解释所有闭环稳态偏差，也未授予真实 Plant、硬件或方案 A 阶段资格。

## 实际链接与源码归因

实际 Observer 的 link.txt 使用 `usv_mpc_cpp::mpc_core_lib` 导出的静态 `libmpc_core_lib.a`；ELF 中存在 `build_frozen_reference` 与 `sample_path_profile_at_time` 实体。函数体在 `src/p1_input_core.cpp`，不是仅由头文件决定。

历史 flat roster 已固定该 `.a`：32114 bytes，SHA `b4279533c459fcdd5026fd19f293da7063e3d1a54cfcfe11dccf9aa22e8c8020`。历史 roster 未单独固定当前 `.cpp` 与 `.o`，因此不能把原有头文件或 ldd 记录等同于历史源码闭合。

新增证据补足当前源码与冻结机器码的等价性：在新 D20 目录按原 flags.make 重编当前 `p1_input_core.cpp`，生成 `.o` 与该历史固化 archive 的 `p1_input_core.cpp.o` 成员 **逐字节相同**，SHA `8de591f7c7a65a281046e4e85a3c40b10171df4e03e34bfe0076a7e134ceedbd`。这属于本批新增的等价性证明，未回写历史 roster。

独立原生 probe 直接链接实际静态库，从原始 SQLite 的 Path/Profile 与真实 Job 状态重建参考：414 个记录 Job 的 126 个 double 均逐项完全一致，metadata 的 nearest/start 也一致。以 prepropagation frozen_state 代替 target_state 会改变其中 402 个 Job 的参考，排除了对采样状态的误读。

## 时间、位置和速度各自是什么

Observer prepare_loop 先把传感器状态按真实 held-input 历史传播到目标激活时刻，然后把传播后的状态传给参考构造器；原先的传感器状态另存为 `job.frozen_state`。

旧函数先求最近离散点 j，再令 i0 = j + max(1, reference_start_offset)。实际 offset 为 2，t0 = profile[i0].time；整个 horizon 在 t0 + k*0.2 上采样。实际 profile_time 分支使用 profile_u，cruise_speed 仅用于未同步时的旧 fallback。

对于不触末端的直线，点距 Δx = v_ref*0.2，最近点量化误差在 ±Δx/2 内，因此 ref0.x − target.x = 2Δx + ε，即领先时间在 [0.3,0.5] s。这里是位置 carrot；horizon 的 Δx/Δt 与 profile_u 仍然一致。

将 offset 参数简单设为 0 仍会被旧函数夹为 1；原生对照也证实这一点。真正取消额外前视需要明确的新采样策略。

| 声明速度 m/s | 末 50 Job 的平均 target.u / profile_u | ref0 领先时间范围 s | horizon Δx/Δt 最大误差 m/s |
|---:|---:|---:|---:|
| 0.05 | 1.250077 | 0.320849–0.472394 | 1.15e-15 |
| 0.1 | 1.250074 | 0.322652–0.474768 | 2.3e-15 |
| 0.3 | 1.249861 | 0.336576–0.488047 | 1.14e-14 |
| 0.6 | 1.222008 | 0.306762–0.489143 | 2.28e-14 |

此表明确取末 50 个记录 Job 的预测目标状态，含关闭时待处理 Job；不是硬件稳态速度估计。

## 实际 Acados warm-prefix 因果对照

共用 s010 的 Job 104：target.x=2.50254083761055 m，target.u=0.12541161761083622 m/s；ref0.x=2.5400000000000005 m，profile_u=0.1 m/s；nearest=125，start=127，t0=25.4 s。参考首点比 target.x 超前 0.03745916238945046 m。

实际后端按历史顺序重放 1..104 的完整 warm prefix，baseline 的首控、X、U 与真实记录最大差均为 0。对照分支保留前 103 次相同 warm 状态，仅把第 104 个 Job 的整个 reference.x 平移 −0.03745916238945046 m；profile_u、空间步进速度、初态、真实 anchor、合同、Q/R/Rd、模型和守卫不变。

- 原真实首控：[0.22811310506227794, 0.22811317547866702] N。
- 仅平移 reference.x 后：[0.05334049129865667, 0.05334056281527283] N。

固定状态的重复 RTI 对照进一步排除“后端天然要跑到 0.125”的解释：

| 固定状态 u | ref.u | ref0 位置领先 m | 首控（每通道，约 N） | 预测首步加速度 m/s² |
|---:|---:|---:|---:|---:|
| 0.1 | 0.1 | 0.00000000 | 0.17206772 | 0.00007269 |
| 0.1 | 0.1 | 0.03745916 | 0.34615105 | 0.02097832 |
| 0.125 | 0.1 | 0.00000000 | 0.04629858 | -0.02224495 |
| 0.125 | 0.1 | 0.03745916 | 0.22114023 | -0.00134748 |

这些是原生固定状态/参考/输入锚点求解，不是新的闭环运行。两组参考不同，其目标函数总值不能直接当作跟踪改善百分比。离线反事实只调用求解后端，未通过实际 Job/Candidate 接纳流程，也未取得运行资格。

## 最小后续实施与当前组件准备

已准备独立 `projected_profile_time_v1`：在 target_state 到最近路径段的连续投影处确定 t0，不额外加 carrot；保留 profile_u/rs、20 步和 0.2 s 步长。零平衡重复点使用显式 stationary 分支；stamp 不匹配、非有限值、时间不严格递增、混合退化段及 horizon 超出 profile 均明确拒绝。曲线 yaw 仍连续展开。

该纯组件已完成 prebuild source/header/static archive/compiler/link 固定，96 项原生真/反例通过。N20 的生产角色集成、构建和后续 DDS 运行以独立记录为准；组件通过不授予阶段资格。新策略使用独立 contract revision/policy 和 Source 投影 metadata，原 legacy builder 与旧业务源码保留。

下一验证保持顺序：先固定真实 Job 与原生参考/后端对照，再验证新角色合同与所有原守卫；先完成 0.05 m/s 的同种正常与受控负例，再逐级 0.1/0.3/0.6 的独立 20 s 标称闭环。记录全部接纳、首失败门和跟踪误差，保持 Q/R/Rd 与原状态、时限、身份、输入守卫。

## 证据索引

- `postrun/reference_mechanism_audit_v1.json`：本审计汇总与所有输入 SHA。
- `build/reference_probe_attempt01/`：414 Job 的实际 archive 原生对照与 prebuild pins。
- `build/reference_source_recompile_attempt01/`：当前源码到历史 archive 成员的 bit match。
- `replay/native_actual_backend_v1.json`：真实 warm-prefix 和 fixed-state 后端对照。
- `build/projected_reference_component_attempt01/`：96 项候选纯组件验证。

组件验证、长窗研究资格、真实 Plant/硬件资格分别记录；当前研究资格与执行资格均保持 false。
