# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：True
- diagnostic_complete：True
- normal_contract_complete：False
- fault_mechanism_passed：True

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- 未发现本检查范围内的不一致。

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 54,
    "p50": 0.056705,
    "p95": 0.2290217499999998,
    "p99": 0.2617199,
    "max": 0.263082
  },
  "activation_jitter_ms": {
    "count": 54,
    "p50": 0.10833000000000001,
    "p95": 0.35266854999999997,
    "p99": 0.40338588999999997,
    "max": 0.40428
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.192253,
    "p95": 0.262181,
    "p99": 0.31310150000000003,
    "max": 0.358305
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.178897,
    "p95": 0.23753849999999999,
    "p99": 0.29625599999999996,
    "max": 0.337347
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
    "p50": 0.3815115,
    "p95": 1.1391891499999998,
    "p99": 1.3415347399999995,
    "max": 1.4651
  },
  "rtf": {
    "count": 529,
    "p50": 1.0000480219870387,
    "p95": 1.0014150674019306,
    "p99": 1.0017874311776442,
    "max": 1.002198059210104
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
