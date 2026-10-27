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
    "p50": 0.044733499999999995,
    "p95": 0.06114114999999999,
    "p99": 0.06235556,
    "max": 0.06248
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1033605,
    "p95": 0.11915049999999999,
    "p99": 0.12747247,
    "max": 0.131299
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.313061,
    "p95": 0.397054,
    "p99": 0.4604085,
    "max": 0.522048
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.295797,
    "p95": 0.37544900000000003,
    "p99": 0.43777900000000003,
    "max": 0.498374
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
    "p50": 0.9999993105648468,
    "p95": 1.0014013881329424,
    "p99": 1.005608663629318,
    "max": 1.0079138151987153
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
