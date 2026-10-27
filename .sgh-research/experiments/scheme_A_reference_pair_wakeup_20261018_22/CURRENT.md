# 方案A第22批当前状态（2026-10-18）

参考配对完成后的重试已实现，保留原mutex、eligible、身份、phase+Applied、epoch和150ms/200ms约束。新合同diag8，Q/R/model及性能门不变。419项pure检查、19项源内回归、57项判定器通过；另有单独预登记的真实DDS交错组件1例通过，触发一次freeze/Job并实际收包，提交时尚余143.2ms。组件worker/时钟/Ready前提仍明确设定，不是五角色受控交错资格。

五角色首档0.05m/s完成：100/100连续合法接纳，连续性门通过；102/102参考重建误差0，1167模型状态最大误差6.55e-15，五角色正常回收。实际34次retry均未成功freeze，此次未命中该成功交错，不能将所有闭环变化归因于新入口。

全窗速度RMSE0.009234946529高于0.007392495755门限，仅此性能门失败；末5秒均速0.050000000524通过。后三档NoGo，未运行。前2秒SSE已占完整允许预算140.603%，不能靠只看末窗过门。

下一步先做实际Acados启动机制单因素对照，固定真实初态/anchor/reference/Q/R/model，区分首命令等待、RTI初始化与任务目标代价；有机制证据后再新版本首档。不改本批失败。旧改动、冻结资产、所有失败和gdb证据保留。阶段、正式execution、真实Plant、研究优越性仍未授予。

[完整报告](/home/trevor/MPC/scheme_A_reference_pair_wakeup_20261018_22/documents/方案A_参考配对重试修复_验证结果与下一步_2026-10-18.md)；[下一步](/home/trevor/MPC/scheme_A_reference_pair_wakeup_20261018_22/documents/next_startup_mechanism_plan_v1.md)。QA passed仅表示归档完整性。
