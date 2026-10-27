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
    "p50": 0.1175095,
    "p95": 0.2005876,
    "p99": 0.23120134,
    "max": 0.23251
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.218968,
    "p95": 0.32995909999999995,
    "p99": 0.33885453,
    "max": 0.339516
  },
  "solve_wall_ms": {
    "count": 39,
    "p50": 0.273384,
    "p95": 0.4095054,
    "p99": 0.43784789999999996,
    "max": 0.443622
  },
  "backend_ms": {
    "count": 39,
    "p50": 0.252078,
    "p95": 0.39604300000000003,
    "p99": 0.42434167999999994,
    "max": 0.429705
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
    "count": 558,
    "p50": 0.9999735999730415,
    "p95": 1.0015776169225008,
    "p99": 1.0211709692465478,
    "max": 1.0281776841728176
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
