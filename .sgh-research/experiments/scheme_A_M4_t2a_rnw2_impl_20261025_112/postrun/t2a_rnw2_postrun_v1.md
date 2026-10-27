# 第112批 postrun：T2A-RNW2两次尝试——resume NW根因链再精化（维持not_covered）

裁决：**目标正事实未观察到，resume NW维持not_covered**；两次尝试原件保留（`runs/T2A_RNW2_attempt1`、`runs/T2A_RNW2`），根因链精化为**两层**。

## 尝试史

| 尝试 | 表 | 结果 | 发现 |
|---|---|---|---|
| attempt-1 | a1 hold(1200ms)+a2 resume(advance 779) | 动作执行✓（terminal.json: t2_executed=[a1,a2]）、pause确认✓（schedule 1→3）、run健康关闭；但resume后仅~475ms | **driver观察循环在最后一个表动作后立即close（无settle窗）**——窗口不足 |
| attempt-2 (rev2) | +a3 driver_shutdown_request@after_grant+9000ms（观察窗~6.3s） | 窗口充足；run健康关闭；但**仍无新job/无scoped open** | **第一层阻塞：`owned_pair_consistency_failed`**（seq15/tick0）→worker_unusable+stop_requested→输入管线停摆（odometer/imu/clock事件停止、rtf_valid永久False、决策停在16） |

## 根因链（精化后，三层证据全在册）

1. **L1（本批发现，第一阻塞）**：resume携带advance（sim跳变+779ms）后，锚历史一侧`known`在暂停窗口内失效（[false,true]），权威API事实侧仍known（[true,true]）→R1接线的`owned_pair_consistency_failed`守卫（regulator L1248-1258：分歧→re-anchor→**fail-closed停摆**）。tick在resume后从未恢复提议——scoped epoch根本没有机会被评估。
2. **L2（批94/111证据）**：即使越过L1，单代终态Epoch拒绝新代提交（批94 `policy_reason=epoch_terminal`在册）。
3. **L3（批102-105已解决）**：scoped Epoch使L2可解——但L1不解则不可达。

批94"5s drain时间不足"归因正式废止：时间既非L1也非L2。

## 下一步登记候选（不调参追绿，先归因）

- **候选A（政策实验）**：advance_ms=0的resume（无跳变）是否避免锚`known`失效——需先归因锚失效是"暂停期age过期"还是"跳变本身"（读command_anchor_v2的unknown条件）。
- **候选B（政策设计）**：合法时钟跳变resume的锚re-anchor不停摆政策（L1守卫对合法resume的误报处理）——属监督政策设计，须独立评审。
- 两者均须新批登记+归因前置，不在本批继续尝试。

## 治理记录

attempt-1→2的rev2为结构性修复（driver循环终止条件，加登记终止动作），非参数追绿；attempt-2失败后按"失败即停"收束。admission rev2含缺陷记录；verdict文件attempt1/attempt2分别保存。
