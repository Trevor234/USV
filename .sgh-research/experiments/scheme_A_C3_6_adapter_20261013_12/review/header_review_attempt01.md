# C3.6 adapter 新 header 只读复审

复审 scope：N13 `command_anchor_v2.hpp`、`c36_runtime_adapter.hpp`、`owned_peer_c36_v1.hpp`；源文件 SHA/字节锁见 [机器记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/header_review_attempt01.json)。本条没有修改源码，没有运行节点、编译或授予阶段资格。

当前 kernel 已解决原始有限组件用于 shadow 的主要冲突：完整 ticket 和非零 prediction 由 import_frozen 保存；原始 anchor 必须能匹配认证 history 中的序列/数值/时间；inspect_consume 只执行最终观察复核并清 slot，不创建 Active，也不虚构调用结果；schedule generation 变化清 pending 并重置 target 排序，同时 job ID 不回退。外层 ready 仍比较完整 Job JSON。

初次读到的 Adapter cancel/close 忽略 time_order，可能清外层 job 但保留 kernel pending。主代理已修为返回 Result，且成功才清外层 job。当前三个 header scope 内没有剩余 P1/P2。

OwnedPeer 提供独立外部pins、bounded nofollow manifest + exact SHA、JSON duplicate/depth、typed canonical、启动 /proc→pidfd→/proc 与 callback实际 DataWriter GID。它明确保留 post-pin exec 连续性、continuous DDS uniqueness、close intent、endpoint exit 和 plant unknown；startup 的 graph snapshot 不能扩称连续唯一出口证明。

尚须复审真正 Node 接入点：在业务 mutex 内现取本地时间并调用adapter；Applied完整CDR之前有资源界；认证GID和旧whole-pair assess成功后才observe；保留完整payload/state/clock/lease/resource与最终commit guards；skip/invalidate/失败/close清同一slot；close request禁新任务但独立保留认证tail，session/cleanup/endpoint退出不与组件closed合并。

Adapter目前false调用结果都映射failed，未调用路start/end=0会触发shape拒绝。因此若实际 Node只导入旧whole-pair assess通过的反馈，应把支持域明确写为认证完整双路成功反馈；部分发布、失败和未调用事实可保留raw诊断并触发旧终止政策，不能据此宣称真实逐路execute adapter完成。
