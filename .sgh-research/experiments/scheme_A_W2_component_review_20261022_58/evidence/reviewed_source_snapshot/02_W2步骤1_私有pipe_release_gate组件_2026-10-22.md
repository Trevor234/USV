# W2 步骤 1：私有 pipe release gate（组件层 + pipe 层，已实施并验证）

_2026-10-22。范围：纯 C++ 组件，不接 ROS、不起子进程、不改 56 包。_

## 1. 本步交付什么，不交付什么

按审查文档 §5.6 的顺序，W2 先做**纯组件验证**，再登记 owned 运行。本步只完成前者：

**已交付**：一个有界的 release gate 组件 + POSIX pipe 适配器 + 31 个测试（19 单元 + 12 pipe）+ 7 个变异自检。gate 在调用边界等待，只接受一次身份匹配的释放，并把超时、EOF、半帧、CRC 错误、身份不符、重复释放、停止请求区分成互不相同的终局。pipe 层用真实 fd 验证 EOF 只在所有写端关闭时到达、跨写分片能重组、信号中断 poll 不被误报为超时。

**未交付**：进程真的停在 native 边界、Driver 真的只向 Worker 继承读端、跨多拍后过期分支的行为、以及任何 owned run。这些属于 §5.6 后半段，需要新的作者树派生、重建、重新登记，不在本步。

所以本步**不提升**任何矩阵子项，也不改变 M4/F6/P1 的 false 状态。

## 2. 组件设计

文件：

- `implementation/w2_gate/w2_release_gate.hpp` —— 帧格式、CRC、身份、（无 I/O 的）状态机
- `implementation/w2_gate/w2_pipe_reader.hpp` —— POSIX `poll`/`read` 适配器，唯一知道 fd 的部分

### 2.1 为什么不复用 DDS 话题

审查文档 §5.2 明确首版不加第二套 topic。组件也按这个前提设计：释放的身份就是继承来的那个 FD，命令帧携带其余。若走 topic，每个订阅者都能看到释放，还需要另一套认证，反而把“单次、绑定到具体调用”这个核心约束变弱。

### 2.2 帧格式

固定 44 字节，小端，无填充：

| 偏移 | 宽度 | 字段 |
| --- | --- | --- |
| 0 | u32 | magic `W2RL` |
| 4 | u16 | version（=1） |
| 6 | u16 | reserved（必须 0） |
| 8 | u64 | run sequence |
| 16 | u64 | job id |
| 24 | u32 | call ordinal |
| 28 | u32 | nonce |
| 32 | u64 | release sequence（必须 =1） |
| 40 | u32 | CRC-32 over 0..39 |

**五个字段一起匹配**，不是只比 ordinal。审查文档 §5.3 指出“hook 参数只有 ordinal，不携带 Job”，仅凭 `ordinal==1` 会让每个 Job 的第 1 次调用都暂停。组件把 run/Job/ordinal/nonce 一起绑进帧，正好补这个缺口。

`reserved` 必须为零、`release sequence` 必须为 1，是为了让“协议升级”和“重复释放”都变成显式的 `bad_frame`，而不是被静默接受。

### 2.3 十种互不相同的终局

| 终局 | 含义 |
| --- | --- |
| `released` | 合法、匹配、首次释放 |
| `not_configured` | 本运行未登记 gate，调用方直接继续 |
| `timeout` | 未收到任何字节即到期 |
| `eof` | 写端已关闭且未释放 |
| `partial_frame` | 收到字节但不足一帧（含中途到期） |
| `bad_crc` | 帧完整性失败 |
| `bad_frame` | magic/version/reserved/sequence 非法 |
| `identity_mismatch` | run/Job/ordinal/nonce 不指向本边界 |
| `duplicate_release` | 同一边界第二次释放 |
| `stop_requested` | 等待期间收到停止 |

把 `timeout` 与 `partial_frame` 分开是有意的：前者是“Driver 从未释放”，后者是“Driver 开始释放后死在中途”，事后证据里这两件事不能混为一谈。同理 `bad_crc` 与 `identity_mismatch` 分开，避免把损坏帧说成“发给了别的 Job”。

### 2.4 不持共享锁

gate 只读一个 FD，不接触 Worker 的 `pending_` 锁、Source 日志锁或 capability 锁。`stop_requested` 是调用方传入的 `const bool *`，组件不为同步策略做决定——调用方传入它已有 atomic 的 relaxed 视图即可。这满足 §5.2“进入等待前已经释放这些锁”的前提：组件本身没有锁可持。

### 2.5 pipe 适配器的三条纪律

`w2_pipe_reader.hpp` 只做三件事，每件都有测试与变异覆盖：

1. **轮询超时不向下取整。** `poll()` 收毫秒。`(ns + 999999) / 1000000` 向上取整，且重试时至少给 1 ms，避免把亚毫秒预算变成 0 ms 的立即超时。
2. **EINTR 只扣实际耗时。** 用 `clock_gettime(CLOCK_MONOTONIC)` 量每次 poll 的实际耗时，信号中断后按剩余预算重试。**这条在初版是错的**——见 §3.1。
3. **无效 fd 立即失败。** `fd_ < 0` 返回 0（EOF）而非 −1（超时），否则会干等整个预算。

