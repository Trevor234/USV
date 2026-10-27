# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：True
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：False
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：True

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "fixture_raw_publisher_bag_count_mismatch_or_unknown", "scope": "raw_recording", "input": "clock", "fixture_published": 493, "actual_bag_count": 351}
- {"code": "fixture_raw_publisher_bag_count_mismatch_or_unknown", "scope": "raw_recording", "input": "odom", "fixture_published": 493, "actual_bag_count": 351}
- {"code": "fixture_raw_publisher_bag_count_mismatch_or_unknown", "scope": "raw_recording", "input": "imu", "fixture_published": 493, "actual_bag_count": 351}
- {"code": "fixture_raw_publisher_bag_count_mismatch_or_unknown", "scope": "raw_recording", "input": "path", "fixture_published": 11, "actual_bag_count": 7}
- {"code": "fixture_raw_publisher_bag_count_mismatch_or_unknown", "scope": "raw_recording", "input": "profile", "fixture_published": 11, "actual_bag_count": 7}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 47,
    "p50": 0.122272,
    "p95": 0.22783699999999996,
    "p99": 0.24956502,
    "max": 0.25171
  },
  "activation_jitter_ms": {
    "count": 47,
    "p50": 0.244619,
    "p95": 0.3321556999999998,
    "p99": 0.35390742000000003,
    "max": 0.359277
  },
  "solve_wall_ms": {
    "count": 41,
    "p50": 0.238684,
    "p95": 0.293054,
    "p99": 0.3331284000000001,
    "max": 0.352654
  },
  "backend_ms": {
    "count": 41,
    "p50": 0.21932,
    "p95": 0.261075,
    "p99": 0.3068718000000001,
    "max": 0.332679
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 37,
    "p50": 0.361698,
    "p95": 0.9614655999999998,
    "p99": 1.1006708800000002,
    "max": 1.158835
  },
  "rtf": {
    "count": 462,
    "p50": 0.9999511684014526,
    "p95": 1.0013854214654065,
    "p99": 1.0016990299296287,
    "max": 1.0019900473882657
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
