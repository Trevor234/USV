# 第46批：当前版本正常连续来源窗

沿用control-preflight-reflect/control-theory-veto/control-postrun-retro；EDA专属WNS/PPA/DEF不适用。

根因排序：1.39–42当前同源ELF只保留短正常片段/特定故障，不能拼成20s正常来源；2.前轮计划可能把完整formal no_output业务误当M0b独立必需门，原计划M0b允许shadow或无输出校准；3.当前源为owned nominal Fixture19，不是plant，turn/mixed/硬时钟界仍有独立范围限制。

A选定：先原门矩阵，派生当前42 healthy driver为一次连续正常20s source采集，ELF全部复用、81字段diag10/0.05参考/nominal19hydro/控制参数不变、hooks全0、fault许可仅保留既有shadow配置所需，实际无故障注入。保存全部prepare/tail，单列首个完整动态source job至最后job的连续20s，不拼接、不用零尾段。B重跑45已证prepare或另造完整no_output阶段拒绝；C调RMSE/RTI/阈值拒绝。

GO限实现Driver/独立检查器；源锁、所需针对验证和具体注册成立后才运行。预算：prepare20s、正常观察不超过26s、整体60s/输出128MiB，正常关闭沿用现有publisher-first流程，独立close预算15s并纳整体；单次actual run，不在原目录补跑。源码before/after、既有dirty与失败保留。

验收：连续至少20s动态Job冻结来源，实际非零动作/移动来源并非静止尾部，planar speed<=1.2、相邻source stamp gap<=250ms，所有jobs/decisions/raw/Source/Worker/Witness/actualstorage及末帧纳入独立审计。目标只补当前nominal直线有限正常窗和其差集；不自动称一般D1/plant/turn/mixed/clock硬界或B5/M0b/P1已验收。固定指纹/容差门不改，所有超门事件如实保留。
