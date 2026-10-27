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

- {"code": "regulator_source_counts_or_incomplete", "scope": "recording"}
- {"code": "lifecycle_fact_unknown_or_false", "scope": "lifecycle", "field": "regulator_source_flush_verified"}
- {"code": "regulator_shutdown_missing", "scope": "lifecycle"}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 17,
    "p50": 0.056974,
    "p95": 0.0587682,
    "p99": 0.05906324,
    "max": 0.059137
  },
  "activation_jitter_ms": {
    "count": 17,
    "p50": 0.091502,
    "p95": 0.1171362,
    "p99": 0.12254804,
    "max": 0.123901
  },
  "solve_wall_ms": {
    "count": 17,
    "p50": 0.316521,
    "p95": 0.3875095999999999,
    "p99": 0.4866987199999999,
    "max": 0.511496
  },
  "backend_ms": {
    "count": 17,
    "p50": 0.29812,
    "p95": 0.36712939999999994,
    "p99": 0.45944747999999996,
    "max": 0.482527
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 16,
    "p50": 0.21795550000000002,
    "p95": 0.9054515,
    "p99": 1.0778350999999997,
    "max": 1.120931
  },
  "rtf": {
    "count": 217,
    "p50": 1.0000117952353131,
    "p95": 1.001748321238823,
    "p99": 1.0386523104628147,
    "max": 1.0439603996101412
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
