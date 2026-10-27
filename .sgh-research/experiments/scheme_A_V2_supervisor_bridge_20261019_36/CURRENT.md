# 方案A当前状态：第36批（2026-10-19）

已实现Source实际终结→身份再认证→即时owned Supervisor stop的显式诊断桥接。Source增量游标持有原inode，绑定Observer实际写FD，分别记录终结、读到、解析、认证、真实killpg调用及逐段wait/组退出；不再等工作线程自然返回或整组关闭才处理中止。

唯一实际run `v2_supervision_01`及独立审计通过，launcher13.287s。终结后82.567ms被本游标读到，162.578ms完成身份再认证，222.915ms发SIGINT。认证后显式SIGSTOP用于确定性覆盖升级；SIGINT返回到TERM调用527.781ms，TERM返回到KILL调用1038.215ms，KILL返回后90.669ms观察到组空。终结到Worker cleanup完成1899.466ms。实际合同等待为500ms／1s／1s，不是500ms总退出界。

Worker返回-9，正常Source资格false保留；其余四角色0，全owned组清空。`supervision_case_completed=true`，原正常业务passed/evidence_qualification_clean及旧V2_case_completed仍false。监督期间10个回退Decision持续，无新submit/accepted activation；最大start/activation jitter0.269ms，start gap200.152ms。Stored1296消息/34 Decision/21 Applied/41 capability，关机零命令Applied21，Source/GID/完整业务值和Recorder SQL/metadata匹配。

本批只验证Source健康、有限本地域及显式暂停后的完整升级诊断，不证明acados C调用挂起、通用通知WCET或正式监督服务全部原因/无诊断暂停分支。12项通知/Source身份反例、3个真实owned子进程清理用例、8项实际raw审计反例通过。五角色ELF、C++及合同沿用，CXX构建0；一次CLI导入顺序错误已在实际运行前修复，原错误和源码快照保留。

有效配置核验纠正前批文档：diag10实际kill_postcheck_ns=1s，原计划写500ms。旧文档未回写；本批Worker stop从合同读取500ms／1s／1s，并逐段核验。500ms是SIGINT后等待，不等同于总组退出时间。其它角色维持已有有限关闭流程，不由本批授予全合同监督资格。

初次全字节保护44388路径/5537587047字节通过；原24个业务dirty、既有real.launch差异、旧资产/失败保留。B4八组pending、B5/M0b、M4、模型事务/F6及原P1整体仍待闭合。下一步按V3核验来源/时钟/32历史选择及最多2次重验交错，最终冻结前另核定正式监督派发和无诊断暂停路径。

MPC交付仅认本批delivery_verification.json存在且passed、完整二次SHA读回通过；本批未重新全读所有历史MPC镜像。
