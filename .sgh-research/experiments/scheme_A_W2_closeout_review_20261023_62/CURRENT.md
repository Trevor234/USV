# 方案A第62批：W2 D1–D6收口复核

日期：2026-10-23。只新增审查、私有编译和反例；未修改61作者树、旧包或生产控制器。

[完整复核与正式登记准备计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_closeout_review_20261023_62/documents/方案A_W2_D1D6收口复核与正式登记准备计划_2026-10-23.md)。

## 已确认推进

- 当前36项测试、9个变异、Driver观察后分支5例独立重放通过。
- D1落入W1、D3真实C错误返回后事实丢失、目标D4准备期guard已修复。
- validate生产共用、Driver实际pipe/manifest对账成立；原error/其他角色坏退出/非空组已正确拒绝。
- Worker、Regulator、Fixture私有编译3/3，未执行，身份为x占位，非正式owned来源。

## 有限残余

- Driver漏Worker信号检查及隔离时序；前期Fixture失败时finally引用未初始化W2上下文。
- 非匹配Job/ordinal绕过最终guard；最终拒绝policy和最终时间字段需统一。
- 两个准备窗口测试实际在Gate前注入；删除真正final_guard后原8项仍通过。
- 参数名单helper未接生产白名单；删生产五项名字后入口suite仍13/13。
- expired异常终局仍未清active；登记条款与对应实际收尾需合并落实。

附加真实Backend检查4通过、3失败（RC1），均保留。已有修复不回退为“全部未完成”。

## 下一步

转§6.3准备；在同批最终源码冻结前完成有限小修与针对性反例回归→固定bundle/Driver/ELF/依赖和生命周期登记→一次最小owned W2及独立对账→原矩阵差集/M4→F6→P1。不新增Gate设计、C内部死锁或重复release协议门槛。

本批固定99项输入，旧包保护范围为207项选定资产，21个普通并行工作区文件保留。未启动ROS/owned/硬件；离线测试实际调用acados。M4/F6/P1/plant/硬实时全部false，实船B保持MANUAL＋RC覆写。

## 本批实施（E1–E6 收口）

日期：2026-10-23。在新派生树 `implementation/w2_author/` 完成 62 号计划 §5.1；未改 61 及更早原件。

实施记录：[W2_E1-E6收口实施记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_closeout_review_20261023_62/documents/W2_E1-E6收口实施记录_2026-10-23.md)。

| 编号 | 修正 |
| --- | --- |
| E1 | Worker 关闭信号按登记精确对账；隔离 transition 时间须不早于 verified expired；watchdog 必须为空 |
| E2 | W2 上下文与 fd 全部上提到 try 之前；登记条款在启动角色前预检 |
| E3 | final guard 先查 stop 与 Job 截止，再用 `matches` 决定是否进 gate |
| E4 | `permit_native_entry` 所有出口刷新 guard 时间；catch 重刷 policy 并保留调用事实 |
| E5 | 新增 10 项源码级契约检查；Worker 白名单合并 helper 集合；删真正 guard 与删生产名单各成变异 |
| E6 | 异常终局清 active、pending 逐 Job discard、不增 completed |

验证：

```
test_w2_native_boundary  PASS 15/15
test_w2_backend_wiring   PASS 11/11
test_w2_entry_contract   PASS 13/13
12 个变异全部 prepared 且被捕获（含 delete_real_final_guard、
  worker_whitelist_skips_helper、terminal_catch_keeps_active）
source contract 10/10；Driver 分支重放 5/5
sealed tree unchanged: True；complete: True
```

## 仍未做

- §6.3 最终构建与登记：本树编译用 `x` 占位身份，不能作为 owned 来源。
- §6.4 最小 owned W2：未运行。
- registration 字段尚未写成 JSON 并被 Driver/审计实际消费。
- `kDuplicateRelease` 仍无实际返回路径。

M4/F6/P1/plant/硬实时均为 false。未启动 ROS 图或硬件控制。
