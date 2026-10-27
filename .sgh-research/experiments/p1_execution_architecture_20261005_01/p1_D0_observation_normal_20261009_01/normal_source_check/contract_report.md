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
    "p50": 0.0565995,
    "p95": 0.0592971,
    "p99": 0.06007901,
    "max": 0.060206
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.0922415,
    "p95": 0.0962249,
    "p99": 0.10858129000000005,
    "max": 0.120271
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.296475,
    "p95": 0.3142455,
    "p99": 0.43077449999999995,
    "max": 0.542357
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.277541,
    "p95": 0.2944685,
    "p99": 0.40681,
    "max": 0.515847
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
    "p50": 0.267451,
    "p95": 0.9118955499999999,
    "p99": 0.98951159,
    "max": 1.010096
  },
  "rtf": {
    "count": 559,
    "p50": 0.9999476840876351,
    "p95": 1.0013941465793568,
    "p99": 1.0187239097743865,
    "max": 1.0240139514537887
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
