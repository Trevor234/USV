# P1 源记录与实际 typed bag 对账

- mode：unknown
- source/bag 契约：False
- 逻辑准入：False
- 生命周期事实：False
- raw_input_recording_complete：unknown
- activation_source_contract_complete：False
- diagnostic_complete：False
- normal_contract_complete：False
- fault_mechanism_passed：False

no_output/shadow 的源记录一致不证明物理执行合同。故障机制结果与正常合同分列；所有时间统计是有限源样本，不是最坏实时证明。plant 接纳、真实力、物理原子性、精确 plant 步长和 GP eligibility 均未证明。

## 问题

- {"code": "reader_or_source_error", "scope": "recording", "message": "[Errno 2] No such file or directory: '/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/p1_vrx_shadow_20261006_03/regulator_source.jsonl'"}

## 实测诊断指标

```json
{}
```

完整计数、来源/原始 bag/合同/检查器 SHA256、读取前后哈希与 component error 见同目录 contract_report.json。原始输入不改写。
