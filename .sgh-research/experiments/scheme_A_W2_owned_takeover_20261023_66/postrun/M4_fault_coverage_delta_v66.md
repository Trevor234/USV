# 第66批：原M4九组矩阵差量

原件保持：[M4_fault_matrix_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/M4_fault_matrix_v1.json)。本表是派生差量，完整M4/F6/P1均为false。

| 原组 | 本批增量及剩余义务 | 整组资格 |
| --- | --- | --- |
| compatibility_input | 核对F5 source/reference/mapping及logging off/on适用性；独立Fixture的输入契约与旧core逐项绑定。 | false |
| time_boundaries | 本次只实测一个严格过期点；50/150/250/400ms、等号、early ready、wrong target、delayed tick须逐案映射已有证据或补最小差集。 | false |
| native_block_and_delivery | 边界独立释放子项已通过；56的W3/W4_05需对66的投递路径给出来源/行为差异适用性判定，不能直接转移资格。 | false |
| candidate_identity_shape | failed/shape/NaN/duplicate/reordered/foreign身份的原case，需同源码准入证据与当前接线路径的适用性对账。 | false |
| task_reference | clear/single point、求解中clear/replace、same-content、path/profile不一致与new odom的未覆盖差集。 | false |
| state_clock | 旧组件/正常段证据保留；当前路径stale/future/mixed skew、pause/reset/jump/RTF差集尚待核对。 | false |
| anchor_fallback | 本次全API流间隔/跨度/rate通过；不等于五次miss、HOLD等号/之后、invalid bypass、unknown-side矩阵全闭合。 | false |
| publication_exit | 本次健康有限隔离与清理通过；50/53/56历史子项须适用性核对，cleanup_failed及清理失败禁止重启仍未实证闭合。 | false |
| actual_source_recording | 本次306条Stored及Source/Witness闭合；没有施加log queue pressure，也未替代所有原正常/故障配置。 | false |

本次只关闭原文 `worker held at native boundary until independent release` 子项。56的W3/W4投递延迟/丢弃证据保留，待来源与行为差异适用性核对；本次没有重跑它们。acados C内部挂起未覆盖，但不是原47这条要求，也不新增为本阶段前置条件。无需把九组全部改成新的长ROS运行；先核对已有证据，再跑确切缺口。
