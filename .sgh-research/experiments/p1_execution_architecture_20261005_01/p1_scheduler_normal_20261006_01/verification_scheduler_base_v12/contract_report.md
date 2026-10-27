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
    "p50": 0.1237815,
    "p95": 0.19690464999999982,
    "p99": 0.2415189,
    "max": 0.241983
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.2293905,
    "p95": 0.31268214999999994,
    "p99": 0.35593299000000006,
    "max": 0.376461
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.205571,
    "p95": 0.2697835,
    "p99": 0.3871615,
    "max": 0.438557
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.189484,
    "p95": 0.24891249999999998,
    "p99": 0.3711485,
    "max": 0.421778
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 48,
    "p50": 0.3966,
    "p95": 1.1154505499999998,
    "p99": 1.19484585,
    "max": 1.198721
  },
  "rtf": {
    "count": 558,
    "p50": 0.999946690975446,
    "p95": 1.0015025553832446,
    "p99": 1.022119597576902,
    "max": 1.0292090392198885
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
