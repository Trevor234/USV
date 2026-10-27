# P1 源记录与实际 typed bag 对账

- mode：no_output
- source/bag 契约：False
- 逻辑准入：True
- 生命周期事实：True
- raw_input_recording_complete：True
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：True

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "source_bag_identity_set", "scope": "recording", "stream": "decisions", "missing_in_bag": [1, 2], "bag_only": []}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 1, "actual": 3}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 2, "actual": 4}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 3, "actual": 5}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 4, "actual": 6}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 5, "actual": 7}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 6, "actual": 8}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 7, "actual": 9}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 8, "actual": 10}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 9, "actual": 11}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 10, "actual": 12}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 11, "actual": 13}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 12, "actual": 14}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 13, "actual": 15}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 14, "actual": 16}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 15, "actual": 17}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 16, "actual": 18}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 17, "actual": 19}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 18, "actual": 20}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 19, "actual": 21}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 20, "actual": 22}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 21, "actual": 23}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 22, "actual": 24}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 23, "actual": 25}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 24, "actual": 26}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 25, "actual": 27}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 26, "actual": 28}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 27, "actual": 29}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 28, "actual": 30}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 29, "actual": 31}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 30, "actual": 32}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 31, "actual": 33}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 32, "actual": 34}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 33, "actual": 35}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 34, "actual": 36}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 35, "actual": 37}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 36, "actual": 38}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 37, "actual": 39}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 38, "actual": 40}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 39, "actual": 41}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 40, "actual": 42}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 41, "actual": 43}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 42, "actual": 44}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 43, "actual": 45}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 44, "actual": 46}
- {"code": "decision_sequence_gap", "scope": "recording", "expected": 45, "actual": 47}

## 实测诊断指标

```json
{
  "tick_start_jitter_ms": {
    "count": 45,
    "p50": 0.108354,
    "p95": 0.21608599999999997,
    "p99": 0.23191788000000002,
    "max": 0.233908
  },
  "activation_jitter_ms": {
    "count": 45,
    "p50": 0.187661,
    "p95": 0.3404117999999998,
    "p99": 0.37150208,
    "max": 0.378561
  },
  "solve_wall_ms": {
    "count": 41,
    "p50": 0.198072,
    "p95": 0.352988,
    "p99": 0.41037620000000014,
    "max": 0.442355
  },
  "backend_ms": {
    "count": 41,
    "p50": 0.183901,
    "p95": 0.316448,
    "p99": 0.39086940000000014,
    "max": 0.423171
  },
  "publish_span_ms": {
    "count": 0,
    "p50": null,
    "p95": null,
    "p99": null,
    "max": null
  },
  "target_sim_alignment_ms": {
    "count": 40,
    "p50": 0.27597,
    "p95": 0.9747158499999994,
    "p99": 1.24779375,
    "max": 1.281402
  },
  "rtf": {
    "count": 438,
    "p50": 0.9999267946785291,
    "p95": 1.0014072831855743,
    "p99": 1.0017403522260653,
    "max": 1.0019511963911052
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
