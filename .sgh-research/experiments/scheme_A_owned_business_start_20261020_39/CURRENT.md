# 方案A当前状态：第39批（2026-10-20）

已实现受认证、单次、有界的Observer业务启动门控，并首次完成当前组合的实际普通active监督确认。第38批三次失败及其1841/1843/1845源锁保持原样，未重跑旧脚本。

新policy=owned-prepare-before-business-v1：保留原端点/完整图/typed参数检查/Reader匹配顺序，传感器、Worker能力与Applied接收照常；tick/prepare等到原Publisher release、实际peer绑定、真实初始零Applied与LegacyReady齐备，且driver活PID/start/exe/argv/源码SHA、run/boot/合同及manifest绑定通过后才启动。20s等待、2s请求TTL，默认immediate路径独立，旧五hook0、物理Writer0、150ms/200ms/20ms业务合同不变。

唯一actual run business_active_01通过：门控前Decision/job均0，完整参数查询完成；开门后首phase仅3.386393ms，原150ms界内。健康job1完成后，job2实际pre-native刺激触发active_watchdog。终结后63.494ms被读到，144.550ms完成认证，186.481ms发真实SIGINT；只用SIGINT，Worker返回0且Source完整。终结至Worker cleanup729.590ms；这是本次实测，不是500ms总退出保证。实际只走natural和worker_grace，TERM/KILL未执行。

38项source-linked Native通过；16项实际raw副本反例（6门控、10普通监督）全部拒绝。五组独立审计通过，1924输入前后SHA一致；运行锁1805项不变。Stored1300消息/16 Decision/14 Applied/53 capability，最后Applied14为shutdown_zero。四个停止期间回退Decision连续，最大jitter0.172ms、gap200.037ms。五角色返回0、owned组全空、宿主扫描0遗留。

仅新建Observer ELF（96fc74eb839367b6d420c6d698cc0302d242e1b57a879aaf39f4470d07aa7096），其它四角色与认证/release/Supervisor/普通策略/合同不改。原最终activation、prepare、publication及tick主体字节相同，新增门控入口和等待前无业务保护。CXX首轮构建通过；一次precheck尚缺审计入口文件的准备错误留证，实际前补齐并重验。

组件与选定实际active case已通过；driver普通业务passed仍false（预期故障case），Witness局部normal_contract仅记录完整性/BusinessReady一致性。B4八组整体、B5/M0b、M4、模型事务/F6、原P1与研究结论均未自动通过。当前最终组合V1、普通lease及必要恢复确认下一步按影响图补齐；不重复此active/V3/旧C3矩阵，不调参、不改旧RMSE NoGo。

MPC交付仅认delivery_verification.json的完整二次SHA读回；未重验所有历史远端镜像。
