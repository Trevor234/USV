# P1 源记录与实际 typed bag 对账

- mode：shadow
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：None
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
    "count": 183,
    "p50": 0.047221,
    "p95": 0.09586,
    "p99": 0.11790620000000009,
    "max": 0.234964
  },
  "activation_jitter_ms": {
    "count": 183,
    "p50": 0.175442,
    "p95": 0.20947459999999998,
    "p99": 0.23005148000000014,
    "max": 0.289224
  },
  "solve_wall_ms": {
    "count": 161,
    "p50": 0.242638,
    "p95": 0.355878,
    "p99": 0.39936980000000016,
    "max": 0.460924
  },
  "backend_ms": {
    "count": 161,
    "p50": 0.228572,
    "p95": 0.340187,
    "p99": 0.3836266000000001,
    "max": 0.440743
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 2,
    "p50": 0.1899505,
    "p95": 0.33847794999999997,
    "p99": 0.35168039,
    "max": 0.354981
  },
  "rtf": {
    "count": 9036,
    "p50": 1.00010566015618,
    "p95": 1.00143432783972,
    "p99": 1.0032844570224038,
    "max": 1.7779146694820624
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
