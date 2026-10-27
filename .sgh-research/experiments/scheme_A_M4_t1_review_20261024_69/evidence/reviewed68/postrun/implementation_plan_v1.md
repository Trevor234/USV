# 方案A第68批：T1 当前 Regulator 候选/参考/时钟接线组件实施计划

日期：2026-10-24（北京时间）。上游：第67批 `next_implementation_plan_v1.json`（schema `scheme-A-after-case-inventory-minimum-gap-plan-v67`）与 `case_applicability_v1.json`。

## 1. 范围与本批不做的事

本批执行 T1：把 23 项"需补当前接线"缺口全部接到**当前真实 Regulator 源码**上做组件级验证，并产出 T2 最小移交清单。不做：T2 owned 跨进程 run、T3、N3–N5、任何对 `~/USV` 生产树和 67 批 `current_author` 的写操作。`current_owned_run_count` 保持 0，`new_ros_graph` 为 0（gtest 进程内 rclcpp 仅为节点基座，不创建控制 DataWriter）。

## 2. 实施结构

- 被测源：67 批 `implementation/current_author/observer/src/shadow/regulator_owned_execute.cpp`（逐字节冻结，经 `P1_REGULATOR_SOURCE` 宏 include 编入测试可执行文件，配合既有 `P1_SHADOW_ENTRY_TEST`/`P1_C33_MATRIX_TEST` 缝与 `C33MatrixAccess` friend；不复制准入算法）。
- 新测试：`implementation/tests/test_current_candidate_reference_clock.cpp`，23 项 atom 逐项映射（candidate 8 / reference 7 / clock 6 / publication_exit 2），另补 250/400ms delayed tick 外壳组合。注册结果从真实 DiagSink JSONL 的 `candidate_registration` 事件断言；激活经真实 `admission_.take` + `activate_candidate` 路径；时钟暂停/跳tick 经真实 `tick_loop`（`own_authority_` 用 47 批冻结 v3 合同 + 17 字段合成上下文按 `context_gate("no_output")` 规则构造）。
- 前提种入：readiness/lease/liveness/ticket/anchor 在 `C33MatrixAccess::make` 中显式种入并在每用例 `scope.json` 里声明；测试文件头声明"组件级合成输入，非 owned 四角色资格"。
- 变异正控（≥3，独立目录 `evidence/t1_mutations/`）：①消费后候选可复活（去 `candidate_.reset()`）②时钟 epoch 变更不失效 ③路径变更不失效——均必须被断言捕获。
- 证据：`evidence/init_inputs_v1.json`（输入冻结+SHA）、`evidence/t1_wiring/verification_v1.json`（23 atom 逐项 {tests, statuses, driven_real_code}）、`postrun/t1_handoff_to_t2_v1.json`（最小跨进程清单）。

## 3. 完成判定（T1 done_when 原文）

所有 23 项都有实际调用及正反例结果；未覆盖的跨进程部分精确移交 T2，不由测试名代替路径。不宣称 M4 通过 / owned 资格 / 跨进程语义。

## 4. 顺序

init_inputs（冻结+git porcelain 基线）→ 编译 attempt01（失败轮保留不覆盖）→ 名义运行 → 3 变异正控 → verification + T2 移交 → final_verification（输入未变、生产树未动、porcelain 与基线一致、owned=0）→ 镜像 `/home/trevor/MPC/scheme_A_M4_t1_component_wiring_20261024_68/`。

机器可读版：`implementation_plan_v1.json`。
