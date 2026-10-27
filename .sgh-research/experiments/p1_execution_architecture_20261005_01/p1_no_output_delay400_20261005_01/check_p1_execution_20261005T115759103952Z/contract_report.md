# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：False

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- 未发现本检查范围内的不一致。

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 52,
    "p50": 0.08115,
    "p95": 0.15993059999999995,
    "p99": 0.20066951000000002,
    "max": 0.207554
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1580775,
    "p95": 0.25633239999999996,
    "p99": 0.2915266700000001,
    "max": 0.31457
  },
  "solve_wall_ms": {
    "count": 26,
    "p50": 0.2661765,
    "p95": 0.36264225,
    "p99": 0.44344174999999997,
    "max": 0.469311
  },
  "backend_ms": {
    "count": 26,
    "p50": 0.25409099999999996,
    "p95": 0.34396525,
    "p99": 0.42604875,
    "max": 0.450438
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
    "p50": 0.9998905810003442,
    "p95": 1.0015774637414399,
    "p99": 1.0126248134351057,
    "max": 1.0165096861334513
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
