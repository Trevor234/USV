# 方案A当前状态：第35批（2026-10-19）

V2两项选定的最小实际诊断已通过独立闭合审计。lease：最后有效回调后655.887ms终结；实际暂停1109.464ms，期间Worker成功发布5次能力，恢复后7个合法同身份回调均未续租/复活。active：工作线程1700.076ms屏障期间能力发布和有效接纳各继续6次；active起点后1189.326ms首先触发active watchdog，最近能力回调年龄188.537ms，阻塞Job2没有迟到调用native。两项观察窗口均无skip，最大start/activation jitter约0.345ms、start gap约200.115ms。

独立审计核对Source/Witness、五个owned身份/完整typed配置、实际Writer GID/Fixture/Stored完整业务值、API幅值/按实际publish-start的率限、关机零命令和Recorder SQL/metadata。两个最终run返回0、全组退出清空；driver正常业务passed=false保留，V2_case_completed=true仅表示明确诊断profile完成。Recorder内建stream_accounting=false不改。

共4次启动、3次释放、2次最终profile通过。首次缺库启动未释放；随后lease run确实触发租约失效，但原原因字面门失败、原正常anchor尾段超时。这些源码、数据和失败均保留。最终r3明确识别带同时间Source因果配对的完整原因链，并用独立worker-terminal-reception-v1关闭profile核对认证接收；没有重判旧正常anchor链。

Worker新增显式一次性pre-native策略，旧两个钩子仍0，原释放代码不变。构建1次、Native22断言、时间边界12项、因果/关闭离线10项、实际raw终结不变式8项拒绝检查通过。两项最终run使用相同Worker/Observer及其余角色ELF。新run在旧owned全关闭后重建身份，并在自身故障前形成新的实际accepted prefix。

仍有具体V2监督缺口：本次屏障在watchdog后505.910ms才释放，Worker组在2180.917ms后清空；本批证明15s内整组关闭，不认证500ms监督中止界，也未测试acados C函数内部不可中断挂起或当前组合旧实例包注入。下一步先补“实际终结→owned Supervisor有界stop”闭环，再按V3核验来源/时钟/历史重验交错。

初次本地全字节保护43359路径/5440520275字节通过，原24个业务dirty、既有real.launch差异、旧冻结资产和失败保留。B4八组pending、B5/M0b、M4、有限模型事务/F6、原P1整体及研究结论仍未闭合。各版本资格按实际role组合核对，不累计成全域证明。

MPC交付认本批delivery_verification.json：存在且passed、完整二次SHA读回通过才表示完成；历史MPC全镜像未在本批重新全读。
