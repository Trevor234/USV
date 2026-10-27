# 第42批：lease41关闭后的全新身份健康恢复

沿用control-preflight-reflect、control-theory-veto及control-postrun-retro。EDA route/STA/WNS/PPA不适用。

现有事实：当前39普通active、40严格V1/fault close、41普通receipt-lease即时stop与退出后旧队列拒绝均通过。39→40及40→41身份链已核对，但41 lease后独立新run尚未实际观测；此差集不能用旧版本或旧终结场景代替。

根因/假设排名：1）身份恢复证据不足，假设已完整退出的41后可以按原全冷启动流程产生全新run/PID-start/Worker instance；2）旧诊断终结tail与正常tail前提不同，假设无故障恢复运行能满足原全部Applied锚点及零尾关闭；3）一次健康前缀不足以说明持续新候选，假设至少两个不同job的Source/Witness/Stored/candidate/Applied/认证phase可独立闭合。

A（选定）：复用同五ELF，只派生Python恢复driver和fresh_recovery helper。读取已封存41同次lease终结、所有owned组退出与独立审计；新完整准备/typed参数/Reader匹配/release后，在business gate前验证全新身份及Worker instance。关闭V1/V2/V3刺激及callback gate，保持business gate显式20s/2sTTL。gate后等待两个不同健康job、实际Applied和认证phase，然后按字节未改的原publisher-first正常关闭分支执行。

B：继续重复lease/V1/active刺激，没有新的待证事实，不选。C：借用旧Worker-terminal reception诊断关闭算正常tail，会丢失完整锚点前提，不选。

GO准入：旧资产全字节保护通过、五角色注册与关键入口复用、旧41证据hash锁定、新入口必要拒绝、CLI和完整SDK loader通过、host未发现所选遗留角色；所有运行输入锁定后只执行fresh_after_lease_01一次。45s总、15s关闭、128MiB raw，外55s INT+20s清理上限；无C++构建/生成代码/安装/硬件/Gazebo/GP/PPO。

验收：旧41五owned组先完成退出，新五manifest的run/PID-start与Worker instance不同，ELF/bundle相同；完整参数查询、当前Native Reader/Writer绑定、新零锚点和新gate均成立，gate前Decision/job0。两个不同健康job的全部immutable Job/Candidate、成功native求解、原150ms绝对ready截止、Witness接纳、实际Publisher Applied/认证phase成立，不把重复job计作新周期。原200ms T、20ms jitter/240ms gap、80N/s实际publish-start率限、±25N、全部旧hook0不变。无worker_unusable或实际故障gate刺激；正常close ACK后无新submit/accepted；原完整anchor序列、两侧实际API末尾零Applied、Fixture GID/Stored全值、全topic SQL/metadata与正常Source/Witness关闭分别核验。五角色0、组空、只必要INT，无强制TERM/KILL/SIGSTOP。

组件入口只按seeded context拒绝检查，不冒充实际新manifest认证；实际raw副本14项针对身份复用、重复job、截止/Applied/phase、失效、缺正常锚点/零尾、关闭后授权和ACK绑定，全部需拒绝。原raw和所有源锁前后SHA不变。

失败原样保存，不放宽正常tail、不把诊断tail改标签，不借别轮填缺口。恢复组件通过不授予B4整体/M4/P1/P2或方案A性能结论；原半RMSE NoGo保留。若成功，只需冻结最终角色/配置并逐组审查B4来源/域/政策，不重复本批。
