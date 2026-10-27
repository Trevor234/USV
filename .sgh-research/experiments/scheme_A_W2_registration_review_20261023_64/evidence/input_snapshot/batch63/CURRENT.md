# 方案A第63批：W2 正式构建与登记

日期：2026-10-23。冻结源码、以真实身份重建、生成 registry 与 W2 registration。**未运行 owned W2。**

主报告：[W2正式构建与登记](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_registration_20261023_63/documents/W2正式构建与登记_2026-10-23.md)。
验证发现：[登记前验证发现与修正](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_registration_20261023_63/documents/登记前验证发现与修正_2026-10-23.md)。

## 已完成

- 冻结 95 个源文件 → source bundle；以真实身份重建 Worker/Regulator/Fixture（源码 hash 前后一致）。
- 编译期身份宏写入 ELF 并回读确认（3/3）。
- 生成 registry 与 W2 registration；Driver 启动断言全链 20 项重放通过。
- 目标可达性：Job 2 走 `apply=false` 路径，`invoke` 只调用一次、ordinal=1，Boundary 命中注册目标。

## 第三轮验证修正（2 条）

| 问题 | 修正 |
| --- | --- |
| Worker 把 `read_only`/`gate_armed` 写死为 true，Regulator 却信任它 | 改为实际观测（`w2_gate_`/`w2_boundary_` 是否存在 + `F_GETFL` 复判） |
| 文档 hash 与最终 artifact 不符 | 由 `freeze_and_build_v1.json` 回填 |
| 文档声称"重放通过"但无产物 | 新增 `evidence/preflight_replay/preflight_replay_v1.json` |

## 第二轮验证修正（3 条，含 1 critical）

| 问题 | 修正 |
| --- | --- |
| `<implementation>/runs` 从未创建，Driver 非递归 mkdir 抛 FileNotFoundError | 登记生成时创建 runs 父目录 |
| Driver 读 Worker 从不发出的 `backend_terminal` 键 | 从实际 terminal 证据推导 |
| W2 在读到 boundary 结果就 break，看不到其后的 terminal 行 | 继续 drain 直到 terminal 与 active 清零都到位 |

## 登记前验证修正（四条 critical）

四条独立视角对抗性验证确认，全部已修：

| 问题 | 修正 |
| --- | --- |
| `index_sha256` 写成合同 hash | 写 `INDEX_SHA` 冻结证据标记 |
| `output` 不在 `<implementation>/runs` | 改到 `OUT / 'runs'` |
| bundle 每行缺绝对 `path` | 每行加 `path` |
| Driver 读 `guard_ns` 层级错误 | 读 `w2_result['boundary']['guard_ns']` |

## 额外修正

- Recorder provenance 由路径推导（实际为 `p1_execution_architecture_20261005_01`，原误标 attempt18）。
- Regulator W2 准入新增四个 `w2_release_*` 参数，逐项对账上报的 channel（原只查正数）。

## 已知未消费条款（不声称已验证）

- `two_deadlines` / `release_preconditions` / `channel.*`：描述性政策，实际由 `w2_release.wait_budget_ns`、Worker 的 `deadline_steady_ns` 与 `w2_entry::validate()` 的 `F_GETFL` 执行。
- `acados_runtime` hash：**真实缺口**，无运行时比较。
- `source_bundle_macro_present` 只证明 64-hex 串出现，不证明来自该宏。
- Gate `run_seq` 两侧都是字面量 1，不绑定 run_id。

## 未做

- §5.3 一次最小 owned W2 运行（需要 ROS 图与真实 acados 运行）。
- W2 审计扩展。
- M4/F6/P1/plant/硬实时均为 false。
