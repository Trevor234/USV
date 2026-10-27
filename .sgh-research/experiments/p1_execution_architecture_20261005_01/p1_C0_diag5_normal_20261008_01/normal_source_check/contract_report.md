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
    "p50": 0.0554075,
    "p95": 0.056817349999999996,
    "p99": 0.05723553,
    "max": 0.057285
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.0857235,
    "p95": 0.08922264999999999,
    "p99": 0.10186400000000001,
    "max": 0.106301
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.301223,
    "p95": 0.308924,
    "p99": 0.4127485,
    "max": 0.492142
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.283053,
    "p95": 0.2904485,
    "p99": 0.38380400000000003,
    "max": 0.468381
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
    "p50": 0.49230549999999995,
    "p95": 0.8014781499999999,
    "p99": 1.0176979599999996,
    "max": 1.091343
  },
  "rtf": {
    "count": 541,
    "p50": 0.9999307865131143,
    "p95": 1.001423693483901,
    "p99": 1.0290190449756313,
    "max": 1.0349855130526184
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
