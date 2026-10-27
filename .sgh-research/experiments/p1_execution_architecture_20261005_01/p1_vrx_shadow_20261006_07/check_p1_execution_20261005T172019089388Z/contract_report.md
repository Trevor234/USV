# P1 源记录与实际 typed bag 对账

- mode：shadow
- source/bag 契约：True
- 逻辑准入：False
- 生命周期事实：True
- raw_input_recording_complete：None
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：False

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "normal_diagnostic_has_no_solver_activation", "scope": "logical"}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 172,
    "p50": 0.055507,
    "p95": 0.0888579,
    "p99": 0.09632716999999999,
    "max": 0.09763
  },
  "activation_jitter_ms": {
    "count": 172,
    "p50": 0.119706,
    "p95": 0.1689068,
    "p99": 0.18823918999999995,
    "max": 0.211414
  },
  "solve_wall_ms": {
    "count": 166,
    "p50": 0.263905,
    "p95": 0.418325,
    "p99": 0.4863328499999998,
    "max": 0.531469
  },
  "backend_ms": {
    "count": 166,
    "p50": 0.2497865,
    "p95": 0.3989285,
    "p99": 0.46909054999999983,
    "max": 0.513222
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
    "count": 8653,
    "p50": 1.0001033235998333,
    "p95": 1.0014029301302043,
    "p99": 1.004485057595102,
    "max": 1.0084726392427628
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
