# 第113批：resume NW的L1归因批（候选A关闭，唯一路径=候选B政策设计）

## 状态
归因批：无run、无代码修改。**候选A（advance=0）判定不可行**（结构性：回拉≈静默时长−advance，advance=0回拉更大；tick重排与Applied回环窗口不因参数消失）。

## 机制定论（代码行级）
1. 恢复时投影域回拉（实测seq14→15回拉541.761ms=静默1.32s−advance0.779s）+tick 3/4→0/1重排
2. Applied回环逐侧锚更新L766-767：恢复过渡窗内一侧被拒→`anchor_.known[i]=false`（单侧）
3. 一致性守卫L1248-1258：权威[true,true]vs历史[false,true]→fail-closed停摆

（批112"锚老化"表述修正为"恢复过渡窗内逐侧拒绝"）

## 下一步
候选B设计批（B1声明过渡窗/B2调度域重置比较——二选一或其它，须不削弱真实分歧的fail-closed，独立评审后实施）

## 交付
[归因文档](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_attribution_20261025_113/documents/方案A_第113批_resumeNW_L1归因与候选A判定_2026-10-25.md)
