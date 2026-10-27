# 首次 DecisionEnqueue 失败共享槽失效：执行前反思

## Evidence Lock

2026-10-08 只读核对完成。R5 历史 guard SHA 为 `0e53dcf332c0d4ceae8f377533720e21329675e8e59639811bccbe97a11908bc`，2626 个文件无漂移；主机 boot `5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb`，现存 controller/Gazebo=0，无法读 cmdline=0。普通源、诊断源分别锁定 `1163a651…eb8c`、`a67d65fd…cdb`。当前 ROS 工作空间普通源和 install 可执行文件属于历史 guard，不覆盖。

## 问题与假设

代码事实：首次 `sink.add(Decision)` 返回 false 后，两个版本均未调用共享槽失效；若当前动作是零，紧邻 shutdown 分支直接退出，下一 TickStart 不发生。历史 R5 先由 TickStart 失效，未覆盖这种次序。本轮目标是清 candidate、admission ready/committed 和 pending，并与最终准备提交门使用同一业务互斥锁。

假设：在 Sink 返回后取得 `mutex_`，锁内设置停止状态并无条件调用已有 `invalidate_locked()`，能在同拍退出前清共享槽。锁序保持业务 mutex→prep mutex；Sink 已释放队列锁。已 pop 到准备线程栈上的工作仍由既有最终提交门拒绝，已提交 DDS 尾部不会被撤销。

## 三种可选路径

A：新版本修复普通源和诊断源；抽取真实 Tick 尾部供发行循环与源码链接测试共用。仅测试编译宏提供不启动业务线程的构造入口；发行二进制不存在新参数或故障入口。旧源用完全相同尾部抽取适配保留旧失败体，形成负例。再运行一次新诊断版本有限正常对照。

B：等待随机日志压力再次出现该次序。成本高且可能仍先走 TickStart，无法保证命中。

C：新正式 ROS 故障参数模拟首次入队失败。增加配置和资格面，超出本次最小修复。

选择 A。定向测试使用真实 Sink 拒绝及真实 finish_tick 的入队、清槽、shutdown 返回路径；不复制一个镜像清槽 helper。真实 ROS 初始化仅用于源码链接测试 Node/Publisher，测试不启动准备/控制线程，不发布物理推力，不把合成 Witness 身份当作运行资格。

## GO / NO-GO 与停止条件

GO：历史资产无漂移、主机空闲、源 SHA 正确，允许新目录构建和有限 no_output 验证。发行编译禁用测试宏。旧两源负例必须在清槽/新 Witness 断言失败，新两源正例必须通过；不把旧负例预期失败包装成正常通过。新有限正常对照须保留严格源/bag/Witness/输送/生命周期检查。任一超时、未回收 owned 进程、未知身份或资产漂移即 NO-GO，不晋级。

阶段停止：实际分支修复、负例/正例、隔离构建、有限正常对照和独立复核完成即停止。B4/B5、正式 M0b/M4/F6/P1 和 physical execute 仍不晋级。本轮不声称完整 ROS 图中压力首次失败恰好落在 DecisionEnqueue，也不声称硬实时性能或实船证明。
