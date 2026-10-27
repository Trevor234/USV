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
    "count": 183,
    "p50": 0.055221,
    "p95": 0.0585021,
    "p99": 0.08417148000000002,
    "max": 0.086656
  },
  "activation_jitter_ms": {
    "count": 183,
    "p50": 0.137761,
    "p95": 0.19254290000000002,
    "p99": 0.23772108000000008,
    "max": 0.26317
  },
  "solve_wall_ms": {
    "count": 169,
    "p50": 0.239114,
    "p95": 0.30134520000000004,
    "p99": 0.36168167999999984,
    "max": 0.503168
  },
  "backend_ms": {
    "count": 169,
    "p50": 0.225988,
    "p95": 0.2839276,
    "p99": 0.3426008399999998,
    "max": 0.464077
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
    "count": 9351,
    "p50": 1.000106492758419,
    "p95": 1.0013912182723606,
    "p99": 1.0017474577459762,
    "max": 1.0048071355819008
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
