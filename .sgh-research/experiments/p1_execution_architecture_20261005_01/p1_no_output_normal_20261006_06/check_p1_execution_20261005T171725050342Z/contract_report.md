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
    "p50": 0.0842885,
    "p95": 0.18542624999999993,
    "p99": 0.20262906,
    "max": 0.206859
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.2053895,
    "p95": 0.2997732499999999,
    "p99": 0.32675299,
    "max": 0.336826
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.20709,
    "p95": 0.295488,
    "p99": 0.3447965,
    "max": 0.358707
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.192851,
    "p95": 0.281198,
    "p99": 0.328384,
    "max": 0.340143
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 49,
    "p50": 0.342981,
    "p95": 0.9771039999999992,
    "p99": 1.1283781599999998,
    "max": 1.153366
  },
  "rtf": {
    "count": 557,
    "p50": 0.9999293315762562,
    "p95": 1.0015478264589737,
    "p99": 1.0091958410482313,
    "max": 1.0121742085801746
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
