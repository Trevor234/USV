# 第38批预检反思（2026-10-20，Asia/Shanghai）

沿用control-preflight-reflect／control-theory-veto的证据、A/B/C与go/no-go结构。该技能EDA专用route/STA/WNS/PPA条目不适用，本批按当前Source、Witness、Linux signal与实际合同核验，不制造EDA指标。

依据：第36批Source即时认证后SIGSTOP→INT→TERM→KILL仅强制升级诊断；第37批V3实际来源交错及新Observer通过，角色组合发生一次Observer版本变化；第35批实际active/lease Source因果记录与Worker pre-native一次性1700ms入口、正常Source结构。原B4总体、M4和性能NoGo均保留。

根因与假设排序：
1. 上次显式暂停使普通退出路径不可观测。移除暂停，实际stop可按Worker自然响应退出，不能预设或要求KILL。
2. 旧桥接只认证active_watchdog。严格派发表增加worker_capability_expired，分别要求active年龄＋健康receipt lease，或实际receipt超时；拒绝未知/重复/外实例，不能用reason子串分类。
3. 最终Observer的V3参数需进入完整配置认证。复用第37批五ELF、C++/合同/认证/SourceCursor/Supervisor不变；普通配置V3=none/0、V1=none。所选实际触发单独启用Worker V2 pre-native fault，普通健康配置仍为none/0。

A（选定）：仅派生Python普通监督策略与driver。先用第35批两组冻结Source验证cause选择，必要反例验证错误身份/原因/重复/条件；使用真实owned Linux小子进程验证新单次派发、SIGINT自然退出和无重复信号，明确授权上下文为unit seed、不是ROS Source实测。旧未改Supervisor三级清理组件引用第36批，不重复。

B：先重跑历史全部V1/V2/V3。不直接补普通路径，重复成本高，不选。

C：仅移除SIGSTOP而不做原因/配置与实际数据闭环。不能得到所需证据，不选。

GO：上述组件与只读loader/CLI检查，CXX构建0。组件通过、保护通过、五ELF与完整来源锁定后，再单独预注册一个实际active run。触发沿用Worker一次性pre-native1700ms，Observer V1/V3均关闭；监督代码不调用SIGSTOP。Source终结→游标实际可见→解析→Observer/Worker完整身份配置＋Source写FD再认证→单次注册Worker stop；不等待barrier自然释放才开始stop。

实际预算：本地域196、driver45s、输出128MiB、外层55s INT加20s清理。通知到再认证观察预算250ms，认证到实际INT100ms，wait观测余量100ms；均是该次有限观察门限，不是通用WCET。合同worker grace500ms、TERM1s、kill postcheck1s分别记账，执行到哪个阶段如实记录，不提前发升级信号凑测试。

实际验收：真实active终结与前序健康命令链；真实INT且无SIGSTOP；支持的升级前缀、逐段合同wait因果顺序、五角色最终正常退出和Worker完整Source；终结后无新submit/accepted，回退tick时限及正常receiver尾部ACK、全部Stored/Fixture/GID/CDR关联。若发生KILL，资源清理仍记录，selected正常Source资格失败保留；未知通知不授予信号权，失败后原owned资源关闭仍进行。

本批只确认所选active普通路径，lease派发是冻结Source与单元证据；不声称实际lease普通监督、native C hang、所有终结原因或整组阶段通过。原冻结资产与失败逐字节保护、MPC新目录create-only交付、完整二次SHA读回。
