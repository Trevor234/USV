# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：False
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
    "count": 52,
    "p50": 0.08542749999999999,
    "p95": 0.12630399999999992,
    "p99": 0.17888041000000016,
    "max": 0.220552
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.133195,
    "p95": 0.23773789999999995,
    "p99": 0.31440868000000016,
    "max": 0.358999
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.226605,
    "p95": 0.4161945,
    "p99": 0.4333805,
    "max": 0.437263
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.210118,
    "p95": 0.39749199999999996,
    "p99": 0.41412099999999996,
    "max": 0.418273
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "rtf": {
    "count": 559,
    "p50": 0.999956809775464,
    "p95": 1.0014592030445835,
    "p99": 1.0273762477700583,
    "max": 1.0367457416588215
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