它**不**验证：这个 fd 是不是 Worker 真正继承来的读端、写端是否被别人持有、fd 是不是终端或共享 socket。这些属于 owned 运行的登记与核对，适配器只回答“从这个 fd 能不能读到一帧”。

## 3. 验证

入口：`implementation/w2_gate/run_component_verification.py`。

```
component suite: PASS {'pass': True, 'passed': 19, 'failed_tests': []}
pipe suite:      PASS {'pass': True, 'passed': 12, 'failed_tests': []}
mutation drop_identity_comparison          -> caught by 5 tests
mutation drop_crc_check                    -> caught by 1 test
mutation drop_stop_poll                    -> caught by 1 test
mutation drop_release_sequence_check       -> caught by 1 test
mutation drop_partial_frame_distinction    -> caught by 1 test
mutation invalid_fd_waits_instead_of_failing -> caught by 1 test
mutation no_eintr_retry                    -> caught by 1 test
suite passes: True
every prepared mutation caught: True
```

**变异自检是本步的重点**，不是附带项。上一轮审计器的教训正是“用例通过但删掉被测逻辑仍通过”。这里逐个删掉 gate 的七个保护，每一个都至少有一个测试变红。

### 3.1 变异测试实际发现的两个缺陷

这两条不是事后补的说明，是变异跑红之后才暴露的：

**(1) EINTR 记账错误（gate 行为缺陷）。** 初版在 poll 被信号中断时，把**整个请求的 slice** 计入已等待时间，然后按剩余预算重试。结果一次 SIGALRM 就把整个预算烧光，`SignalInterruptingPollIsRetriedNotReportedAsTimeout` 返回 `timeout` 而非 `released`——也就是说，普通的信号投递会被误报成“Driver 从未释放”。修正为 `clock_gettime(CLOCK_MONOTONIC)` 实测每次 poll 的实际耗时，只扣实际时间。

**(2) 无效 fd 等满整个预算（gate 行为缺陷）。** 初版 `read_some` 对 `fd_ < 0` 返回 `-1`，gate 把它当成超时，于是会干等 2 秒。现在返回 `0`，gate 立刻报 `eof`。`NegativeFdIsReportedImmediatelyNotAfterTheBudget` 用 5 秒预算、断言实际耗时 < 1 秒来锁住这一点。

第 (1) 条如果没有 pipe 层测试和变异自检，会一路带到 owned 运行里——症状是“W2 偶发超时”，而根因是一次被信号打断的 poll。

产物：`evidence/w2_gate/component_verification_v1.json`。

## 4. 与其他角色的接线（下一步，未实施）

组件与 pipe 适配器本身不接入 Worker。接线需要改的是 §5.4 列出的四个文件，且必须在新派生的作者树里做。

1. `solver_worker_m4.cpp`：在 `solve_start_ns` 检查之后、`solver_->solve_owned()` 之前插入 gate 等待。注意现有代码在 `v2_block_` 之后**又做了一次** deadline 检查（`result.solve_start_ns = ...; if (stopping||fatal_|| > deadline) { pending_expired_before_native; continue; }`）——这正是 §5.5 要求的“释放后重查截止”的落点，gate 应插在它之前，让它成为“最后 guard”。
2. `owned_cold_backend.hpp`：现有 `BeforeCall` hook 在 `invoke()` 内、`clock_()<=deadline` 检查之后、`solver_.step()` 之前。若要把 gate 下移到 C++ 包装器内部而不是 C++ 外层，这是正确 seam；但首版建议放在 `solver_worker_m4.cpp` 的外层 guard 之前，因为那里已经能记录 `owned_backend_entered` / `actual_C_call_started` 的区分。
3. `owned_m4_diagnostic_driver_v1.py:166`：`subprocess.Popen(..., start_new_session=True, env=...)` 需增加 `pass_fds=(write_fd,)`，并且只给 Worker。其余三个角色不继承。
4. 新 registration/registry：把 FD 能力、run/Job/ordinal/nonce、最大等待、预计终局写进登记，并在 manifest 的 `effective_parameters` 里体现，使审计能绑定。

**必须同时处理的截止语义**（§5.5）：150 ms 截止 + 200 ms tick 决定了跨两拍释放时该 Job 必然过期。合法终局是“释放被验证 → 最后 guard 判定过期 → C 调用不发生 → 旧候选不激活”，**不能延长 deadline**。因此接线时必须记录四个独立事实：`owned_backend_entered`、`actual_C_call_started`、guard 结果、最终调用计数；不能把外层 `solver_invoked` 等同于 C 函数已进入。

## 5. 边界

- 本步没有启动任何 ROS 进程，没有构建作者树，没有修改 56 包。
- pipe 层测试用真实 pipe 与真实 fd，但**不是**跨进程继承来的 fd：`PipePair` 在同一个进程里持有两端。因此“Driver 是否只把读端交给 Worker、其他角色是否没继承”仍未验证，属于 owned 运行前的联调项。
- `POLLHUP` 到达后先读残留再返回 EOF 的顺序在本进程内成立；真实父进程先写后关、子进程晚读的顺序未实测。
- `duplicate_release` 在组件层由“release sequence 必须为 1”覆盖；gate 的 `done_` 标志保证不再读第二帧。第二帧在真实 pipe 上的到达时序仍未经实测。
