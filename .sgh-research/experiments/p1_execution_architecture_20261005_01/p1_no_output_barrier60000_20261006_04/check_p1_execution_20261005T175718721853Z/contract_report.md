# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：False
- 逻辑准入：True
- 生命周期事实：False
- raw_input_recording_complete：True
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：True

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "terminal_summary_missing_or_nonterminal", "scope": "lifecycle", "stream": "worker"}
- {"code": "worker_source_counts_or_incomplete", "scope": "recording"}
- {"code": "lifecycle_fact_unknown_or_false", "scope": "lifecycle", "field": "worker_source_flush_verified"}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 12,
    "p50": 0.0572345,
    "p95": 0.0967315,
    "p99": 0.10002710000000001,
    "max": 0.100851
  },
  "activation_jitter_ms": {
    "count": 12,
    "p50": 0.109786,
    "p95": 0.12946515,
    "p99": 0.12948583,
    "max": 0.129491
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
    "count": 92,
    "p50": 0.9996228349116476,
    "p95": 1.0012693448513332,
    "p99": 1.0013866091414683,
    "max": 1.0016571114551212
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
