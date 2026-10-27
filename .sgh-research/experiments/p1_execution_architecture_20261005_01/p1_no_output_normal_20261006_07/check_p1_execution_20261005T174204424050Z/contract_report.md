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
    "count": 52,
    "p50": 0.0929265,
    "p95": 0.142099,
    "p99": 0.14940833,
    "max": 0.151253
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1436485,
    "p95": 0.19532299999999997,
    "p99": 0.2846905600000001,
    "max": 0.304399
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.203439,
    "p95": 0.2923535,
    "p99": 0.348169,
    "max": 0.359609
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.18953,
    "p95": 0.277584,
    "p99": 0.32335349999999996,
    "max": 0.340603
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 48,
    "p50": 0.330514,
    "p95": 0.85407225,
    "p99": 0.93211594,
    "max": 0.933384
  },
  "rtf": {
    "count": 558,
    "p50": 0.9999931382429904,
    "p95": 1.001470778367038,
    "p99": 1.0296957364583526,
    "max": 1.0375288206584004
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
