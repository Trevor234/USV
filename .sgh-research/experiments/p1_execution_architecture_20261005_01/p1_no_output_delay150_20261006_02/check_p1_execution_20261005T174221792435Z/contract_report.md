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
    "p50": 0.0975485,
    "p95": 0.22344309999999998,
    "p99": 0.23839044,
    "max": 0.241122
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.19340400000000002,
    "p95": 0.28688745,
    "p99": 0.30617244000000005,
    "max": 0.317064
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.200336,
    "p95": 0.304339,
    "p99": 0.39035200000000003,
    "max": 0.446178
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.186613,
    "p95": 0.2908275,
    "p99": 0.3707165,
    "max": 0.426138
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
    "p50": 0.9999453234840794,
    "p95": 1.001512373899803,
    "p99": 1.0087060696666574,
    "max": 1.0107157209667421
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
