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
    "p50": 0.057554,
    "p95": 0.10981125,
    "p99": 0.12122115000000004,
    "max": 0.128838
  },
  "activation_jitter_ms": {
    "count": 52,
    "p50": 0.1152475,
    "p95": 0.16790295,
    "p99": 0.1748634,
    "max": 0.176067
  },
  "solve_wall_ms": {
    "count": 51,
    "p50": 0.196531,
    "p95": 0.2463165,
    "p99": 0.31369,
    "max": 0.349795
  },
  "backend_ms": {
    "count": 51,
    "p50": 0.182627,
    "p95": 0.22793,
    "p99": 0.29716549999999997,
    "max": 0.330988
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
    "p50": 0.328714,
    "p95": 1.0051516499999995,
    "p99": 1.2392281699999999,
    "max": 1.304872
  },
  "rtf": {
    "count": 558,
    "p50": 1.0000410074017692,
    "p95": 1.0015384383988903,
    "p99": 1.0198651293352352,
    "max": 1.0255848163273977
  }
}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
