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
    "p50": 0.09099,
    "p95": 0.22876515,
    "p99": 0.24106556,
    "max": 0.243995
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.21245150000000002,
    "p95": 0.3367425,
    "p99": 0.353901,
    "max": 0.356757
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.198863,
    "p95": 0.2592055,
    "p99": 0.3884765,
    "max": 0.448188
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.185314,
    "p95": 0.24557299999999999,
    "p99": 0.35334699999999997,
    "max": 0.397028
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
    "p50": 0.9999298979406246,
    "p95": 1.0016486163563139,
    "p99": 1.0295630348725477,
    "max": 1.0381351170264856
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
