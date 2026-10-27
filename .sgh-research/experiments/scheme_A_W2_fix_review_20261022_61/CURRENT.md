# 方案A第61批：W2修正代码复核

日期：2026-10-22。承接60号§6.1—§6.2实施结果；本批只新增独立审查、私有编译和反例，不修改60作者树与更早原件。

[详细复核与最小收口计划](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/documents/方案A_W2修正代码复核与登记前最小收口计划_2026-10-22.md)。

## 已确认推进

- 原25项测试和6个变异独立重放全部通过；删Backend接线被4项真实测试捕获。
- Worker白名单、FIFO/F_GETFL方向检查、旧hook、R7停止窗口及R8私有构建均有实际修正。
- Worker、Regulator私有编译通过，身份宏为x占位，未启动角色或登记来源。
- 成功返回后的真实policy快照一致性追加检查通过。

## 剩余缺口

- Driver W2仍落入W1观察后断言；W2汇总漏ramp/transition字段。
- W2最终谓词跳过关闭/error/目标身份约束，且隔离transition政策不一致。
- C调用失败后Boundary仍误报未调用；真正C入口前缺准备后的stop/deadline复查。
- 入口测试使用手抄名单与POSIX样例，Worker恢复旧错误时仍4/4通过。
- 实际pipe与registration/manifest绑定、FD finally清理、active/pending终局尚需收口。

新增Backend检查为1通过、3失败，RC1；失败证据保留，不能包装为整体实现complete=true。完整owned W2与正式登记未实施，不记为运行失败。

## 下一步

一次有限收尾修Driver、真实入口事实/guard、入口共用helper和终局→对应反例通过→最终构建登记→一次最小owned W2及独立对账→原矩阵差集/M4→F6→P1。

本次固定96项输入；保护历史选定110项及21个普通工作区文件，范围以evidence最终核对为准。未启动ROS/owned/硬件，离线测试实际调用acados。M4/F6/P1/plant/硬实时全部false，实船B保持MANUAL＋RC覆写。

## 本批实施（D1–D6 收口）

日期：2026-10-23。在新派生树 `implementation/w2_author/` 完成 61 号计划 §6.1–§6.2；未改 60 及更早原件。

实施记录：[W2_D1-D6收口实施记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_fix_review_20261022_61/documents/W2_D1-D6收口实施记录_2026-10-23.md)。

| 编号 | 修正 |
| --- | --- |
| D1 | 观察后断言/汇总/最终判据各加完整 W2 分支 |
| D2 | W2 专用 common 条件（其余角色与关闭全查，仅 Worker 退出码按登记）；目标 Job/ordinal 核对；缺失 `w2_exit_codes.worker` 即拒绝；隔离 transition 按登记原因允许 |
| D3 | 调用事实由真实 C 入口观察者提交，异常路径同样成立 |
| D4 | `RawBackend::set_final_guard` 在所有准备后、实际 C solve 前复查 stop 与截止 |
| D5 | 抽出 `w2_entry_contract.hpp`，Worker 与测试共用 |
| D6 | Driver 固定 pipe device/inode 并与 Worker manifest 对账；finally 全路径关闭 |

验证：

```
test_w2_native_boundary  PASS 15/15
test_w2_backend_wiring   PASS  8/8
test_w2_entry_contract   PASS 13/13
9 个变异全部 prepared 且被捕获
Driver 分支重放 5/5（合法流通过，四种错误流各自被拒）
sealed tree unchanged: True
complete: True
```

## 仍未做

- §6.3 构建与登记：本树编译用 `x` 占位身份，**不能**作为 owned 来源。
- §6.4 最小 owned W2：未运行。
- expired 生命周期仅代码走终端隔离，登记条款未写。
- `kDuplicateRelease` 仍无实际返回路径。

M4/F6/P1/plant/硬实时均为 false。未启动 ROS 图或硬件控制。
