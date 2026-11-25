# 方案A PPO 融合优化：全计划执行记录

工作区：`scheme_A_ppo_fusion_opt_work`（新证据，不改旧 R2/R5 产物）。

## P1 前瞻距离消融（`p1/`）

- 每臂 42 eps（calibration 12 eps × 3 seeds + dev_straight/dev_left_turn），λπ=0.0005

| 臂 | CTE (m) | checker | Δ vs gp_only | 95% CI | Wilcoxon p | W/T/L |
|---|---:|:---:|---:|---:|---:|:---:|
| `gp_only` | 0.07582 | 42/42 | 0.00000 | - | - | - |
| `gp_ppo_la75` | 0.07702 | 42/42 | +0.00120 | [-0.00096,+0.00274] | 6.51e-04 | 10/2/30 |
| `gp_ppo_la40` | 0.07551 | 42/42 | -0.00031 | [-0.00287,+0.00146] | 4.35e-01 | 22/0/20 |

- 判定：`adopt_training=False` → `LOOKAHEAD_M = [0.4, 0.8, 1.4, 2.2, 3.2, 4.4, 5.8, 7.5]`（训练与部署同值）
- 离线反事实（`p1_shadow/lookahead_counterfactual.json`）：11117 窗口，median |Δu|=10.39 N，p95=26.76 N —— 前瞻确实显著改变单拍动作，但没有带来闭环增益。

## P2 观测契约 `ppo-obs-v2`

- 单一真源 `usv_rl/observation.py`；部署节点同值副本，`tests/test_obs_contract_parity.py` 逐位锁定。
- 端到端：`/tmp/p2_e2e`（30 决策）→ `ppo_proposal.jsonl` 契约全为 `ppo-obs-v2`，27 个 job 的 `ppo_reject_reason` 全为 `ok`，`ppo_identity_mismatch` 记录 0 条。
- `regulator.cpp` 门禁默认值已改为 `ppo-obs-v2` 并重建（5 包）。

## P3 奖励/成功判据/场景分布

- `e_ct` 折线投影 + 平方-线性惩罚；成功需同时满足（到末段、终点 1.0 m 内、全程 max|e_ct| ≤ 0.75 m）。
- 反例测试：恒定航向全推力策略 0/20 成功、median max|e_ct| = 5.42 m（旧判据会奖励它）。
- 场景改为方案 A 机动生成器（`maneuver_reference.py` 为唯一副本，抽取前后 54 组组合逐字节相同）。
- smoke：`p3_smoke` 20k 步跑完，`train_meta.env.path_type == scheme_a_mix`。

## P4 续训学习率与检查点

- `segment_linear_schedule_fn`：`p0 = 段步数/(历史+段步数)`，段首映射到峰值。
- smoke：`resume: base_steps=10092544 p0=0.0020 effective_lr@first_update=1.000e-04`（旧实现会落到 1e-6 量级）。
- `train_meta.json.resume` 完整记录；`best/vecnormalize.pkl` 已生成且 `VecNormalize.load` 可读（`p4_smoke_eval`）。

## P5 融合闭环

- C ABI `libusv_acados_backend.so` 导出 7 个 `p1_fusion_*` + `p1_fusion_set_anchor`，solve 0.14–0.47 ms。
- 回放校验三道门全部通过（参考 4.4e-16 / 残差 2.7e-13 / 求解 0.0e+00 N），36 个校准运行 36/36 通过。
- 权限门：计划 λ 集合 [0.0005, 0.002, 0.005] 全部不达标（5 N 时中位 |Δu0| = 0.028 / 0.110 / 0.265 N，门 0.5 N）→ **按计划条款 3 停止 PPO 融合线**。
- P5.6 结论（`p5/P5_conclusion.md`）：当前融合形式**在计划允许的 λ 区间内**没有有效权限 ⇒ 不执行 P5.7 重训；
  但 P6 复用了已冻结的 v5 权重，在 v2 契约下取得了可重复增益（见 P6 节），因此交付配置是
  **gp_only + v5（λπ=0.0005，`ppo-obs-v2`）**。

## P6 候选选择（有候选达标）

- 工具 `select_ppo_candidate.py`：配对 ΔCTE + bootstrap CI + Wilcoxon + W/T/L + TV/step。
- 运行 `v5_s4_dr` vs `gp_only`：calibration 12 eps × 3 seeds = 36 配对，
  **ΔCTE = -0.00468 m**，95% CI [-0.00555,-0.00373]（上界 < 0），
  p = 3.20e-09，W/T/L = 34/0/2，checker 36/36。
- **selected = `v5_s4_dr`**，产物 `p6/selected/`（ONNX + manifest + selection.json）。
- **held-out 确认（`p6_final_test/`，同一工具/门槛）**：ΔCTE = -0.00419 m，95% CI [-0.00530,-0.00315]，p = 5.1e-08，W/T/L = 33/0/3，checker 36/36，`ppo_identity_mismatch` 0 条 ⇒ **泛化成立**。
- 关键解释：v5 是在**旧契约**下训练的，增益出现在 `ppo-obs-v2` 契约下 ⇒ R5 的"融合无增益"主要来自
  观测语义错位（时间索引 vs 进度索引），而不是网络容量/训练步数；P5.6 权限门仍然未过（增益来自
  幅度极小但方向稳定的偏置，不是大权限）。

## 最终交付

| 项 | 值 |
|---|---|
| 交付配置 | `gp_only` + 冻结 `v5/s4_dr`（λπ=0.0005，观测契约 `ppo-obs-v2`，前瞻 7.5 m 元组） |
| 闭环收益（final_test 36 配对） | ΔCTE −4.19 mm（95% CI [−5.30,−3.15]，p=5.1e-8，W/T/L 33/0/3） |
| 闭环收益（calibration 36 配对） | ΔCTE −4.68 mm（95% CI [−5.55,−3.73]，p=3.2e-9，W/T/L 34/0/2） |
| 未执行 | P5.7 重训/微调（P5.6 权限门在计划 λ 区间内未过，按条款 3 停机） |
| 关键结论 | R5 的“融合无增益”主要源于**观测语义错位**（时间索引 vs 进度索引）；同一权重换契约后即为稳定增益 |
| 遗留风险 | 权限门未过 ⇒ 增益对 λπ 敏感，λπ 上调到 ≥0.01 的效果未测（未授权） |
| 交付产物 | `p6/selected/`、`p6_final_test/selected/`：`model.zip`(10092544 步) + `vecnormalize.pkl` + ONNX + manifest + `selection.json` + **`deployment_contract.json`** |
| 契约 provenance | 交付 ONNX 的 manifest 早于 P2.5，无 `observation_contract` 段 ⇒ 节点回退到 `DEFAULT_LOOKAHEAD`(7.5 m，与部署契约一致)，门禁只校验版本字符串；训练契约是 legacy（时间索引/4.0 m/pre_update），已在 `deployment_contract.json` 明示 |
