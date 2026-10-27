# 第100批：T3-C族实施（cleanup_failed / group边界，全部通过）

## 状态
- **裁决：C12（=C1+C2）与C3全部断言通过**（`postrun/t3c_run_verdict_v1.json`）
- Driver级短run：真实四角色、隔离DDS域、ROS上下文true；无资格变化（M4/F6/P1/plant/硬实时false）

## 交付
- `implementation/t2_author/`（批91树副本+survivor fixture变体+T3 driver最小diff+cmake目标，105文件）
- `freeze_t3c.py`→bundle(340b7b2a...)+4 ELF+双registry+双table+双registration（预登记，离线预检双通过）
- `run_t3c.py`→runs/T3C_C12、runs/T3C_C3（各恰1次，原件保留）
- 文档：`documents/方案A_第100批_T3C族实施与裁决_2026-10-25.md` + `postrun/t3c_postrun_v1.md`

## 关键证据
- C1：具名cleanup_failed（fixture组非空、check_deadline 1s、梯=[INT超时,TERM]）、run判失败、survivor 2.2s内有界自灭
- C2：恰4次spawn、无restart事件、静态diff证明spawn调用点零变化
- C3负控：原厂二进制健康关闭全绿
- 已声明偏差：survivor角色recorder→fixture（批66外置二进制不可重建）；fault_injection=false+显式t3_close_injection登记

## 义务覆盖
publication_exit.09 / publication_exit.10 在当前实际消费关闭链上以真实进程覆盖

## 下一批（101）
audit_t3.py 逐条款审计（Q+C族复算）+ 批67登记表3项状态更新
