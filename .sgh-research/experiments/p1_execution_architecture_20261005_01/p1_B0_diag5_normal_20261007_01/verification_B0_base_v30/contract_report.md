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
    "p50": 0.059305,
    "p95": 0.0637262,
    "p99": 0.07306764000000002,
    "max": 0.075534
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1288475,
    "p95": 0.16196825,
    "p99": 0.16423949,
    "max": 0.164954
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.313344,
    "p95": 0.3313685,
    "p99": 0.4446785,
    "max": 0.531476
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.29423,
    "p95": 0.31157199999999996,
    "p99": 0.41246099999999997,
    "max": 0.506411
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
    "p50": 0.4569005,
    "p95": 0.7721932499999999,
    "p99": 1.12696993,
    "max": 1.138506
  },
  "rtf": {
    "count": 559,
    "p50": 0.9999110266354557,
    "p95": 1.0014912110359444,
    "p99": 1.0036503516332573,
    "max": 1.0050421822540745
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
