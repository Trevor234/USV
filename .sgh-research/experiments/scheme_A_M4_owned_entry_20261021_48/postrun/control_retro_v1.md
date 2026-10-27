# 第48批复盘

主机制flow_policy_mismatch：把旧Recorder完整就绪屏障直接放到新Writer创建之前，产生依赖环。实际0控制API，不能解释为NMPC拒绝。新变量应为process-only认证→endpoint创建→full Recorder/源认证→一次grant的分阶段生命周期；不增加等待预算。

下一修复confidence高、impact高、cost中、risk中，要求真实进程pin与full-ready分开验证，full-ready之前禁止API。允许单个独立新注册确认，旧run不重试。STOP沿原owned/时序/记录/退出规则。假设及经验：bootstrap实际锚点；原生GID格式；强typed完整配置；零请求/进程退出不当plant证明；原来证据不能替代新执行分支。EDA指标不适用。
