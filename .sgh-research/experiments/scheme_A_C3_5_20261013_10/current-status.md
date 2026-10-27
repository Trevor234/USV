# 方案 A 当前状态：C3.5 收尾

更新日期：2026-10-13；当前作者 N11、证据 batch10。

C3.5 的当前冻结组件合同与验证已完成：14 个正式离线作业、48 项最终单元测试、14 个 readiness coherent 反例、18 个合同反例通过。新 readiness 的实际导入/来源闭包、typed/Source/CDR/GID/Storage、发布计数与关闭语义已绑定；正式 v3 固定完整输入、作业、依赖矩阵、prereg 身份并拒绝优化解释器。

收尾复核 N10 355 对/710 次读取、声明父资产 3411 个内容 pin 和 141 项 support 均一致；原业务 24 文件 diff 不变。新增 N11 11 个源文件及收尾工具、6 份登记/合同共 18 对冻结。旧资产、失败、原未提交改动继续保留；未启动新 ROS/plant/硬件。

| 层次 | 当前结果 |
| --- | --- |
| 有界组件接受 | passed，仅 `frozen-N10-synthetic-shadow-components` profile |
| B4 / M0b / B5 / M4 | unknown，qualified=false |
| 当前动态 20s / turn-mixed / pressure-recovery-failed-close | not_run |
| anchor 执行契约 | unknown；21 次正常 anchor 拒绝与尾部诊断接受不能证明执行 |
| 工程时间与域外政策 / 不可变 execute 政策 | not_run |
| Master Clock 硬界 / plant 保持 / 全调度 WCET | unknown/null |
| strict / C3_general / D1 / F6 / P1 / execute / 研究结论 | false |

当前仍基于 scheme=B DynamicMpc 路线。实际 4s 原件只出现 1 次关闭尾部非零 shadow accepted，两路 publish_success=false。下一步优先 anchor/反馈有限契约与工程时间/域外政策，再固定当前动态 recipe 并补最终版本必要失效案例，完成相应阶段合同后独立推进 M4。

入口：[本批实现报告](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/方案A_C3_5执行依赖合同与有界验证报告_2026-10-13.md)、[最终结果](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/acceptance/full_attempt03/result.json)、[最终资产核验](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/postrun/final_closure_QA.json)、[C3.6 实施计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/方案A_C3_6下一步实施计划_2026-10-13.md)。

本批过程与最终文档的 MPC 归档目录：`/home/trevor/MPC/scheme_A_C3_5_20261013_10`。完整归档、SHA 回读和保护复核以同目录 `delivery_verification.json` 为准；准备状态与已验证归档状态分别保留。
