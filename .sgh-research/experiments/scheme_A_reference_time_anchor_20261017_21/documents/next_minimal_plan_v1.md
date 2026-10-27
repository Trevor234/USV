# 第21批之后的固定顺序与最小实施计划

2026-10-18。先保留本批失败，下一批再实施；本文件不修改本批prereg、阈值或三个未运行档位。

## 1. 先修复观测到的输入配对重试缺口

六个运行中空拍的上一拍phase全部身份有效、已接受，匹配Applied已先到达。当时profile已刷新、path尚未刷新；匹配path在0.622–0.994ms后补齐，距原150ms截止仍至少144.732ms，但没有再次调用maybe_enqueue_controlled_locked。真实源码只从Applied和phase回调触发它；path/profile提交完成后不触发。下一tick把旧phase过期。没有对应Job到达Worker，不能把它解释为求解器拒绝。

新建源码、合同/Source身份与prereg，不改本批。最小修改位于Observer的path/profile有效提交完成处：复用现有maybe_enqueue_controlled_locked，按原mutex、原phase+Applied配对和原全部eligible守卫尝试一次；pair仍不完整、已freeze、已过期/超deadline、关闭或身份失效均不能产生Job。不得扩大150ms/200ms、不换epoch、不跳过Source age或跨版本输入守卫。具体重试调用是否需要扩展到其他eligibility依赖，先由原生反例确认，避免引入无界定时重试。

## 2. 用实际回调路径验证边界，再跑首档

新增源内原生回归：Applied→新profile→phase→匹配path；Applied→新path→phase→匹配profile；phase先于Applied；deadline内最后一个依赖补齐；重复依赖只提交一个Job；过期、任务/时钟变化、错误stamp/身份、关闭和资源异常仍拒绝。测试应穿过实际maybe_enqueue与准备提交路径，不能只复制条件写一个替代状态机。

先核对完整原生warm prefix、两个策略首拍一致、Source/合同与静态库输入；冻结新版本，再做0.05m/s/20秒。先确认≥90连续接纳、≥18秒覆盖和无运行中漏准备、完整证据与正常回收；同时保留全部原性能门。首档失败不放行后续速度。任何额外G/T对照要独立预登记为同档有限机制实验，不能把某次失败删掉或筛选最有利运行。

## 3. 连续链路成立后，再解释启动与任务目标

本批T末5秒速度近乎精确、相对首目标任务时钟的位置误差大幅减小，但峰值速度0.06472m/s，速度整窗RMSE反而0.00979774；前2秒误差已消耗完整允许SSE预算的156.94%。不能由末窗好看推导已过门，也没有证明只修重试即可达到RMSE门。

下一批并列保留整窗速度RMSE、末窗速度均值、任务时间位置误差、启动分段和实际首次控制发布时间；明确区分沿路径定速与按任务时刻到位置。若需改变起步参考或warm start，先在相同实际首状态、anchor和完整native前缀下单因素检验，再另立版本，不直接调Q/R或将原速度门换成位置门。

阶段资格仍待动态场景、噪声/延迟与时限、完整对照、真实Plant等后续证据。当前不授予dynamic20s R5/B4/M0b/B5/M4/F6/P1、正式execution或研究优越性。
