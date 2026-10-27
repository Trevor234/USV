# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：False
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：False

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "v2_source_contract_limits_or_frame_missing", "scope": "logical"}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 52,
    "p50": 0.079815,
    "p95": 0.24486215,
    "p99": 0.24834732,
    "max": 0.249657
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.17512699999999998,
    "p95": 0.31634985,
    "p99": 0.3544286900000001,
    "max": 0.384254
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.204059,
    "p95": 0.2768775,
    "p99": 0.32305649999999997,
    "max": 0.358754
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.190386,
    "p95": 0.26224099999999995,
    "p99": 0.306577,
    "max": 0.34016
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 50,
    "p50": 0.377195,
    "p95": 0.9600187499999994,
    "p99": 1.11698669,
    "max": 1.135273
  },
  "rtf": {
    "count": 557,
    "p50": 0.9999678377127351,
    "p95": 1.0014978495276785,
    "p99": 1.0057047548031177,
    "max": 1.008240094051445
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
