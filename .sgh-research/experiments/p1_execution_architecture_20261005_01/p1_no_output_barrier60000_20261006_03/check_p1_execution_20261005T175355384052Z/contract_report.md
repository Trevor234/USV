# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：False
- 逻辑准入：True
- 生命周期事实：False
- raw_input_recording_complete：True
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：False

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "terminal_summary_missing_or_nonterminal", "scope": "lifecycle", "stream": "worker"}
- {"code": "worker_source_counts_or_incomplete", "scope": "recording"}
- {"code": "lifecycle_fact_unknown_or_false", "scope": "lifecycle", "field": "worker_source_flush_verified"}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 3,
    "p50": 0.090992,
    "p95": 0.09219350000000001,
    "p99": 0.0923003,
    "max": 0.092327
  },
  "activation_jitter_ms": {
    "count": 3,
    "p50": 0.131764,
    "p95": 0.1482178,
    "p99": 0.14968036,
    "max": 0.150046
  },
  "solve_wall_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "backend_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
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
    "count": 70,
    "p50": 0.9998054220747887,
    "p95": 1.0059391823631236,
    "p99": 1.0072610589547983,
    "max": 1.0074362534372674
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
