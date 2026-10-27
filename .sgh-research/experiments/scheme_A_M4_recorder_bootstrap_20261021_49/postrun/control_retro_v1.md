# 第49批控制实验复盘

使用control-postrun-retro的机制分类、证据、下一步和STOP结构；EDA指标不适用，按用户要求将过程材料保存于本批并同步/home/trevor/MPC。

**假设验证：成立。** 48的主机制为flow_policy_mismatch：完整Recorder屏障与未来Writer互相等待。49只拆分真实进程认证与完整记录就绪，未调合同/数值/预算；实际四角色完成准备、一次grant、20秒正常源、210次真实API及有界退出，独立审计通过。新的unknown初始锚点与T200ms真实zero/heartbeat也在完整API流中获得有限组件证据。

新增经验：process-only只授予端点创建，不授予full storage/Reader或输出权限；GID必须采用原生ABI；来源配置、owned进程与完整Reader集合都须绑定真实版本；Driver中间快照104对与最终105对的shutdown差异应按不同观察时刻保留；接收回调、Source发布、wire与Stored是不同覆盖总体，不能互相改名。

结果层级：正常唯一出口组件合格；当前版本故障矩阵、F6及原P1未合格。首次rho不可用、部分阶段非接纳、Recorder内部accounting=false、Witness旧profile标签和历史失败均如实保留；不从实际API推断plant。

下一步候选：映射原9组到当前源码/ELF，优先发布/关闭分支受影响故障确认。confidence高、impact高、cost中、risk中；每case先确定触发方式、预期例外、输入hash与有限预算，再运行。现有成功正常run不重试，旧39～42不全面重跑。M4范围闭合后再做已知模型原子事务/F6和P1复判。

继续条件：只允许明确的当前执行分支证据缺口及固定预算；无需新全量准备/来源校准。STOP为身份/配置失配、full-ready前API、非法正常激活、未声明drop/超时/partial、cleanup_failed或旧组不空。发生则保存失败，不用放宽阈值处理。

本批资产终态复核此前会话中断，独立留证并改用新输出文件重做；未重复实际ROS试验。归档完成后不自动启动下一故障case。
