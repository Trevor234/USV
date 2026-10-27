# 第116批（S0）：证据与解释修订批

## 状态
- 无run、无代码修改、历史文件零改写；执行批115复审的S0
- 独立重算三列时间数据，与复审核定值**逐位吻合**（接收+797450244ns单调无回退/epoch全0/L630未触发；输出投影−541809040ns回退）

## 交付
- [三列证据表](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s0_evidence_20261025_116/postrun/three_column_evidence_v1.json)（attempt目录+Source SHA+登记SHA索引；两attempt登记SHA不同确认run_id不可单独取数）
- [解释修订文档](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s0_evidence_20261025_116/documents/方案A_第116批_S0证据与解释修订_2026-10-25.md)：废止批113"L630竞态/31.91ms回退"与批114"B2'+B0具体化/首stamp≥末stamp充分性"；采纳R115-01/02定论（L844同步分支）；批114三方案降为设计倾向
- 定向回归清单：两次失败run固化为L844路径/窗口不足的真实负控

## 解释现状（唯一权威）
L844同步历史回退分支（工程投影回退→清空+双known→side1恢复→[false,true]）→L1248守卫fail-closed；L630未被证据触发；B2'按S2配对映射helper单因素实施；B0独立另批；B1非默认。

## 下一批（117=S1）
纯审计函数rnw_audit_v1.py（R4=同一gen2 Job完整链：submit→候选→accepted注册→accepted Decision/control_source=candidate→API/Applied/Stored）+准入修复（动作序列/clause值/spawn前拒绝）+正反例矩阵（含两次旧run负控）
