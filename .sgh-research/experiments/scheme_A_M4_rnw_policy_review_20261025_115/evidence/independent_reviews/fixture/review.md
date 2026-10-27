# 114 fixture/计划子审查（只读，2026-10-25）

114目录仅 CURRENT.md 与设计文档，确无实现、测试或新owned运行。合理保留resume NW=not_covered；不能把该批称为已实施B2'+B0。

## 发现

1. **114当前新因果证据不成立。** 实际112 attempt-2的 Regulator clock Source（行355→563）为101782845634→102580295878，sim前进797450244ns，receive gap1539221548ns；全clock epoch仅0，相邻clock无任何后退。114所谓102588031850是decision seq15的publish_sim_ns[0]（行569），不是clock回调的`s`；102619942560在该流中没有出现。不能由投影域回拉推导L630的`s<sim_`触发。seq14→15的publish_sim回拉确有其事，但其历史回退守卫L844须单独归因，不能先修L630便称关闭实际故障。原始来源SHA、行号、实测及最小离线脚本见findings.json/probe.py。

2. **114“复用112 R1-R7”与B2'相矛盾。** L630仅在clock后退或>5s前进时bump epoch；L1115 pause、L631 resume只bump schedule。正确B2'在1.5s保持下不应制造clock epoch变化，binding可由schedule差异承载；112 runner L65–67却要求两代clock_epoch不同。当前attempt-2本身epoch亦从未变化。新登记须承认并检查正确版本五元组，不能保留错误断言或故意造回退满足它。

3. **112 runner不能证明R4，且缺R1/R5。** L80–84只要任意job/candidate_registration/owned_applied_publication存在便判resume_new_window_acceptance，不要求accepted_registration=true、decision.accepted=true/control_source=candidate、同一Job/代际关联、时间>resume；也不检查pause确认/旧候选拒绝。使用AST精确执行其check block的离线反例（不import runner、不subprocess、无ROS）显示：无pause、无resume、candidate明确solver_failed、publication=ramp_zero，全部9项仍PASS。必须先重写纯审计函数并用具名反例锁定，再消耗新owned run。

4. **保持期限实际并非1200ms自动截止。** Fixture L173设置hold_until_ns_但除字段定义外无读取；保持由显式resume解除。当前a1@1200/a2@2700实际保持1527323783ns。应在新登记明确duration_ms是最小时长还是自动期限、最大保持及漏resume终局；不要顺手加自动截止改变旧语义。两处writer相位可有20ms边沿，不能只把resume命令墙时长加在last_stamp上。

5. **B2'须从最后发布的配对时间映射设计，不止单调断言。** 保存最后实际发布clock的(S_last,T_last)，下次writer目标时刻T_next使用S_next=S_last+(T_next−T_last)，避免与last_target_累加双算/漏算。命令处理的hold_started_ns_未必等于T_last；仅S_last+(resume_action−hold_action)+当前publish步delta可出现±20ms相位误差。恢复首stamp>=末stamp只保证源单调，不能证明与静默期已投影的命令历史连续。需同时检查实际时钟、投影历史、RTF及完整writer事件链。ClockWindow最小有效span固定400ms；长gap后必先清空样本并等待至少400ms，B2'不使首恢复样本立即RTF有效。

6. **新fixture不能只登记新SHA便通过旧准入。** 112 admission L147–148固定FIXTURE_SOURCE_SHA_B91；B2'会改变source，需要新族准入与新版source pin（并全部bundle/Driver/ELF链再冻结），不是仅table/registration改动。admission validate_table当前不要求hold/resume精确population/order，也不消费clause值：missing_hold、resume_before_hold、all clauses false三个变体均被接受。新族应先精确有限自动机/参数域检查。

7. **M0沿用的范围要声明。** 94旧run可继续证明旧单代终态的历史限制，无须重跑；旧M0仅证明旧SHA行为。B0+B2'修改后的正常路径可先做新实现组件级M0与真实重置交错负控；如宣称新ELF无hold/resume的owned正常行为也不变，则须新身份下最小owned M0，不能把旧二进制结果标成新源码验证。

## 最小后续顺序

A. 修订设计先决条件：纠正raw clock与publish_sim混用，锁定真实L844历史回退路径；拆分B2'源连续性与B0真正clock epoch重置两个独立义务。先不要按错误L630归因改生产类。

B. 新派生副本先修纯审计/准入：R1 pause+schedule变化、R2 gen1 terminal、R3 gen2 opening、R4同一gen2 Job submit→Worker候选→accepted registration→decision accepted/control_source candidate→API/Applied/Stored全链、R5旧候选负控若本run无旧在途则诚实引用既有证据、不要求凭空发生、R6跨代Job单调、R7四角色实际spawn与关停/组空/Source/Stored；禁止自动重试、旧run不覆盖。加入本文反例。

C. B2'抽为实际writer使用的纯算术helper，测试20ms边沿、命令与timer交错、实际保持长于声明、缺resume、重复resume、时钟无回退/无双算、正常M0、同stamp/silent区别、400ms RTF重新攒窗、历史投影不回退。B0另以真实纪元变化与active output pair各侧交错证明，不引入有时限豁免去屏蔽真实authority分歧。

D. 全离线绿后，新族新pin冻结一次；单次有限owned，按事件窗口/同Job五元组审计，不因rc0或candidate存在宣称resume NW覆盖。失败原件保留、资格全false。
