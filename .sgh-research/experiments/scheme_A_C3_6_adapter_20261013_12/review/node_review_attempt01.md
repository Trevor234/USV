# C3.6 实际 Node 接入 v1 只读审查

本审查对比冻结 N10 和新 source bundle C36_v1；没有修改源码、运行节点或授予阶段资格。源码bundle SHA及具体点位见 [机器记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/node_review_attempt01.json)。

确认新代码保留原始完整Job/Candidate、state/clock/RTF/source-age/reference/lease/resource、Applied whole-pair和最终输入变化守卫；新GID/pidfd gate在合并anchor之前；IO读关闭文件在业务锁外；DDS Job publish仍锁外；组件close在tick/prep join后。未发现锁顺序反转。

发现四个需修订的P2，已逐项通知root先保存v1再修：

1. **registration真实完成时间**：adapter.ready和诊断写入之后仍用之前now进行finalize_ready，新增处理可跨deadline却仍accepted。
2. **资源拒绝人口**：超界Applied在计入legacy_received/callback ordinal之前返回；ready前invalidation无效果，可能后来仍满足完整人口相等。
3. **提交与最终activation完成时间**：import/inspect及新诊断发生在用于deadline/年龄/jitter/targetsim守卫的读钟之后；应在实际新授权形成前重取时间并复核。
4. **已退出owner尾包范围**：shutdown_zero字符串不足以证明零命令，例外应同时要求实际有限零命令和登记的关闭后调用时间，仍经过完整whole-pair assessment且不恢复任务许可。

这些是v1源审查发现，不是实际运行失败记录；v1合法运行是否完成由单独原始日志判断。修订版需要新source bundle及后续独立复审，不能把此记录的开放发现覆盖成已通过。
