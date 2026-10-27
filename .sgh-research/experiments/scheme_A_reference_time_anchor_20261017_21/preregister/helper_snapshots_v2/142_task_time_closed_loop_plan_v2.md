# 第21批最小计划与预运行反思

对照 G 使用封存第20批 projected_profile_time_v1 的完整原始记录。候选 T 为 first_target_task_time_profile_v1。首个实际成功提交 Job 的 target_sim 与几何 profile_t0 一次性固定，后续只按 target_sim 差推进。首拍 reference 必须逐数一致，不能从 Ready、传感器或事后误差拟合 epoch。

先完整重放真实 G warm prefix 至 Job 2/5/10/40；每组仅替换选中 Job 的参考时间位置，状态、anchor、前缀、N/dt、Q/R/Rd、模型、约束都保持。该证据只说明有限候选的机制，不能当闭环或研究结论。

epoch 的事务必须只在实际 Job 提交成功线性化处 commit；准备、守卫、资源或提交失败不创建 epoch。固定 task/model/config/clock/schedule 与 path/profile 内容指纹。正常重复发布更新时间戳但内容不变可以继续；时钟重置、任务/内容变化或失配终止当前 run，不能静默重锚。先限制201点、0.2秒、直线0.05m/s实际域，覆盖不足拒绝。

保留25s准备、20s测量、90s总预算与15s关闭，原完整身份、配置、Source/Storage、Witness、Worker、Applied、实际Float64、phase、独立Fossen回放与增量预算检查。末5秒均值相对误差≤5%；整窗速度RMSE≤0.007392495755251466m/s（冻结D19对应RMSE的50%）。新增任务时间位置误差和启动分段诊断只能并列报告，不能替代原门。首档失败后三档保持未运行。

已知失效模式：epoch提前绑定；每拍重锚；重复stamp被当作任务更新；旧warm状态不可重现；把时间位置追赶后的超速误判为成功。对应通过事务测试、Source逐Job独立重建、完整前缀数值核对与冻结速度门核查。旧投影策略的极小时间间隔边界仍封存，本轮实际固定0.2s域。

Go/NoGo：旧资产与工作区完整性、有限原生/判定器检查和新严格合同完成前禁止新DDS实验；通过后只允许新隔离域FastDDS/LOCALHOST1的标称首档。实际物理执行、真实Plant及阶段/研究资格始终未授予。


原生有限证据：G Job2/5/10/40完整warm前缀首控/X/U误差均0，首拍reference逐double相同。只改选中参考的T首控增加；Job10约0.08013→0.21223N/桨。这不是闭环性能证据。新合同e70beba368108d0e58d3ea2cc60ba34901166ab83c56892a3cd46a4725b51dee，rev7，offset0。原性能门与窗口保持。正常paired stamp刷新保留epoch，失配输入在已有epoch后终止本run；无静默重锚。


## 2026-10-18 修订02启动问题修复

修订01未到release/传感器启动，Observer旧内联diag6检查拒绝diag7，已冻结其全部源/二进制/运行与失败记录。修订02新源码目录，仅修正Observer构造入口，抽取同一实际调用的严格入口函数并增加原生拒绝测试；合同e70b...不变，Worker/Publisher/Fixture/Recorder复用已通过固定合同的原二进制。新预登记v2与新domain194，首档仍.05m/s/20秒与原门，性能失败仍停后续。该启动修复不赋予性能通过；失败尝试不能当有效测量。
