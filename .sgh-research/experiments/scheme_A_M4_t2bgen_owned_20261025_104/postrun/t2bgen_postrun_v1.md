# 批104 postrun：T2B-GEN owned（Stage 2）裁决

裁决：**v2 13/13全过**（`postrun/t2bgen_owned_verdict_v2.json`；POS与NEG各恰1次有效run，3次失败launch原件保留）。

## POS正控证据（runs/T2BGEN_POS）

| 断言 | 观测 |
|---|---|
| 单次换代 | generation 2开启，prev={gen1, epoch_binding_changed, first_job=1, last_job=2} |
| 两代committed绑定身份不同 | gen1(gen=1,task=2,fp=a9cb3d54…) vs gen2(gen=2,task=6,fp=a9cb3d54…) |
| replace确实执行 | path_version含2个不同指纹（.1瞬态ed1edc95…被观测）、201点、task_gen 2→4→6 |
| scoped重提交 | job_scoped_generation_resubmit×1（generation 2） |
| gen2作业继续 | job 3-10（8个） |
| 无不可用停止 | 开启后0条task_time_reference:*拒绝 |
| 健康关闭 | 4角色rc=0、组空、恰4次spawn、无restart事件 |

## NEG负控（runs/T2BGEN_NEG）

健康关闭、无generation_opened、恰1次committed(gen1)、指纹零变化——证明改动regulator的普通路径行为不变。

## 重要发现：fixture周期性重发语义

fixture的path/profile发布器周期重发**原始.05参考**，登记的path_replace(.1)是瞬态：绑定序列 (.05,task2)→(.1,task4)瞬态→(.05,task6)。gen2锚定在(.05,task6)——代际身份差异由**版本五元组**(task 2→6)承载而非指纹。裁决v1的"指纹必异"断言因此过约束（分析缺陷，run未动），v2改为绑定身份比较（generation+task_generation+指纹元组）。此发现同时印证task_reference.05"同内容重发"语义与版本递增机制的配合。

## 执行史（3次失败launch，全部保留+归因）

| Launch | 失败点 | 根因 |
|---|---|---|
| 1 | fixture rc=2 "ordinary runtime release stays disabled" | 自造scope不在m4_owned::contract冻结词表 |
| 2 | 同上 | scope手抄笔误t2**b**_boundary vs header t2_boundary（字节级） |
| 3 | regulator rc=1 "unknown diagnostic_case" | v4诊断合同强制W-hook档案——T2B-GEN是政策正控非故障注入，诊断档案不适配 |
| 4 | **成功** | ordinary scope+v3冻结合同+新准入模块钉新regulator SHA |

另有一处driver缺陷：`gen`别名为main()内局部变量（task_generation）遮蔽→UnboundLocalError；改别名t2gen（freeze后预检通过才发现，属launch0，stderr已捕获机制补齐）。

## 冻结身份（最终）

bundle f1395dcd…→重freeze后（ordinary路径）见`implementation/t2bgen_registry.json`；regulator diff 70行（scoped接线五处+include+generation字段）；driver diff语义3行（import别名+2调用点）；新准入模块`t2b_gen_admission.py`（钉新regulator SHA 2a3fc697…+批91 worker/fixture源SHA+v3合同+ordinary scope+族词表201点/.1 replace）。
