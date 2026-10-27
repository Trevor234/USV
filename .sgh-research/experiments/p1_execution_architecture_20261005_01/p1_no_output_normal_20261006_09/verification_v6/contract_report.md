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
    "p50": 0.088534,
    "p95": 0.20325144999999997,
    "p99": 0.25595429000000003,
    "max": 0.262748
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.143432,
    "p95": 0.32387999999999995,
    "p99": 0.36088458000000007,
    "max": 0.381816
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.198494,
    "p95": 0.26585000000000003,
    "p99": 0.312311,
    "max": 0.347776
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.185507,
    "p95": 0.250241,
    "p99": 0.29640750000000005,
    "max": 0.329247
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
    "p50": 0.4657425,
    "p95": 1.00549695,
    "p99": 1.15747038,
    "max": 1.162977
  },
  "rtf": {
    "count": 558,
    "p50": 0.9999393146303874,
    "p95": 1.0015399018396742,
    "p99": 1.0324313777040188,
    "max": 1.0398028171151892
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
