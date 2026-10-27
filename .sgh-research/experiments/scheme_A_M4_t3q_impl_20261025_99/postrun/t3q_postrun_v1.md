# 批99 postrun：T3-Q族裁决汇总

裁决：**5/5 case 通过**（verdict v2 passed=true；attempt-1 的3个case仅因登记计数缺陷判失败，断言本身在两次attempt均全过，原件保留于 `t3q_run_verdict_v1.json` 与 `runs/<case>/`）。

## 逐case证据（attempt-2 为准；Q1d/Q4 为 attempt-1）

| Case | 运行目录 | 断言数 | 关键观测 |
|---|---|---|---|
| T3-Q1d | runs/T3-Q1d | 14/14 | accepted=513(=capacity+1)、rejected=2048(=K)、peak=512、generated=2561=513+2048、publisher.calls=513、QueueOverflow=1、SourceFailure=1、normal_source_complete=false |
| T3-Q1r | runs/T3-Q1r_r2 | 14/14 | generated=2560、dropped=2047、emitted=513、peak≤512(=512)、QueueOverflow=1、balance成立 |
| T3-Q2 | runs/T3-Q2_r2 | 14/14 | 4线程×768=3072次、accepted=513、dropped=2559、peak=512、QueueOverflow恰1次（原子exchange）、无死锁/崩溃、join有界(≈1.07s总时长) |
| T3-Q3 | runs/T3-Q3_r2 | 16/16 | 溢出后drain完整：513事件逐条恰一次(unique=513)、file行=513+1、normal_source_complete=false |
| T3-Q4 | runs/T3-Q4 | 8/8 | 负控：dropped=0、failed=false、无溢出相位、normal_source_complete=true、100条全emit |

## 结论范围

- 义务 `actual_source_recording.03`（log queue pressure及声明drop）的**组件级**范围已证：真实DiagSink enqueue/drain路径在有界自然压力下拒绝有界、计数可对账、溢出终态不伪造正常完成；负控证明判定非构造性必败。
- "Stored"以publish seam为交付观测，**不声称**四角色Stored对账（批98登记原文）。
- ROS_context=false；stage/execute/research全false；M4/F6/P1/plant/硬实时不变。

## 缺陷与修正记录

- **登记计数缺陷**（revision 2）：racing用例中共享balance助手二次发射`generated_equals_attempts`，登记清单13/13/15 vs 实际14/14/16。仅计数修正，断言名/语义/激励/binary SHA/bundle SHA零变化。attempt-1失败原件保留（verdict v1 + runs/T3-Q1r|T3-Q2|T3-Q3），受影响3 case各恰1次重跑至`_r2`目录，自动重试仍为0（单次修正性attempt，已记录）。

## 冻结身份

- bundle fa77feeed4e3ebf4...（104文件）、binary 011b1d46ea3f96e3...、g++ 13.3.0、registry/registration见 `implementation/t3q_registry.json`、`implementation/T3Q_registration.json`(rev2)。
