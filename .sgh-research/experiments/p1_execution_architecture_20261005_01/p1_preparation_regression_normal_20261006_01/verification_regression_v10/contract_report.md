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
    "count": 67,
    "p50": 0.074268,
    "p95": 0.14565909999999999,
    "p99": 0.2078669000000001,
    "max": 0.228977
  },
  "activation_jitter_ms": {
    "count": 67,
    "p50": 0.141231,
    "p95": 0.2835891,
    "p99": 0.33516948000000024,
    "max": 0.375048
  },
  "solve_wall_ms": {
    "count": 49,
    "p50": 0.205574,
    "p95": 0.32430139999999974,
    "p99": 0.34880212,
    "max": 0.351613
  },
  "backend_ms": {
    "count": 49,
    "p50": 0.1914,
    "p95": 0.2959247999999999,
    "p99": 0.33188512000000003,
    "max": 0.332392
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 46,
    "p50": 0.3306825,
    "p95": 0.94976125,
    "p99": 1.2244356999999997,
    "max": 1.269388
  },
  "rtf": {
    "count": 537,
    "p50": 1.0000087420537527,
    "p95": 1.0014722895572867,
    "p99": 1.6358294214261024,
    "max": 1.8019878845720525
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
