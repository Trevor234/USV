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
    "p50": 0.087376,
    "p95": 0.22891819999999996,
    "p99": 0.24540307000000006,
    "max": 0.254095
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.150851,
    "p95": 0.337832,
    "p99": 0.37285539000000006,
    "max": 0.387345
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.198921,
    "p95": 0.284034,
    "p99": 0.394065,
    "max": 0.419558
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.183527,
    "p95": 0.2550575,
    "p99": 0.3653465,
    "max": 0.379832
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
    "p50": 0.3786425,
    "p95": 0.8730091999999999,
    "p99": 1.1194660399999994,
    "max": 1.267938
  },
  "rtf": {
    "count": 558,
    "p50": 0.99995849836486,
    "p95": 1.0015490269874394,
    "p99": 1.0069729585070966,
    "max": 1.0096121307106873
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
