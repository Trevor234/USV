# Scheme A GP-NMPC + PPO Delivery Bundle (`scheme_A_gp_ppo_20261117_r1`)

- Created UTC: `2026-11-18T04:45:56.444138+00:00`
- Worktree: `/home/trevor/usv_scheme_a_wt` (`USV_RESEARCH_TEST_SEAMS=OFF`)
- Selected Pooled GP Snapshot: `/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261117_work/gp_models/gp_snapshot.json` (`sha256=c1391cfd9b1c93b226e0f13ff6a907430ce880906e8bde930a407746bcea0eb9`)
- Frozen PPO ONNX (`v5/s4_dr`): `/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx` (`sha256=ff60e0f70a142dc0c76ac0e1b8e1d113bcff892d7999fad9ef41cf5a83147278`)
- Calibrated `lambda_pi`: `0.001` (overall best on calibration split: `0.001`)
- GP Python vs C++ Parity (`gp_numeric_parity.json`): `sha256_match=True`, `max_abs_mean_diff=5.684e-14`, `ood_flags_exact_match=True`
- WP6 Closed-Loop Regression (`wp6_regression_report.json`): `all_passed=True` (['a_nominal_zero_equivalence', 'b1_surge_mismatch_gp_vs_nominal', 'b2_heldout_pooled_gp_vs_nominal', 'c_gp_hotswap_schedule', 'd1_ppo_lambda0_identity', 'd2_ppo_kill_fault_tolerance'])

## Held-Out `final_test` Summary (12 Episodes x 301 Ticks)
| Arm | Pass/Succ | CTE RMSE (m) | Heading RMSE | Speed RMSE | TV/step | Vel Res RMSE | E2E P95 (ms) | E2E Max (ms) |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|
| `nominal_nmpc` | 12/12 (12) | 0.1675 | 0.2170 | 0.1930 | 1.413 | 0.00894 | 3.071 | 7.358 |
| `gp_nmpc` | 12/12 (12) | 0.1833 | 0.2634 | 0.1990 | 1.341 | 0.00400 | 9.613 | 24.712 |
| `ppo_guided_nmpc` | 12/12 (12) | 0.1568 | 0.2134 | 0.1669 | 1.225 | 0.00841 | 3.067 | 7.233 |
| `gp_ppo_nmpc` | 12/12 (12) | 0.1711 | 0.2662 | 0.2023 | 1.361 | 0.00411 | 9.650 | 15.291 |

- Unseen `heldout_combination` (6 eps) mean CTE RMSE: `nominal=0.1581m`, `gp_nmpc=0.1598m`, `ppo_guided_nmpc=0.1502m`, `gp_ppo_nmpc=0.1428m`.

## WP8 Verification & Target Hardware Status
- x86 Learning Pytest (`5` files): rc=`0`; B2 `test_shipboard_commissioning.py` rc=`0`
- x86 Functional C++/ROS Suites (`usv_acados`, `usv_nmpc`, `usv_research_safety_cpp`): `243` functional tests, `0` failures
- Live GP `shipboard_dry_run` Safety & Data Guard: `passed=True`, `anchor_known=False`, `closed_loop_verified=False`, `physical_output_enabled=False`, `dataset_builder=dry_run_not_executable_truth`
- ARM64 Target (`trevor@10.0.0.3`): ICMP ping OK=`False`, SSH BatchMode=`False` (`blocked_ssh_auth_required_no_key_or_noninteractive_auth`; stderr: `ssh: connect to host 10.0.0.3 port 22: Connection timed out`). Production `SCHEME=B` untouched.
