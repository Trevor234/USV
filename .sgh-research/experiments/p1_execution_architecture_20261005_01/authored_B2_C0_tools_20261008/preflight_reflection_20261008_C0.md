# B2/C0 事前反思与最小执行计划

日期：2026-10-08。沿用 control-preflight-reflect 的证据锁、假设、选择和 go/no-go；本批是 ROS 无输出审计对照，EDA route/WNS/PPA 字段不适用。

## 已核实事实与待验证前提

B1 已交付：37 新 C++ 测试、63 新 Python 测试、9 实际启动拒绝、Witness 54728 bytes。最终事实 SHA `2d34adaf5c8902f8d6737a5806a70a2ab485c82218f7b1fd8461c5ac2211a88f`；2340项关闭守卫 SHA `87323918705c45cbf09cd61645a22ab174d5e3d55d5a83b2aae2c614e912159f`。当前诊断bin与source均已锁，完整C0 runtime49files具备同目录依赖。B1没有合法ROS正向采集或C0逐项比较；工具单元通过不代表source/Witness能实际对应。

真实source时刻不同：Job source.submit_commit是门前采样，Witness Submit.commit是授权存储后采样；Decision.end是业务计算尾部，Witness Tick.end包含enqueue/prepare/stop/cutoff尾部。这些不应要求相等。source dequeue顺序和DDS接收顺序也不等于跨线程commit顺序。旧normal checker/source-bag/owned/close验证维持原门，独立比较不修改其结果。

## 机制假设与选择

1. insufficient_evidence：缺少真实完整owned生命周期的source/Witness一一映射。正常10s运行可检验身份、行数和真实时刻关系。
2. flow_policy_mismatch：直接按数值相等比较不同时间端点会产生假失败；按真实源码声明包围关系，所有丢行/额外行/错身份仍拒绝。
3. tool_stability_issue：首次启用整套Witness的真实运行可能暴露工具接入问题；保留原件，工具修正必须升版本，不能运行后放宽既定政策。

| 选择 | 动作 | 判断 |
|---|---|---|
| A（选择） | 新建C0比较工具，独立测试，核验资产/主机，使用同B1 bin/diag5/512队列，五fault参数0、Witness开启，真实就绪后正常测量10s，完整owned source/bag/ledger/Witness对照 | 最小补证，支持之后R5 |
| B | 直接暂停512队列并将结构完整当作机制通过 | 独立映射未验证，不选择 |
| C | 顺便修改Decision入队失败的清槽政策 | 混合业务修复与审计对照，不属于C0 |

## 事前通过门与停止条件

工具和只读预检GO；实际运行GO以工具测试/独立审查无阻断、B1关闭清单无漂移、主机controller/Gazebo/diag/fixture及不可读命令行0为条件。本轮只执行一个预声明正常C0批次。run_id、新目录、声明10s、bin/source/worker/合同摘要、比较器版本和政策JSON在运行前归档。参数不得在运行中延长或改阈值直至通过。

- 输入为完整diag5，mode no_output，log_capacity512，test_delay/native/prepare/tick/sink_pause全0；Witness显式开启用于审计，原暂停钩子关闭。只用既有合法50Hz synthetic fixture与native worker。
- 正常测量实际达到声明10s；窗口起点需实际录制与业务就绪；wholeowned记录包含前置和收尾，不裁成10s来隐藏尾部。
- 新比较器要求每个Decision对应一条Tick，exact身份/planned/start/version/skipped/candidate输入；source.end<=Witness整拍end。每个授权Job对应一条Submit，source.submit_commit<=Witness.commit<=source.publish_start，完整原job source存在。带candidate的每个Decision对应一条Activation尝试，exact accepted/reason/ready/commit/version；拒绝也比较。
- context从driver独立锁定mode、witness=true、pause0/全部fault0、10s声明和actual assets/header；Witness不得自己提供expected身份来源。结构/固定容量/首失败与终端完整性沿用B1独立校验门。
- 原source/base/实际bag/应用及owned账本/关闭门全通过，RC0、无drop、source summary完整；新source-Witness门独立通过才C0完成。任何unknown/缺项/额外行/错误身份或时间关系保留失败。正常停机的stopping/invalidation/close phase允许；pause/overflow/sourcefailure phase不能当正常通过。
- 整个owned run physical topics端点0，normal_contract_complete/plant_acceptance_observed/execute资格均false；不运行R5、不改业务政策、不做正式冻结。

资产漂移、未拥有控制进程、审计incomplete、原source/base失败、测量不完整或owned清理失败立即阻止晋级。若失败是比较工具缺陷，先依据运行前源码政策说明原因、保存失败原件、独立修正/测试并锁新版本后才考虑重试；不能称原批通过。若是业务缺口，保留失败并另立最小修复计划。
