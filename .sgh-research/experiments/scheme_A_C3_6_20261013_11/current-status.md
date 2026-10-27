# 方案 A 当前状态：C3.6-A 有限组件

更新：2026-10-13，N12 / batch11。

新增 typed command-anchor 状态机、源锁定原生历史重放和严格 decoder。最终 50 个 native 场景、22 次原件 activation predicate、10 个 coherent 副本反例、12 个 decoder 用例通过。没有新 ROS 节点或实际输出，没有修改运行控制器、旧冻结资产、失败、expected 或原业务 dirty。

补证：旧 guard 允许连续同值 history；21 次 mismatch 来自真实命令变化。尾部 accepted 位于关闭信号/末次 zero/session end 后、cleanup 完成前约 2.455ms；shadow.previous_* 是非调用默认值，不是 execution feedback。

有限组件 passed；统一 runtime anchor 契约 unknown，adapter/活 owner 认证尚未接入。工程政策及当前 20s/turn-mixed/压力/恢复/failed-close not_run；物理时钟硬界、plant 保持与全调度 WCET unknown/null。B4/M0b/B5/M4 仍 unknown、qualified=false；strict、D1、F6/P1、execute 和研究结论 false。

下一步先接入 source-linked owner/Job/逐路许可/结果/关闭 adapter，保留所有现有 guard，再登记工程政策和具体 recipe。新组件的 closed 仅指命令许可事务结算，不能当作进程或 DDS owner 已退出。

入口：[本批报告](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_20261013_11/方案A_C3_6A_anchor有限组件实现与验证报告_2026-10-13.md)、[来源与关闭审计](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_20261013_11/source_audit/anchor来源与关闭边界复核_2026-10-13.md)、[下一步计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_20261013_11/方案A_C3_6A后续实施计划_2026-10-13.md)。归档到 `/home/trevor/MPC/scheme_A_C3_6_20261013_11` 的完成与回读结果，以 `delivery_verification.json` 为准。
