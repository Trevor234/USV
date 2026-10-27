# 第41批复盘

假设A通过：将ordinary监控移到pause ACK后立即进入，真实lease终结后原Source认证和唯一owned stop满足原预算；原普通策略无需修改。Worker正常INT退出后才恢复callback，旧实例在pidfd guard被拒绝，业务未改。六项独立审计与14个actual-copy负例通过。

主要机制是flow_policy_mismatch的调用次序差集得到解决，旧900ms观察继续按其原用途冻结。没有新的控制模型或性能结论；Source receipt新鲜与源发送新鲜度分账。

下一步只补精确41 lease后全新身份healthy恢复和正常资源闭合。confidence=medium、impact=high、cost=low、risk=low（有界本地shadow）。STOP条件：新身份、旧组退出、新gate/健康候选或正常tail任一缺失；保留实际证据，不追加同故障刺激、不放宽时限。

依赖经验：完整准备先于业务；旧Source原因必须精确且paired；认证后方可唯一dispatch；快速stop不强制KILL；已退出guard前不承诺全payload；组件、诊断正常资源关闭、正常业务与阶段分别核验。审核超时按明确一次重试规则处理且保留事件，不作控制失败解释。EDA route/STA/WNS/PPA不适用。
