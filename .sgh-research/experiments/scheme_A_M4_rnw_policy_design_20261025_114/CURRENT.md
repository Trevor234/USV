# 第114批：resume过渡政策设计批（证据完备化+三方案，推荐B2'+B0）

## 状态
设计批：无run、无代码修改。批113机制定论补齐最后一环：

## 证据完备化（新）
1. **回退时钟步实测31.91ms**（恢复首对sim 102588031850 < 静默前末stamp 102619942560）——fixture冻结基+advance算术缺陷
2. 回环锚事件=0——owned锚更新全在`apply_channel_result`
3. **竞态签名完全吻合**：时钟线程L630（s<sim_合法触发）重置{false,false}恰落入publish逐侧提交锁间隙→[false,true]
4. **非对称重置=根源**：L630重置历史锚不重置命令权威锚→合法纪元变更必然分歧→守卫按设计停摆

## 三方案
- **B2'（推荐）**：fixture恢复算术改"末stamp+实际保持墙时长"，消除回退步
- **B0（推荐）**：L630经change_version协议对称通知own_authority_——关闭竞态类
- B1（过渡窗）：语义最弱，仅兜底不单独用

## 实施轮廓（批115，待批准）
批112树+B2' fixture变体+B0 regulator最小diff→新族登记rev3→复用R1-R7断言+新增两条→单次运行

## 交付
[设计文档](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_policy_design_20261025_114/documents/方案A_第114批_resume过渡政策设计_2026-10-25.md)
