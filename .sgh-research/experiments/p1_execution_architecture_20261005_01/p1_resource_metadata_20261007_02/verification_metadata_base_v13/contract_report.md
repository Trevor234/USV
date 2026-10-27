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
    "count": 67,
    "p50": 0.056677,
    "p95": 0.058751,
    "p99": 0.05922932,
    "max": 0.059822
  },
  "activation_jitter_ms": {
    "count": 67,
    "p50": 0.118756,
    "p95": 0.1242246,
    "p99": 0.1402263,
    "max": 0.140454
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.306911,
    "p95": 0.33163549999999997,
    "p99": 0.4357865,
    "max": 0.508869
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.289093,
    "p95": 0.30278099999999997,
    "p99": 0.411582,
    "max": 0.478408
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 49,
    "p50": 0.438179,
    "p95": 0.8360818,
    "p99": 0.9343809999999995,
    "max": 1.001149
  },
  "rtf": {
    "count": 709,
    "p50": 1.000012336790184,
    "p95": 1.0014040709092984,
    "p99": 1.030705568530049,
    "max": 1.0406768777373996
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
