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
    "p50": 0.055472,
    "p95": 0.0578666,
    "p99": 0.05996992,
    "max": 0.061453
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.0829675,
    "p95": 0.0934887,
    "p99": 0.1054993,
    "max": 0.107881
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.283219,
    "p95": 0.3514035,
    "p99": 0.42242599999999997,
    "max": 0.483643
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.265125,
    "p95": 0.33183850000000004,
    "p99": 0.39942,
    "max": 0.459093
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
    "p50": 0.2123525,
    "p95": 1.04372595,
    "p99": 1.12274167,
    "max": 1.139949
  },
  "rtf": {
    "count": 560,
    "p50": 0.9998376946318708,
    "p95": 1.0015242673657678,
    "p99": 1.024871422597546,
    "max": 1.030972349025141
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
