# 第111批：T2A-RNW2设计批（resume根因修正+scoped正控设计）

## 状态
设计批：无代码修改、无run、无资格变化。

## 关键发现（根因修正）
批94事件流复诊：resume后`job_not_submitted: policy_reason=epoch_terminal`（tick3）+仅1次commit+unusable停推——**"5s drain架构限制"归因错误，真因=单代终态Epoch政策**（与时间无关）。该机制已被批102-104 scoped Epoch解决→**T2-A resume NW从"架构限制"变为可闭合项**。

## 交付
[设计文档](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_design_20261025_111/documents/方案A_第111批_T2ARNW2设计_resume根因修正与scoped正控_2026-10-25.md)：
- 根因修正表（事件证据）+ T2A-RNW2时序设计（批104树，clock_hold→resume→RTF重验证→scoped gen2→新窗口激活）
- binding差异由版本五元组（clock_epoch）承载——与T2B-GEN owned发现同构
- 7条验收断言+负控引用（批94旧证据不重跑）
- 实施计划：112实施→113审计+登记更新（全链最后一条声明架构遗留闭合）

## 下一批（112）
准入扩展（clock_hold/resume词表）+freeze（批104树复用）+T2A-RNW2单次run+裁决
