# P1 时间、任务与激活门禁：执行前核对（2026-10-06）

本轮继续 M2/M3 无物理输出矩阵，沿用 `control-preflight-reflect` 流程。STA/CTS/DRV/PPA/Slurm 为 EDA 专用指标，本 ROS 控制任务不适用，不据此作控制结论。

事实：上一轮 regulator v9 + worker v8 已验证进程退出和 native 数值失败联动；151 个 Python、38 个新架构 C++ 用例通过。正常 no_output 有非零提案，shadow 有真实输入历史拒绝。两者均未完成 execute、M0b 或 F6。主机本轮检查无 controller/Gazebo、无不可读进程条目；817 项已声明资产无漂移，boot 未改变。

已核对本地主方案 §4.3/5.2、Ubuntu 当前共享 `build_frozen_reference` 实现和 regulator v9。profile 的 t0 为前瞻最近点对应的 profile 时间，header 戳只参与消息配对，不是任务绝对时间原点。故同内容、同配对语义重发不升 task generation 合理；暂未发现需要因此修改生产指纹的依据。clock reset/jump 清空 anchor；no_output 合成 anchor 只在启动建立，重置后的未知状态须如实保留，不能先声称自动恢复。

## 假设与风险排序

1. 时间门禁尚缺真实 callback 证据：150–200 ms 之间发生 clear/替换/配对中断时，已 ready 候选应拒绝。
2. 暂停、恢复与 reset 语义尚未成矩阵：暂停/恢复更新 schedule，reset 更新 epoch，并禁止旧候选；no_output reset 后预计需新 run 建立 anchor。
3. 新观测不等于应拒绝：普通同义重发可保留版本；观测过期、物理源时间过旧/过新、激活状态超六分量门槛则拒绝。

## A/B/C 与门禁

- **A（选择，GO）**：编写单独 create-only 诊断驱动和独立 actual MCAP/source checker，真实 regulator/worker、真实 native solve；合成输入，0 物理 publisher。分别触发 path clear、同点数替换、profile 变化、仅 path 戳改造成配对不完整、配对同义刷新、clock pause/resume、rollback/jump、odom 收据过期、源戳过旧/过新、激活 x 偏差。故障在实际成功候选登记后原 deadline+5 ms 注入，记录处理时刻；未满足该前置条件的 run 保留为失败。
- B（仅当 A 报出明确实现缺陷）：保留失败、备份原 source/bin，在原合同下最小修复并独立新编号重验；不调整门槛使失败变通过。
- C（NO-GO）：未冻结 execute 数值前接管物理输出、把诊断成功当闭环性能或严格安全证明。

验收：pre/post hash guard 无漂移；输入、job/candidate/decision 的真实 bag 数量与 source 全字段一致；生产进程身份可追溯；实际异常输入在原候选目标激活前被处理；异常区间至少 0.8 s 且拒绝原因符合合同，无旧版本/旧 epoch 激活；可恢复项有独立后续正常接纳；reset/jump 报 unknown_anchor 及无新 job，不伪造恢复。原始 source、bag、失败与 shutdown 尾部均保留，只清理本 run 拥有的进程。

GO 仅授予 A 的 no_output 诊断。暂不授予 M0b/M4/F6 或残差数据准入。
