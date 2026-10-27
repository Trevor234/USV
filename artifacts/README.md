# artifacts/

运行产物集中处。除本文件外整个目录被 `.gitignore` 忽略——里面的东西都可由代码重新生成，或只对本机有意义。

| 目录 | 来源 | 再生命令 |
|---|---|---|
| `rl_models/` | `usv_rl.train` 的检查点、`export_policy` 导出的 ONNX + manifest | 在 `usv_rl/` 下：`python -m usv_rl.train --run-name <name>`；`python -m usv_rl.export_policy --model ../artifacts/rl_models/<run>/<stage>/model.zip --thrust-scale-n 25.0` |
| `rl_runs/` | TensorBoard 事件文件（PPO `tensorboard_log`） | 同一次训练自动写出；`tensorboard --logdir ../artifacts/rl_runs`（从 `usv_rl/` 起） |

路径由 `usv_rl/usv_rl/paths.py` 统一解析，可用 `USV_ARTIFACTS_DIR` 覆盖。

**注意**：`rl_models/v5/s4_dr/policy_physical_n.manifest.json` 内的 `source_model_path` /
`source_vecnormalize_path` / `export_command` 仍写着重构前的 `usv_rl/models/...` 路径。
这是**故意不改**的：消费方（`rl_policy_node`、`collect_repair_baseline`）只校验其中的
`onnx_sha256` 等哈希字段、从不读这三个字符串；一旦改写，manifest 的 SHA-256 会变，
`.sgh-research/baselines/F*/` 里五份哈希冻结的证据就全部对不上。

## 为什么 MPC 的 `vrx_model/` 不在这里

`usv_mpc_ws/artifacts/vrx_model/` 留在原处，因为它不是纯产物：

- 生成的 `model.sdf` / `model.urdf` 内嵌**绝对路径** `file://.../hull.dae`，移动后 Gazebo 加载失败，必须重跑 `build_vrx_model`；
- `model_report.json` 被 `.sgh-research/baselines/` 的历史基线当哈希冻结的证据源引用。

详见 `docs/USV_reorg_plan_v5.md` 与 `usv_mpc_ws/docs/vrx_model_hydrodynamics.md`。
