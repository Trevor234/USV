# 第21批修订02：启动入口修正与待验证事项

记录日期：2026-10-18，Asia/Shanghai。此文件保留启动修复时刻的状态；最终结果见本批后续报告。

修订01在Observer构造阶段失败，错误为“projected shadow entry requires exact diag6 policy and zero offset”。严格合同与resource函数已经支持diag7，但构造函数另有旧diag6检查。release和sensor_start均未发生，五组owned进程全部回收；这是启动实现遗漏，不是闭环速度或位置性能被拒绝。原失败源码、二进制、参数、日志、原prereg及272个author文件均冻结，未覆盖重跑。

修订02使用新authored_D1_reference_time_anchor_20261018_v21r2目录，只修正Observer实际构造入口：调用同一个纯验证函数，并对它新增20项原生检查。新函数保持shadow限定与完整固定合同校验，明确接受diag7固定时间/首提交epoch策略；旧diag6、策略缺失/篡改、错误类型、零偏移篡改、代价或deadline变化、execute权限都拒绝。

合同SHA e70beba368108d0e58d3ea2cc60ba34901166ab83c56892a3cd46a4725b51dee保持；Worker/Publisher/Fixture/Recorder继续复用已固定合同的二进制。修订02Observer共323项pure检查（其中入口20），加复用Worker84项，判定器49项通过。G完整warm-prefix与T只改选中参考的原生机制结果继续保留。

新预登记v2采用新域194，首先0.05m/s、20秒；末5秒均值≤5%相对误差，整窗RMSE≤0.007392495755251466m/s，首档未通过就不启动后三档。G/T位置诊断仅取首目标之后的实际StoredOdom；启动分段沿用0–1、1–2、2–5、5–10、10到末5秒起点、末5秒。不能替代原性能门。

此时修订02的全量旧资产复核仍在进行，尚无修订02闭环性能结果。阶段、正式执行、真实Plant和研究优越性资格未授予。
