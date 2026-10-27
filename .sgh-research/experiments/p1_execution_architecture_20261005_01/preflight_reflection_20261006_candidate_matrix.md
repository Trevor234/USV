# P1 异常候选真实传输：执行前核对（2026-10-06）

沿用 control-preflight-reflect；ROS 控制任务不适用 EDA 的 STA/CTS/DRV/PPA/Slurm 指标。本轮目标是 M2 剩余候选接纳矩阵，未授予 execute 或 F6 资格。

事实：worker v8/regulator v9 和 revision 3 合同已通过上一批 12 项时间/任务/源年龄/激活矩阵。173 项 Ubuntu Python 通过；38 项当前 C++、114 个不同 GTest 为原保留证据。本轮现场核对 boot 不变、controller/Gazebo=0、不可读 cmdline=0；842 项已声明资产无漂移。

已检查生产 valid_job、candidate、Admission 登记顺序和 ROS 固定长度预测数组。header/身份、N/dt/绝对时刻、有限数、U0/X0、完整 job echo、native 时间、最终目标和去重按真实顺序核对，不能随意给某个输入贴预期 reason。改变 target_tick 回显先触发 job_echo_mismatch；完全一致旧候选重放才测试 wrong_tick。重复与迟到的判据以原截止和当前 tick 为准。

## 假设及风险排序

1. 既有确定性用例不能证明真实 DDS/callback 上所有异常候选都拒绝；需逐条记录注入内容与实际登记事件。
2. 多 publisher 的可靠 QoS depth=1 仍可能发生覆盖，不能假定原候选先登记；每项注入延后原始候选观察至少 20 ms，并由最终 source ready_commit 复核顺序，不满足前置条件即失败。
3. 异常副本不能包装成 native 原始失败。NaN/Inf 在 C++ JSON source 中成为 null，actual bag 保留 invalid numeric 内容；只在对拍该源表示时按明确规则规范化，不能修补原字节或把它当有限值。

## A/B/C

- **A（选择，GO）**：原代码/参数不变，新增 create-only real regulator/worker no_output fixture；原 native 发布继续，驱动逐个新原始候选复制后注入 38 类身份、布局声明、非有限/失败标志、U0/X0、echo、native timing、重复/旧结果/迟到异常。每项独立输入记录，不能把38类计作38个独立run。恢复/正常前后段有实际接纳；全过程0物理端点。独立checker从实际 MCAP 对拍原始 native 与注入内容、多重计数、登记拒绝和最终决定。
- B：若发现明确生产缺陷，保留失败、备份 source/bin，在原合同下最小修复、升实现版本并用新编号独立重验；不放宽门槛。
- C（NO-GO）：伪造 native 失败、把额外测试副本算成真实 worker 输出，或用 typed 数组字段测试宣称非法 CDR/消息长度已验证。

验收：原始 native success/ready 为每项前提；注入前后仅声明字段改变，实际storage=原始native+注入的完整字段多重集合；source每条登记与注入内容/时间绑定，expected reason符合真实检查顺序；异常副本没有被登记、没有替换合法ready；原始合法流与后续正常接纳继续。source/flush完整、owned进程清理、pre/post guard无漂移。stop：身份/物理端点/记录/注入前提/清理任一失败则保留并停止本批，不能循环改阈值求通过。

未覆盖：非法序列化字节、非空preparation pending/退出并发、活进程失联和真实物理发布/恢复预算。M2整体、M0b/M4及P1整体保持未完成。
