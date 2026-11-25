# Scheme A final test

Values are episode means, with checker passes and deadline misses reported as counts.
E is the integral of squared thrust. E/m is the mean of the per-run ratios.

| Contract / arm | Runs | CTE (m) | Progress (m) | Speed RMSE (m/s) | E (N²·s) | E/m | CM (N²·s) | DM (N²·s) | DM share | Opposing | TV/step (N) | Checker | >150 / >200 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E0_base/gp_only | 36 | 0.06788 | 47.793 | 0.14375 | 4047.00 | 84.446 | 3531.57 | 515.43 | 13.32% | 7.82% | 0.8396 | 36/36 | 0 / 0 |
| E0_base/gp_v5_s4_dr | 36 | 0.06369 | 47.795 | 0.14072 | 4018.17 | 83.858 | 3505.43 | 512.75 | 13.39% | 8.11% | 0.8510 | 36/36 | 0 / 0 |
| nominal_energy | 36 | 0.07294 | 40.979 | 0.10560 | 2355.48 | 57.434 | 2074.94 | 280.55 | 12.49% | 8.89% | 0.4135 | 36/36 | 0 / 0 |
| gp_only_energy | 36 | 0.05720 | 41.760 | 0.09997 | 2536.27 | 60.705 | 2208.32 | 327.95 | 13.48% | 10.02% | 0.4441 | 36/36 | 0 / 0 |
| gp_ppo_v5_v2_energy | 36 | 0.05455 | 41.746 | 0.09984 | 2543.49 | 60.919 | 2212.86 | 330.63 | 13.57% | 10.12% | 0.4641 | 36/36 | 0 / 0 |

## Paired differences

Values are candidate minus reference, with percentile-bootstrap 95% confidence intervals. The JSON includes the two-sided Wilcoxon results and all paired metrics.

| Candidate vs reference | ΔCTE (m) | Δprogress (m) | Δspeed RMSE (m/s) | ΔE/m |
| --- | ---: | ---: | ---: | ---: |
| gp_only_energy vs E0_base/gp_only | -0.01068 [-0.01568, -0.00744] | -6.03227 [-6.30329, -5.74621] | -0.04378 [-0.05563, -0.03216] | -23.74100 [-24.92905, -22.62030] |
| gp_ppo_v5_v2_energy vs E0_base/gp_v5_s4_dr | -0.00914 [-0.01306, -0.00679] | -6.04916 [-6.26323, -5.83399] | -0.04088 [-0.05164, -0.03029] | -22.93888 [-24.04401, -21.85159] |
| gp_ppo_v5_v2_energy vs gp_only_energy | -0.00266 [-0.00377, -0.00176] | -0.01442 [-0.12288, +0.08572] | -0.00013 [-0.00099, +0.00075] | +0.21390 [+0.07374, +0.35524] |
| gp_only_energy vs nominal_energy | -0.01574 [-0.01743, -0.01377] | +0.78122 [+0.60358, +0.98240] | -0.00563 [-0.00719, -0.00402] | +3.27191 [+2.89793, +3.62276] |
| gp_ppo_v5_v2_energy vs nominal_energy | -0.01840 [-0.02034, -0.01607] | +0.76680 [+0.62427, +0.93067] | -0.00576 [-0.00763, -0.00382] | +3.48581 [+3.17061, +3.79335] |

## Deadline checks

Final-test deadline counts are reported in the summary table.

## Runtime audit

108 selected runs have zero active plant and solver deadline misses and zero PPO identity mismatch records. The selected evidence includes 2 four-worker plant-deadline replacements and 4 late receipts during shutdown. The [runtime audit](phase13_runtime_audit.json) records the exact paths for each run.

## Held-out acceptance

Each delta is the fused energy arm minus its paired reference. Percentages use the reference arm mean.

| Metric | Δ vs archived fusion | Change | Δ vs GP-only energy | Change |
| --- | ---: | ---: | ---: | ---: |
| CTE (m) | -0.00914 | -14.35% | -0.00266 | -4.64% |
| Progress (m) | -6.04916 | -12.66% | -0.01442 | -0.03% |
| Speed RMSE (m/s) | -0.04088 | -29.05% | -0.00013 | -0.13% |
| E (N²·s) | -1474.68472 | -36.70% | +7.22079 | +0.28% |
| E/m (N²·s/m) | -22.93888 | -27.35% | +0.21390 | +0.35% |
| TV/step (N) | -0.38696 | -45.47% | +0.02000 | +4.50% |

| Gate | Result | Observed |
| --- | --- | --- |
| Checker 36/36 per arm | PASS | 108/108 |
| Solver misses at 150/200 ms | PASS / PASS | 0 / 0 |
| Active plant misses | PASS | 0 after two four-worker replacements |
| PPO identity mismatches | PASS | 0 |
| E reduction ≥20% | PASS | 36.70% |
| E/m reduction ≥15% | PASS | 27.35% |
| CTE ≤0.068 m, target ≤0.064 m | PASS | 0.05455 m |
| TV/step reduction ≥30% | PASS | 45.47% |
| Lower speed RMSE | PASS | 0.14072 → 0.09984 m/s |
| Equal or greater progress and mean surge | FAIL | 47.795 → 41.746 m; 0.7543 → 0.6594 m/s |

Mean signed surge error shifted from +0.0601 to -0.0264 m/s. The reduction in the effort proxy per meter holds at the observed speeds. The experiment leaves the gain at equal throughput unresolved. The [speed tracking audit](speed_tracking_audit.json) records each pair.

## Clone replays

| Episode | Exit | Reference max | Residual max | Residual coverage | Solve max / RMS (N) |
| --- | ---: | ---: | ---: | ---: | ---: |
| [s0_ep_49_test_heldout_combination_straight](clone_verify_straight.json) | 0 | 3.4694469519536142e-18 | 2.9753977059954195e-13 | 100% | 0.0 / 0.0 |
| [s0_ep_51_test_heldout_combination_right_turn](clone_verify_turn.json) | 0 | 2.2204460492503131e-16 | 3.0375701953744283e-13 | 100% | 0.0 / 0.0 |

## Frozen inputs

The frozen E2 contract passed schema and mode validation with SHA-256 `e619f2dbd070a23e212f7980cdb61ac00df48d59165f1de7832213fdc130e5e1`.
The post-freeze [source snapshot](../meta_final/source_hashes.json) matched 229 files with SHA-256 `46cae56de88f6fe7c5855876fb05db33f4c8bb8fc8affae151f0bab104d2d71f`.
The ROS2 process checks before and after the batch were clear.
