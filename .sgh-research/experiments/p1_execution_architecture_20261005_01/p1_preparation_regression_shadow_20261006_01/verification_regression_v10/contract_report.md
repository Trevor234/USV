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
    "count": 171,
    "p50": 0.054898,
    "p95": 0.056389999999999996,
    "p99": 0.07451640000000019,
    "max": 0.094338
  },
  "activation_jitter_ms": {
    "count": 171,
    "p50": 0.140721,
    "p95": 0.2088295,
    "p99": 0.2871326000000002,
    "max": 0.300432
  },
  "solve_wall_ms": {
    "count": 169,
    "p50": 0.235778,
    "p95": 0.30751959999999995,
    "p99": 0.3582359199999998,
    "max": 0.411588
  },
  "backend_ms": {
    "count": 169,
    "p50": 0.223236,
    "p95": 0.2859842,
    "p99": 0.33663279999999995,
    "max": 0.391627
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
    "count": 8751,
    "p50": 1.00010370838945,
    "p95": 1.001349949100533,
    "p99": 1.0017575188675734,
    "max": 1.0032067526858934
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
