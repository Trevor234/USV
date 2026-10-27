# 方案A 第49批当前状态（2026-10-21）

**M4隔离nominal正常唯一出口组件已通过。完整M4、F6、P1尚未验收。** 47的B5/M0b选定工程冻结沿用。

48首次实际入口准备互等、API0的失败保留。49以Recorder process-only进程认证→Regulator创建端点→完整Recorder/Reader/源认证→一次grant解除依赖环，完整就绪之前不调用API。独立新版本run01仅运行一次、自动重试0。

实际正常来源20.001765169s、101个动态Job、窗内100/100决策接纳；全流105对、210次控制API，含bootstrap和shutdown。左右最大间隔200.139/200.175ms、最大pair span0.101ms、最大tick启动迟差0.841ms，满足冻结预算。4053条Stored与Source/实际wire核验；一个末次Capability在Fixture关闭后出现已单独对应，未解释Stored丢失0。四角色仅SIGINT、RC0、owned组为空。

52政策、38源码关联GTest、14原生入口拒绝、14真实Recorder进程pin用例通过；6目标构建成功。回调接收范围、Recorder内部accounting=false和Witness旧标签如实保留，不混同为全部DDS送达或完整M4资格。普通生产release关闭；本隔离运行实际控制API210，非0。没有plant/停船/硬实时/性能优越或GP数据资格。

当前HEAD feb50823a07054879e3c6f8d437c02595ce26976、codex/scheme-c-rl；旧24项内容已在本次前等字节提交，主仓受跟踪文件diff=0、staging为空。既有未跟踪.zcodeignore和ardurover-argus子模块状态标记前后完全保留，不称整个工作区clean。两旧备份头活动路径缺失和.gitignore变更按显式事前例外留证，不声称所有旧原路径未变。47冻结4103项完整，48与历史失败未覆盖。

下一步固定：当前版本原9组M4故障和来源范围差集闭合（优先新发布/退出分支）→有限已知模型model+plan事务/F6→原P1联合复判。不重复45/46、无差集39～42或本次成功正常run，不另加完整no_output阶段，不调RTI/权重/半RMSE。

完整性与交付见postrun/final_QA_v1.json、archive_inventory_v1.json、delivery_verification.json。报告和下一步位于documents目录。
