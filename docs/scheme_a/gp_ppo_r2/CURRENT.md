# Scheme A GP-NMPC + PPO Delivery Bundle (`scheme_A_gp_ppo_20261118_r2`)

- Created UTC: `2026-11-19T07:12:39.382328+00:00`
- Worktree: `/home/trevor/usv_scheme_a_wt` (`USV_RESEARCH_TEST_SEAMS=OFF`)
- Selected Pooled GP Snapshot: `/home/trevor/MPC/03_方案A_研发全周期产物库/08_后续研发与新批次产物/scheme_A_gp_ppo_20261118_work/gp_models/pooled/gp_snapshot.json` (`sha256=0458ff42752f45838b2c5c1f866533027d450a13ee7da087ea26378ea8f7578e`)
- Frozen PPO ONNX (`v5/s4_dr`): `/home/trevor/USV/artifacts/rl_models/v5/s4_dr/policy_physical_n.onnx` (`sha256=ff60e0f70a142dc0c76ac0e1b8e1d113bcff892d7999fad9ef41cf5a83147278`)
- Calibrated `lambda_pi`: `0.0005` (overall best on calibration split: `0.0`)
- GP Python vs C++ Parity (`gp_numeric_parity.json`): `sha256_match=True`, `max_abs_mean_diff=7.105e-14`, `ood_flags_exact_match=True`
- WP6 Closed-Loop Regression (`wp6_regression_report.json`): `all_passed=True` (['a_nominal_zero_equivalence', 'b1_surge_mismatch_gp_vs_nominal', 'b2_heldout_pooled_gp_vs_nominal', 'c_gp_hotswap_schedule', 'd1_ppo_lambda0_identity', 'd2_ppo_kill_fault_tolerance'])

## Held-Out `final_test` Summary (36 Episodes/Arm x 301 Ticks)
| Arm | Pass/Succ | CTE RMSE (m) | Heading RMSE | Speed RMSE | TV/step | Vel Res RMSE | E2E P95 (ms) | E2E Max (ms) |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|
| `nominal_nmpc` | 36/36 (36) | 0.0797 | 0.1929 | 0.1363 | 0.790 | 0.00654 | 1.739 | 4.862 |
| `oracle_nmpc` | 36/36 (36) | 0.0628 | 0.2107 | 0.1441 | 0.813 | 0.00701 | 1.844 | 2.436 |
| `gp_nmpc_r2b` | 36/36 (36) | 0.0678 | 0.2042 | 0.1438 | 0.803 | 0.00352 | 1.954 | 5.709 |
| `ppo_guided_nmpc` | 36/36 (36) | 0.0819 | 0.1924 | 0.1386 | 0.800 | 0.00664 | 1.779 | 5.656 |
| `gp_ppo_nmpc_r2b` | 36/36 (36) | 0.0686 | 0.2023 | 0.1429 | 0.822 | 0.00356 | 1.995 | 6.353 |

- Unseen `heldout_combination` mean CTE RMSE: `nominal_nmpc=0.0837m`, `oracle_nmpc=0.0664m`, `gp_nmpc_r2b=0.0724m`, `ppo_guided_nmpc=0.0855m`, `gp_ppo_nmpc_r2b=0.0714m`.

## WP8 Verification & Target Hardware Status
- x86 Learning Pytest (`5` files): rc=`0`; B2 `test_shipboard_commissioning.py` rc=`0`
- x86 Functional C++/ROS Suites (`usv_acados`, `usv_nmpc`, `usv_research_safety_cpp`): `244` functional tests, `0` failures; Linter suites: `0` failures, `22` skipped
- Live GP `shipboard_dry_run` Safety & Data Guard: `passed=True`, `anchor_known=False`, `closed_loop_verified=False`, `physical_output_enabled=False`, `dataset_builder=dry_run_not_executable_truth`
- ARM64 Target (`trevor@10.0.0.3`): status=`skipped_x86_only_policy`, ping=`None`, ssh=`False`. Production `SCHEME=B` untouched.
