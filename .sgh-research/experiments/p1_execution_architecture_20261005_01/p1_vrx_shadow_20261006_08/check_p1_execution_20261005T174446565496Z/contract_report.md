# P1 源记录与实际 typed bag 对账

- mode：shadow
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：None
- activation_source_contract_complete：False
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
    "count": 184,
    "p50": 0.0568825,
    "p95": 0.08395024999999999,
    "p99": 0.10998156999999995,
    "max": 0.141308
  },
  "activation_jitter_ms": {
    "count": 184,
    "p50": 0.16810799999999998,
    "p95": 0.2389629,
    "p99": 0.26776615,
    "max": 0.279986
  },
  "solve_wall_ms": {
    "count": 170,
    "p50": 0.2446685,
    "p95": 0.3114510499999999,
    "p99": 0.44251528,
    "max": 0.4923
  },
  "backend_ms": {
    "count": 170,
    "p50": 0.2285525,
    "p95": 0.2937517,
    "p99": 0.42436840000000003,
    "max": 0.45707
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
    "count": 9400,
    "p50": 1.0001057886675446,
    "p95": 1.0013497389341526,
    "p99": 1.0017344633503091,
    "max": 1.0033823007240998
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
