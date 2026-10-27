# P1 M2 调度跳拍与准备队列正常释放：运行前反思

日期：2026-10-06。阶段仅限无物理输出诊断；M2、M0b、M4、F6 均未因此关闭。

## 事实与证据锁

- 当前 worker v8 / regulator v11、revision 4 契约；T=200 ms、候选截止=150 ms、能力接收租约=600 ms、active watchdog=1 s。保留这些阈值及契约字节。
- 只读主机审计 `evidence/scheduler_audit_20261006.json`：受保护 1069 项 SHA256 无漂移，现存控制器/Gazebo=0，无法读取进程命令行=0；boot 不变。
- 已有 `p1_capability_regression_pending_exit_20261006_01` 实际源码日志中目标 4→5 被替换，worker 退出后清除目标 5，活动准备目标 3 被取消。不能再说“没有准备队列替换证据”。
- 目前未见准备等待正常结束后的过期项拒绝/最新项继续运行证据，也未见真实独立 tick 线程跨多拍延迟的闭环源日志＋bag 证明。已有 Admission 单元测试不是这种运行证据。
- ROS 主机安装 rclcpp 28.1.21、rmw_fastrtps 8.4.4、fastcdr 2.2.7。上游 Jazzy executor 会捕获 take 阶段的 RCLError，未取到消息时不调用业务回调；不能假定 malformed CDR 一定传到 main catch。安装头文件 SHA 已保留，上游分支与已装二进制不能等同。

## 排名假设

1. `insufficient_evidence`（高置信）：调度跳拍逻辑已有实现，但缺少实际跨拍隔离证明。
2. `flow_policy_mismatch`（中置信）：准备项在 deadline/current_tick/version 门被丢弃，目前没有逐项源日志，单看 job 数不足以证明为何未提交。
3. `insufficient_evidence`（高置信）：字节解码失败在 middleware / executor 发生，现有应用级 typed 日志无法覆盖整个 CDR 管线；仅本地解码实验也不能宣称 live DDS 故障隔离完整。

## A / B / C

| 选项 | 方法 | 置信 / 影响 / 成本 / 风险 | 判定 |
|---|---|---|---|
| A | 最小观测增强＋默认关闭的有限 tick 线程等待；两个生产 regulator 无输出场景；另外只做已装库的本地 CDR 解码边界审计 | 高 / 中 / 低 / 低 | 选用 |
| B | SIGSTOP 整个 regulator，再观察跳拍 | 中 / 中 / 低 / 中 | 会同时阻断 capability/input 回调，租约和状态年龄混淆，不选 |
| C | 随机 CPU 压力、消息字节模糊测试 | 低 / 中 / 高 / 中 | 难以隔离机制及复现，不选 |

## 最小修改与验收

1. 新 tick 诊断参数默认 0；只在 `no_output` 且 fault enabled 开启，范围 0..3000 ms，第三次 tick 迭代触发一次。等待不持有决策/准备 mutex，20 ms 分片可被停止信号取消。约 610 ms 等待只用于制造跳拍，不作为性能阈值。
2. 记录实际 scheduler skip 的旧拍/新拍、单调时间、待清候选身份和清除后状态；保持原有跳拍/候选清除算法。
3. 对原有准备提交门的拒绝增加源日志，保持既有拒绝优先级、deadline 和锁。
4. `tick_skip`：真实 native 通过前缀、跳过至少 2 拍、不补发中间拍、不激活旧目标候选，跳拍后至少 3 次新目标虚拟接纳；等待期至少 2 次有效租约续期，worker 无终止；raw typed job/candidate/decision 全内容及输入计数核对，正常关闭。
5. `prepare_release`：原有准备等待取 2810 ms，自然结束（合法上限仍 3000 ms），避开与整拍同时释放的观测竞争，pending 至少 2 次替换、容量 1；活动旧准备目标不得提交，明确原门拒绝；恢复时提交最新 pending 目标且仍在原 deadline 内，至少 3 次恢复虚拟接纳；不终止 worker；正常关闭及同一证据核对。
6. 新版 normal 与 delay150 各一次必要回归，前者出现真实 native 虚拟接纳，后者仍无过期接纳。tick 参数的正常默认值及模式/范围门测试必须通过。
7. CDR 只选 empty、截断封装头、有效 Candidate 截断尾部，已装库子进程各 ≤2 s，与有效 Candidate 控制样本比较；不创建 ROS publisher/subscriber，不修改原 bag。报告实际异常/返回码，不升级为端到端 DDS 通过。

## GO / 停止门

GO：只读 preflight 与 1069 项保护检查通过，用户“继续”已授权该 P1 最小工作包。改动仅 regulator 观测/诊断、相应测试/运行检查器与说明；worker、F5、契约保持 SHA 不变。先备份源/二进制，构建测试通过才运行。

任一物理 publisher、身份/boot/保护资产漂移、无完整 typed bag、无法闭合 owned cleanup、未形成触发前提即停止晋升并保留失败证据。相同门连续两次失败且无新机制证据，停止递归。不得放宽原阈值以让场景通过。全部关闭只表示本工作包完成，M2 其余序列化责任和最终输出契约单列。

EDA route/STA/DRV/PPA/Slurm 字段在本 ROS 场景 N/A；对应证据使用单调时间源日志、实际 mcap、进程身份台账、构建及保护清单。
