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
    "count": 36,
    "p50": 0.086667,
    "p95": 0.25804825,
    "p99": 0.26850085,
    "max": 0.270898
  },
  "activation_jitter_ms": {
    "count": 36,
    "p50": 0.13035449999999998,
    "p95": 0.39180675000000004,
    "p99": 0.393413,
    "max": 0.394204
  },
  "solve_wall_ms": {
    "count": 32,
    "p50": 0.194495,
    "p95": 0.2995931,
    "p99": 0.33567515000000003,
    "max": 0.343994
  },
  "backend_ms": {
    "count": 32,
    "p50": 0.18058449999999998,
    "p95": 0.28644559999999997,
    "p99": 0.31803311,
    "max": 0.324518
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 31,
    "p50": 0.350893,
    "p95": 0.848283,
    "p99": 0.9695933999999999,
    "max": 1.012323
  },
  "rtf": {
    "count": 341,
    "p50": 0.9999724580955077,
    "p95": 1.001347366924834,
    "p99": 1.0016349305916756,
    "max": 1.0020214225246191
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
