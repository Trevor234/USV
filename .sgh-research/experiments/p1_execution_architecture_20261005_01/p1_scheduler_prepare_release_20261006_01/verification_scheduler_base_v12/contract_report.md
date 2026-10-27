# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：True
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
    "count": 54,
    "p50": 0.0871575,
    "p95": 0.14079559999999997,
    "p99": 0.21565624999999997,
    "max": 0.229688
  },
  "activation_jitter_ms": {
    "count": 54,
    "p50": 0.13604149999999998,
    "p95": 0.28377649999999993,
    "p99": 0.35243852999999997,
    "max": 0.373479
  },
  "solve_wall_ms": {
    "count": 37,
    "p50": 0.209064,
    "p95": 0.2663501999999999,
    "p99": 0.32380380000000003,
    "max": 0.351639
  },
  "backend_ms": {
    "count": 37,
    "p50": 0.194968,
    "p95": 0.2520558,
    "p99": 0.30627692000000006,
    "max": 0.332891
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 36,
    "p50": 0.406314,
    "p95": 1.04132675,
    "p99": 1.11910015,
    "max": 1.12224
  },
  "rtf": {
    "count": 529,
    "p50": 0.9999387107642889,
    "p95": 1.001464838361394,
    "p99": 1.0018650196339252,
    "max": 1.0020209567022327
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
