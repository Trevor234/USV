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
    "count": 52,
    "p50": 0.08736050000000001,
    "p95": 0.10521309999999998,
    "p99": 0.1636633900000002,
    "max": 0.207121
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1283575,
    "p95": 0.16592609999999994,
    "p99": 0.2550826600000003,
    "max": 0.331141
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.201319,
    "p95": 0.24430649999999998,
    "p99": 0.334617,
    "max": 0.398886
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.186898,
    "p95": 0.2295325,
    "p99": 0.3038055,
    "max": 0.352841
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
    "p50": 0.354487,
    "p95": 0.8626821999999998,
    "p99": 0.9728551199999994,
    "max": 1.048674
  },
  "rtf": {
    "count": 558,
    "p50": 0.9999668854482886,
    "p95": 1.0014799572488096,
    "p99": 1.0324048277329843,
    "max": 1.0423214549682478
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
