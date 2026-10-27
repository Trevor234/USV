# 方案A第60批：W2内部接线审查与缺口修正

日期：2026-10-22。审查 59 包 W2 内部接线（R1–R8 全部复现），并在本包新派生树完成 §6.1–§6.2 的修正；未生成 registry、未启动 ROS、owned 闭环或硬件。

审查报告：[W2内部接线代码审查与构建登记前修正计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_hook_review_20261022_60/documents/方案A_W2内部接线代码审查与构建登记前修正计划_2026-10-22.md)。
实施记录：[W2接线缺口修正实施记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_hook_review_20261022_60/documents/W2接线缺口修正实施记录_2026-10-22.md)。

## 审查发现（全部复现）

- Worker 严格白名单缺五项 W2 参数 → 实际 Driver 启动会被拒。
- Driver 无 W2 case；`w2_entered_at` 从未赋值、事件未消费、release 条件永不成立；tick 按读取顺序而非真实时序计数。
- Regulator 无 W2 准入分支。
- fd 方向检查用 `st_mode & O_ACCMODE`；真实 pipe 两端 `st_mode` 相同，读写端都判为只读。
- 旧 `BeforeCall` 回调被静默删除（抛异常的 hook 实测 `seen=0`）。
- 调用事实早于真实 C 入口置位；policy 快照与 Boundary 不一致；后续 Job 会复用旧结果。
- **Gate 后 stop 窗口可达**——59 号报告的"不可达"是错的。
- runner 复用固定 build 目录并原地修改作者树。

## 已修正

| 编号 | 修正 |
| --- | --- |
| R1 | 白名单补齐五项；无 fd 时其余参数须默认；nonce 须非零 |
| R2 | 新增 `W2-native-boundary-hold`；消费进入/结果事件；tick 按 `start_ns >= entered` 真实筛；记录写帧字节数与 SHA256 |
| R3 | `S_ISFIFO` + `fcntl(F_GETFL)` 判方向 |
| R4 | 测试改为经 `solve_owned` 驱动目标 Job/ordinal；新增"删除整块接线"变异 |
| R5 | 恢复 `if(hook_)hook_(ordinal)` |
| R6 | marker 下移到真实 `acados_solve` 前；快照在 Boundary 更新后生成；目标 Job 只发一次结果 |
| R7 | 恢复 post-gate stop 检查为可达，并加入变异覆盖 |
| R8 | 私有副本 + 唯一 build 目录 + `CMAKE_HOME_DIRECTORY` 断言 + 封存树 hash 前后复核 |

## 验证

```
test_w2_native_boundary  PASS 15/15
test_w2_backend_wiring   PASS  6/6
test_w2_entry_contract   PASS  4/4
6 个变异全部 prepared 且被捕获
封存树前后 hash 一致
complete: True
```

关键：`delete_backend_wiring` 变异现在被 4 个真实 Backend 测试捕获——59 包删除整块接线后原测试仍全过。

## 仍未做

- §6.3 构建与登记：新 bundle/ELF/Driver SHA/registry/registration 均未固定，本树 ELF 不能作为 owned 来源。
- §6.4 最小 owned W2：多拍、真实心跳、槽位有界、独立释放、过期终局、API/退出对账全部未验证。
- expired 生命周期政策未落为登记条款（代码走终端隔离路径）。
- `kDuplicateRelease` 仍无实际返回路径。

## 说明

- 私有在线测试实际链接并调用 acados 求解器，不能表述为"未运行任何求解器"。
- `run_entry_verification.py` 曾尝试启动完整 Worker 验证入口，但其 `driver_peer` 需要完整 manifest 链，超出入口检查范围；已改为 `test_w2_entry_contract` 纯逻辑单元覆盖 R1/R3。
- 未修改 59 作者树及 56/57/58 原件；用户并行工作区保留；实船 B 保持 MANUAL＋RC 覆写。
- M4/F6/P1/plant 接受/硬实时/研究结论均为 false。
