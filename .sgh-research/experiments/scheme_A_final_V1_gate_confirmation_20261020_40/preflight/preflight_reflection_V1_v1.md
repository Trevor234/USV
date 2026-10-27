# 第40批：当前门控版本的V1与实际故障关闭最小确认

沿用control-preflight-reflect、control-theory-veto、control-postrun-retro。EDA的RC/via/STA/WNS/PPA不适用；本批不开展控制性能对比。

事实：第39批当前Observer已通过38个Native用例和一次门控后的实际普通active停止。第33批V1第一次存在Applied/arm顺序失败，第二次严格顺序通过；第34批独立故障关闭模块完成历史数据审计及组件验证，尚未在当前门控Observer上实际执行。早期失败继续冻结。当前V1、普通lease和新身份恢复仍不能继承为已完成。

根因与假设排名：
1. 最终组合缺口：启动gate改变了业务起点；假设同一ELF内原V1语义保持，但必须证明实际Accepted→Applied→认证ACK早于arm。
2. 故障关闭与正常关闭前提不同：Sink失败后Source普通完整性和正常close ACK不成立；假设已实现的独立profile能完成资源关闭并保留这一失败语义。
3. 异步接收/持久化缺口：退出码与Source自述不足以证明零命令送达；假设Fixture实际GID/原CDR和SQLite全值可独立闭合。

A（选定）：复用第39批五角色ELF、Source bundles、完整graph/typed参数/Reader匹配/释放/gate流程，仅派生V1专用driver，Worker V2 none/0，Observer V3 none/0。接受健康前缀及认证ACK后实际512容量队列填满并拒绝一次DecisionEnqueue，再执行原sink-fault-self-close-v1模块。只运行一次新run final_V1_01。

B：重编译/修改V1或关闭模块。本批已有代码且无新缺陷证据，不选。C：仅重读旧V1并把旧结果算作当前版本完成，不能证明新组合，不选。

准入：初始旧资产全字节保护、五注册ELF/bundle完全一致、原故障模块和gate helper未改、CLI和完整SDK loader通过、无所选角色存活、所有输入锁定。45s总预算，15s关闭，128MiB输出，外层55s INT+20s清理上限；不启硬件、Gazebo、codegen、GP/PPO。固定DDS196 localhost，synthetic nominal，shadow物理Writer=0。

通过条件：门控前Decision/job=0且真实callbacks继续；完整参数查询先于新请求；不延长原150ms ready/job、T200ms、1s首tick lead；实际accepted Decision、实际Applied、认证phase ACK严格先于arm；真实首次Sink拒绝深度512、同边界stop/清slots/candidate/pending、无后续accepted/submit；失败Decision不在Source成功项、Publisherreceipt和Stored中；Witness完整而Observer普通Source完整性false、Observer返回2。五角色固定Observer→Publisher→Worker→Fixture→Recorder关闭，其他返回0、组空、仅必要INT而无TERM/KILL；Observer关闭后的shutdown_zero有真实API、Stored全值和Fixture原CDR/GID，Recorder独立SQL/metadata全数一致。实际数据副本负例至少14项全部拒绝；原始数据SHA/人口不变。

不通过时原样保存，不放宽顺序、时间或Source完整性，不同轮拼接。只按失败证据决定下一步。组件/当前选定故障组合通过不表示B4整体、B5/M4/F6/P1/P2或方案A优越性通过。
