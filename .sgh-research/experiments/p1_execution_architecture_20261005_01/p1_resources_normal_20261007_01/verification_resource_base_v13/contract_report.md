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
    "count": 52,
    "p50": 0.056519,
    "p95": 0.05799625,
    "p99": 0.05982292,
    "max": 0.061255
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1201065,
    "p95": 0.12447455,
    "p99": 0.13733247,
    "max": 0.138354
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.312623,
    "p95": 0.40600650000000005,
    "p99": 0.4666325,
    "max": 0.524776
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.294751,
    "p95": 0.383843,
    "p99": 0.44387849999999995,
    "max": 0.502242
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 50,
    "p50": 0.38484399999999996,
    "p95": 0.835102,
    "p99": 0.86448507,
    "max": 0.864611
  },
  "rtf": {
    "count": 559,
    "p50": 1.0000510741777557,
    "p95": 1.0014039368685537,
    "p99": 1.0197945244017812,
    "max": 1.025345248366715
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
