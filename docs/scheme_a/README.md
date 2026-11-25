# 方案 A 研发全周期核心文档与交付清单

本目录收录从 `/home/trevor/MPC/03_方案A_研发全周期产物库` 精选合入 Git 的轻量化文档、交付清单与契约配置：

- `00_overview/`：方案 A 全周期交接计划、逐步讲解与档案全景分析。
- `reports/`：GP 残差 + PPO 融合研发技术报告，以及 Phase C2/C3 实船调试与执行契约冻结报告。
- `gp_ppo_r1/`、`gp_ppo_r2/`：GP+PPO 封签交付包的状态总结（`CURRENT.md`）、封签清单（`delivery_manifest.json`）与回读证明（`readback.json`）。
- `ppo_fusion_opt/`：PPO 融合优化执行记录（`EXECUTION_RECORD.md`）、候选评估结果及部署契约 JSON。
- `energy_opt/`：能量优化阶段评测报告（`phase1_report.md`）与冻结契约 `E1`~`E3`。
- `ARCHIVE_README.md`、`scheme_a_migration_manifest.json`：外部产物库原始目录规范与 224 项归档索引。

> 注：数 GB 级历史实验原始包（`01_P0`~`07_S2至S5`）、`runs/`、`ros_logs/`、模型检查点及压缩包（如 `scheme-a-pi-*.tar.gz`、`c2_evidence_*.tar.gz`）未纳入 Git，仍保留在外部产物库归档中。
