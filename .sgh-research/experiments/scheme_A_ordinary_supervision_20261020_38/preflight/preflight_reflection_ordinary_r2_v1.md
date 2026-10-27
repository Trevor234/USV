# 一次准备顺序修复后的有界确认（r2，2026-10-20）

第一个actual run及其1841项源锁保持不变，原ordinary_terminal_notification_deadline、Worker jobs=0、Publisher late phase及terminal-close失败原样冻结。所有角色退出0。不是把无终结改写成监督成功。

独立时间线：release调用152964292ns，release调用起点至Publisher绑定317046450ns，首次Decision22 planned425594226447594，Applied完成425594408074853，晚181.627ms。既有150ms phase检查拒绝；controlled_pending_在抛出后保留，导致后续16槽队列满，没有phase ACK/job。此缺口属于受控harness准备与第一条相位，普通监督派发并未执行。

GO（附释放守卫）：只修Python driver准备顺序。启动并认证已有四角色，对Publisher/Worker/Fixture的同样完整参数查询和不可变探针在Observer启动前完成；同样的显式sensor gate和1.1s预热前移。然后启动最终Observer、保留其完整参数查询、所有五角色认证/唯一图/Reader匹配/零旧hooks/身份反例及原authorize入口。角色ELF、合同、认证模块、普通监督策略完全不改。

最终Observer源证明：native reader-ready文件写完后才启动tick线程，首tick origin=MONOTONIC+1s。因此reader-ready checked_steady_ns+1s为保守首tick下界。新driver要求从该已认证ready时刻至release请求起点<=650ms，否则在release前拒绝。此守卫不是对fsync、绑定或调度作通用WCET保证；实际仍要核对首phase在150ms合同内。旧150ms和所有业务拒绝条件保持。

A选定：以上重排后最多一个全新r2 actual run；新目录、新身份、完整新源锁。B不选：放宽150ms或清理旧pending凑通过。C不选：不改变准备机制的原样重跑。

新增等待要求真实Worker pre-native诊断已进入（已完成一次健康job后触发），再等待Source实际active终结并普通stop。该入口不是合成终结。未知通知/源锁变化或新准备守卫不满足则保留失败、关闭owned组；不再递归重复同因run。本次目标仍是有限active普通路径，lease仍只按组件证据，不授予阶段或研究结论。
