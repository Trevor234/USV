# 第126批：离线整改执行（E00—E12）

2026-10-26。依据第125批严格执行计划。**本批在执行中，每步独立验收。**

## 状态

| 步骤 | 状态 | 说明 |
|---|---|---|
| E00 冻结输入、派生作者树、执行约束 | **PASS** | 100 输入 pin、9 组件谱系、1355 原件零写入、89 case 锁定 |
| E01 Q2 悬空捕获与逐事件记账 | **PASS** | 5/5 case、ASAN 干净、变异被捕获、旧 350/303 重复被点名 |
| E02 RNW 纯审计四维度 | **PASS** | RNW3 Job7/seq18 正例成立；11 反例全拒；112 两次失败不获 R4 |
| E03 硬准入唯一入口 | **PASS** | 9 规则 + 9 Driver 入口用例；所有负例 popen=0；单一规则模块对象 |
| E04 105 审计恒真 | NOT_STARTED | |
| E05 Epoch Proposal 身份 | NOT_STARTED | |
| E06 模型事务状态机 | NOT_STARTED | |
| E07 B2 整数边界 | NOT_STARTED | |
| E08 T3 声明收敛 | NOT_STARTED | |
| E09 组合回归复判 | NOT_STARTED | |
| E10 创新登记簿修订 | NOT_STARTED | |
| E11 三份评审包 | NOT_STARTED | |
| E12 封存与 MPC 交付 | NOT_STARTED | |

机器可读状态：`postrun/step_status_v1.json`。

## 不变式（全程）

- 冻结批次与生产树只读。E00 门禁已证明：B124 登记的 1355 个受保护文件 0 缺失 0 变更；工作区 22 个普通未提交文件与 23 行 porcelain 未变。
- 每步只改本步白名单（`evidence/inputs/allowed_changes.json`），越界即 FAIL_STOP。
- 不初始化 ROS 上下文、不建 DDS 图、不启动四角色/survivor、不发进程信号、不做 owned 运行。
- 预算与尺寸沿用 v3 合同 pin `19d6962b…c23a`（实测一致）。
- 阶段资格全 false：M4 / F6 / P1 / plant / hard_realtime = false；生产 B 维持 MANUAL+RC 覆写。

## 基线事实

- 包路径：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126`
- 主作者树：B119 `implementation/t2_author` → `implementation/author/`（108 文件，逐字节一致）
- Q2 harness：B99 → `implementation/tests/test_t3_queue_pressure.cpp`（其两个头文件在 B99/B119 逐字节相同，已证明）
- 模型事务层：B108 → `implementation/standalone/model/`
- 审计器：B117 `rnw_audit_v1.py` / `rnw_admission_v2.py`、B105 `audit_t2bgen.py` → `implementation/audit/`

## 证据约定

每步四件套：`evidence/E##/attemptNN/{commands,verification}.json`、`postrun/E##_step_result.json`、本文件。四维度分开报：observed_facts / run_accepted / coverage / stage_qualified。

## 下一步

E04：105 审计的恒真比较（`clause()` 参数错位、绑定比较拿常量 1/2 当差异）改为严格 bool + 真实 binding 比较，并对 104 POS/NEG 重判。
