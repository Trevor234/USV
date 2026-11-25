# P6 候选选择（split=final_test，3 seeds x 12 eps）

| 候选 | ΔCTE (m) | 95% CI | CI 上界 | Wilcoxon p | W/T/L | CTE | TV/step | checker |
|---|---:|---:|---:|---:|:---:|---:|---:|:---:|
| `v5_s4_dr` | -0.00419 | [-0.00530,-0.00315] | -0.00315 | 5.06e-08 | 33/0/3 | 0.06369 | 0.8510 | 36/36 |

**selected**: `v5_s4_dr`

v5_s4_dr 在 36 个 final_test episode 上配对 ΔCTE=-0.00419 m（95% CI 上界 -0.00315 < 0），W/T/L=33/0/3
