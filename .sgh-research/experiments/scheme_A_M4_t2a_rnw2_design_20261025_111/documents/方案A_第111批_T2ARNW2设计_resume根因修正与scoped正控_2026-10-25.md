# 第111批：T2A-RNW2设计批——resume新窗口接纳的根因修正与scoped Epoch正控设计

日期：2026-10-25。设计批：无代码修改、无run、无资格变化。

---

## 一、根因修正（批94"架构限制"归因纠正）

**批94原文**（`t2a_resume_result.json`）："post-resume system recovery(RTF re-validation+new acceptance) takes longer than 5s drain; not a bug but a known architectural limitation"，advance_ms=779。

**批111事件流复诊**（T2A_RNW run，`regulator/source.jsonl`）：

| 事件事实 | 计数/值 |
|---|---|
| reference_epoch_committed | **1**（gen1锚定） |
| job_not_submitted：reason=task_time_reference_policy_rejected，**policy_reason=epoch_terminal** | target_tick=3 |
| worker_unusable_transition | 1（随后停推） |

**结论**：clock resume→时钟纪元bump→binding变更→reference epoch **terminal**→后续提交全部`epoch_terminal`拒绝→unusable停推。**与drain时间无关**——即使给无限时间，单代终态Epoch政策下resume后新接纳在结构上不可能。779ms是停推前残量，不是恢复耗时。

**该机制已被批102-104解决**：scoped Epoch包装层（G1-G6）允许binding变更后开新代——T2B-GEN owned run已证明同机制（版本五元组承载差异→gen2开启→job继续）。**T2-A resume NW的"架构限制"由此变为可闭合项**。

## 二、正控场景设计：T2A-RNW2

**载体**：批104树（scoped接线regulator 2a3fc697…+`t2b_gen_admission.py`准入体系）。

**时序**（全部在max_seconds=45内）：

```
t=0        启动，.05直线参考，gen1锚定+提交+激活
t≈2.0s     clock_hold（T2A族既有动作，fixture执行；保持~1200ms > pause_confirm 400ms）
t≈2.0s+    pause确认→5维版本bump（clock_epoch/schedule，T2-A silent已证语义）
           →binding变更→epoch terminal(epoch_binding_changed)+invalidate_locked同锁quiesce(G2)
           →旧候选拒（T2-A已证，复述）
t≈3.2s     clock_resume（fixture恢复发布真实推进stamp）
t≈3.2s+    RTF重验证（新鲜clock消息+ratio∈[0.95,1.05]；ClockWindow组件，~百ms级）
           →tick重排（R1已证单一调度转移）→下一tick以新binding propose
           →scoped开启gen2（G1终态在册/G2已quiesce/G3 binding因clock_epoch不同/G4静态域不变/G5 job单调/G6账本）
t≈4-8s     gen2新Job提交→Worker求解→candidate→**新窗口激活（resume后接纳，此前not_covered的正事实）**
t≈10s      健康关闭
```

**关键差异 vs 批94**：binding差异由**版本五元组（clock_epoch）**承载（path指纹不变）——与T2B-GEN owned发现同构，且G3对版本元组差异放行有组件级证据（E1/E2族）。

## 三、准入与登记

- 扩展`t2b_gen_admission.py`（或平行`t2a_gen_admission.py`）：新case `T2A-gen-resume-new-window`，动作词表=clock_hold+clock_resume（fixture既有T2A writer，参数登记固定），v3冻结合同+ordinary scope+scoped regulator SHA钉死（与T2B-GEN同模式）。
- 预检登记/单次有限/自动重试0/失败原件保留。

## 四、验收断言（登记后不得改）

| # | 断言 | 证据源 |
|---|---|---|
| R1 | pause确认+5维版本bump（clock_epoch/schedule） | regulator事件（T2-A silent语义复现） |
| R2 | gen1 terminal=epoch_binding_changed | 事件流 |
| R3 | **scoped gen2开启**（generation=2，previous reason=epoch_binding_changed，previous jobs在册） | reference_epoch_generation_opened |
| R4 | **resume后≥1个gen2 Job提交+≥1 candidate注册+≥1激活接受**（新窗口接纳正事实） | job/candidate_registration/activation事件，时间均>resume点 |
| R5 | 旧（pause前）候选拒于新窗口 | 版本门事件 |
| R6 | job id跨代严格单调 | 全job事件 |
| R7 | 健康关闭（4角色rc=0/组空/恰4 spawn） | driver_result |
| N1 | 负控引用：批94既有run（无scoped接线）epoch_terminal拒绝在册——限制的旧形态证据**不重跑** | T2A_RNW（批91树） |

## 五、不声称

- 本正控证明"scoped接线使resume后新窗口接纳可观察"；不声称原批91树（无scoped）行为改变；
- 组件/阶段资格/研究结论分别判定；M4/F6/P1/plant/硬实时false；生产B仍MANUAL+RC覆写。

## 六、实施计划

| 批 | 内容 |
|---|---|
| 112 | 准入扩展+freeze（复用批104树）+T2A-RNW2单次run+裁决 |
| 113 | 审计+批86/94登记状态更新（resume NW：not_covered→已证scoped路径+旧路径限制在册）——**全链最后一条声明的架构遗留闭合** |
