# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：True
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：True

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- 未发现本检查范围内的不一致。

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 49,
    "p50": 0.082832,
    "p95": 0.22406319999999988,
    "p99": 5.50927735999996,
    "max": 10.370978
  },
  "activation_jitter_ms": {
    "count": 49,
    "p50": 0.140069,
    "p95": 0.35631159999999984,
    "p99": 5.61955835999996,
    "max": 10.449927
  },
  "solve_wall_ms": {
    "count": 48,
    "p50": 0.19846350000000001,
    "p95": 0.25532705,
    "p99": 0.32856144000000015,
    "max": 0.376994
  },
  "backend_ms": {
    "count": 48,
    "p50": 0.1834695,
    "p95": 0.23614835,
    "p99": 0.3061112400000001,
    "max": 0.359648
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 46,
    "p50": 0.398003,
    "p95": 0.9672315,
    "p99": 1.0420107499999995,
    "max": 1.101044
  },
  "rtf": {
    "count": 559,
    "p50": 0.999969217971812,
    "p95": 1.0015376486165757,
    "p99": 1.038001042690177,
    "max": 1.0487527726935888
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
